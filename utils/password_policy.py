"""password_policy.py - Politica de contrasenas para admin/staff.
Para clientes (PIN 4-6 digitos) NO aplica - se mantiene la UX intencional.
"""
from __future__ import annotations
import re
from typing import Tuple

# Lista corta de contrasenas comunes que NO se aceptan ni cumpliendo otras reglas
_COMMON = {
    'password', 'admin123', 'qwerty12345', 'sandoval123', 'mecanica123',
    'milton2024', 'milton2025', 'milton2026', 'taller123', 'sandoval2026',
    'administrador', 'cambiar123', 'password1', 'admin12345', 'aaaa1111',
    'changeme', 'welcome123', 'p@ssw0rd', 'qwertyuiop',
}


def validate_password_strength(password: str, *, role: str = 'admin') -> Tuple[bool, str]:
    """Valida fortaleza de password segun rol.
    role='admin' o 'staff' -> politica fuerte (10+ chars + complejidad).
    role='cliente' -> NO valida (PIN numerico es UX intencional).
    Retorna (ok, motivo).
    """
    if role == 'cliente':
        return True, 'OK (cliente PIN exempt)'

    if not password or not isinstance(password, str):
        return False, 'Contrasena vacia'

    if len(password) < 10:
        return False, 'Minimo 10 caracteres'
    if len(password) > 128:
        return False, 'Maximo 128 caracteres'

    if not re.search(r'[A-Z]', password):
        return False, 'Debe contener al menos una letra mayuscula'
    if not re.search(r'[a-z]', password):
        return False, 'Debe contener al menos una letra minuscula'
    if not re.search(r'\d', password):
        return False, 'Debe contener al menos un numero'

    # Rechazar contrasenas comunes (case-insensitive)
    if password.lower() in _COMMON:
        return False, 'Contrasena demasiado comun, elige otra'

    # Rechazar repeticiones obvias (todo el mismo char)
    if len(set(password)) <= 3:
        return False, 'Demasiados caracteres repetidos'

    # Rechazar secuencias triviales
    seq_low = ['0123456789', 'abcdefghijklmnop', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']
    pl = password.lower()
    for s in seq_low:
        for i in range(len(s) - 5):
            if s[i:i+6] in pl:
                return False, 'Contiene secuencia trivial (ej. 123456 / qwerty)'

    return True, 'OK'
