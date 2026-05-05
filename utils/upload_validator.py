"""upload_validator.py — validacion magic-bytes para uploads.
Defensa anti-content-spoofing: una foto.jpg renombrada a .pdf no puede pasar
si su contenido empieza con FFD8 (JPEG). De este modo si un atacante intenta
subir un .php disfrazado de .jpg, el header HTTP/JPEG no coincide con el
contenido real y se rechaza.

Uso:
    from utils.upload_validator import validate_upload_bytes, MAX_UPLOAD_SIZE
    content = await file.read()
    ok, kind = validate_upload_bytes(content, ext)
    if not ok:
        raise HTTPException(400, f'Archivo invalido: contenido no coincide con extension {ext}')
"""
from __future__ import annotations
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Tamaño máximo por archivo (15 MB) — protección anti-DoS
MAX_UPLOAD_SIZE = 15 * 1024 * 1024

# Magic numbers (primeros bytes) por tipo de archivo aceptado
_MAGIC = {
    'jpeg':  [b'\xff\xd8\xff'],
    'png':   [b'\x89PNG\r\n\x1a\n'],
    'gif':   [b'GIF87a', b'GIF89a'],
    'webp':  [b'RIFF'],          # RIFF....WEBP
    'pdf':   [b'%PDF-'],
    'mp4':   [b'\x00\x00\x00\x18ftyp', b'\x00\x00\x00\x20ftyp', b'\x00\x00\x00\x1cftyp'],
    'mov':   [b'\x00\x00\x00\x14ftyp', b'\x00\x00\x00\x20ftyp'],
    'avi':   [b'RIFF'],          # RIFF....AVI
    'svg':   [b'<svg', b'<?xml'],
}

# Extensiones permitidas → familia de magic
_EXT_TO_KIND = {
    '.jpg': 'jpeg', '.jpeg': 'jpeg',
    '.png': 'png',
    '.gif': 'gif',
    '.webp': 'webp',
    '.pdf': 'pdf',
    '.mp4': 'mp4',
    '.mov': 'mov',
    '.avi': 'avi',
}


def validate_upload_bytes(content: bytes, ext: str) -> Tuple[bool, str]:
    """Valida que content empiece con el magic apropiado para ext.
    Retorna (ok, kind_str).
    """
    if not content:
        return False, 'empty'
    if len(content) > MAX_UPLOAD_SIZE:
        return False, 'too_large'
    ext = (ext or '').lower()
    if ext not in _EXT_TO_KIND:
        return False, 'ext_not_allowed'
    kind = _EXT_TO_KIND[ext]
    magics = _MAGIC.get(kind, [])
    head = content[:32]
    for m in magics:
        if head.startswith(m):
            # WEBP/AVI extra check: bytes 8..12 = WEBP/AVI (RIFF container)
            if kind == 'webp' and b'WEBP' in head[:16]:
                return True, kind
            if kind == 'avi' and b'AVI ' in head[:16]:
                return True, kind
            if kind in ('webp', 'avi'):
                continue
            return True, kind
    logger.warning('upload rechazado: ext=%s magic-mismatch head=%s', ext, head[:8].hex())
    return False, f'magic_mismatch_{kind}'


def safe_extension(filename: str, default: str = '.bin') -> str:
    """Extrae ext segura de filename (lowercase, validada)."""
    import os
    if not filename:
        return default
    ext = os.path.splitext(filename)[1].lower()
    return ext if ext in _EXT_TO_KIND else default
