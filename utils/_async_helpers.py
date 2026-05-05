"""
utils/_async_helpers.py — Reemplazo de threading.Thread(daemon=True) por
ThreadPoolExecutor centralizado con backpressure + logging.

2026-05-04 FASE1.4: el patron `Thread(daemon=True).start()` en helpers de push
notifications mataba threads en deploy y silenciaba excepciones. Este modulo
provee `fire_and_forget(fn, *args, **kwargs)` con un pool acotado y logging
de cualquier excepcion no capturada.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_log = logging.getLogger("sandoval.faf")

_MAX_WORKERS = int(os.getenv("FAF_WORKERS", "8"))
_pool = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS,
    thread_name_prefix="sandoval-faf",
)


def _log_exc(fut):
    exc = fut.exception()
    if exc is not None:
        _log.exception("fire_and_forget task failed: %s", exc)


def fire_and_forget(fn: Callable[..., Any], *args, **kwargs) -> None:
    """
    Encola fn(*args, **kwargs) en el pool. Si la funcion lanza, se loguea pero
    no propaga al caller (semantica fire-and-forget). Reemplaza:

        threading.Thread(target=fn, args=..., kwargs=..., daemon=True).start()
    """
    try:
        fut = _pool.submit(fn, *args, **kwargs)
        fut.add_done_callback(_log_exc)
    except Exception as e:  # pool full o shutdown
        _log.error("fire_and_forget submit fallo: %s", e)


def shutdown_pool(wait: bool = False, timeout: float = 5.0) -> None:
    """Llamar en el shutdown del proceso para drain ordenado."""
    try:
        _pool.shutdown(wait=wait, cancel_futures=not wait)
    except Exception:
        pass
