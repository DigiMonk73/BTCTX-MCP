"""
backend/services/desktop.py

What the Mac app's launcher (desktop/entrypoint.py) told the backend through
environment variables. Outside the Mac app (Docker, StartOS, dev servers)
none of them are set and `is_desktop()` is False.
"""

import os
from typing import Optional


def is_desktop() -> bool:
    return os.environ.get("BTCTX_DESKTOP") == "1"


def _int_env(name: str) -> Optional[int]:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return None


def desktop_info() -> dict:
    """
    {"desktop": bool, "port": int|None, "preferred_port": int|None,
     "port_fallback": bool}. port_fallback is True when the user chose to run
    this session on another port because the usual one was taken; AI
    assistants can't find the app until it restarts on the usual port.
    """
    if not is_desktop():
        return {"desktop": False, "port": None, "preferred_port": None, "port_fallback": False}
    port = _int_env("BTCTX_DESKTOP_ACTUAL_PORT")
    preferred = _int_env("BTCTX_DESKTOP_PREFERRED_PORT")
    return {
        "desktop": True,
        "port": port,
        "preferred_port": preferred,
        "port_fallback": port is not None and preferred is not None and port != preferred,
    }
