"""REST API endpoints for multi-model-router."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException

router = APIRouter()
_PLUGIN = Path(__file__).resolve().parent.parent

def _m():
    mod = sys.modules.get("multi_model_router_manager")
    if mod is None:
        spec = importlib.util.spec_from_file_location("multi_model_router_manager", _PLUGIN / "manager.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["multi_model_router_manager"] = mod
        spec.loader.exec_module(mod)
    return mod

def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/status")
def get_status(ensure: bool = False):
    m = _m()
    if ensure:
        _run(m.ensure)
    return _run(m.status)

@router.post("/proxies/start")
def start_proxies():
    m = _m()
    return _run(m.start_all)

@router.post("/proxies/stop")
def stop_proxies():
    m = _m()
    return _run(m.stop_all)

@router.get("/autoswitch")
def get_autoswitch():
    m = _m()
    return _run(m.chain_status)

@router.put("/autoswitch")
def put_autoswitch(body: dict = Body(...)):
    m = _m()
    return _run(m.set_autoswitch, body)

# ── Sign-in routes ──

@router.post("/agy/login/start")
def agy_start(body: dict = Body(default={})):
    return _run(_m().agy_login_start, bool(body.get("open_browser", True)))

@router.post("/agy/login/complete")
def agy_complete(body: dict = Body(...)):
    return _run(_m().agy_login_complete, str(body.get("session") or ""), str(body.get("code") or ""))

@router.delete("/agy/accounts/{slot}")
def agy_remove(slot: int):
    return _run(_m().remove_agy_account, slot)

@router.post("/claude/login/start")
def claude_start(body: dict = Body(default={})):
    return _run(_m().claude_login_start, bool(body.get("open_browser", True)))

@router.post("/claude/login/complete")
def claude_complete(body: dict = Body(...)):
    return _run(_m().claude_login_complete, str(body.get("session") or ""), str(body.get("code") or ""))

@router.delete("/claude/accounts/{slot}")
def claude_remove(slot: int):
    return _run(_m().remove_claude_account, slot)
