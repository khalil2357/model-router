"""multi-model-router manager — cross-platform (macOS, Windows, Linux).

Handles:
* Unlimited Antigravity accounts (~/.hermes/antigravity-accounts/accN) -> ports 8881, 8882... + router 8880
* Unlimited Claude accounts (~/.hermes/claude-accounts/accN) -> ports 8981, 8982... + router 8980
* Per-account auto proxies (launchd on macOS, systemd on Linux, detached on Windows)
* Any model can be selected as default (Antigravity, Claude, OpenAI, etc.)
* Custom model priority list with failover and dynamic switching
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYSTEM = platform.system().lower()
IS_MAC = SYSTEM == "darwin"
IS_LINUX = SYSTEM == "linux"
IS_WIN = SYSTEM == "windows"

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or HOME / ".hermes")
AGY_ACCOUNTS = HERMES_HOME / "antigravity-accounts"
CLAUDE_ACCOUNTS = HERMES_HOME / "claude-accounts"
PROXY_DIR = HERMES_HOME / "tools" / "antigravity-proxy"
LOGDIR = HERMES_HOME / "logs"
PIDDIR = HERMES_HOME / "multi-model-router" / "pids"
DATA_DIR = HERMES_HOME / "multi-model-router"
SETTINGS_FILE = DATA_DIR / "settings.json"
CONFIG_FILE = HERMES_HOME / "config.yaml"

AGY_ROUTER_PORT = 8880
AGY_SLOT_BASE = 8880

CLAUDE_ROUTER_PORT = 8980
CLAUDE_SLOT_BASE = 8980

AGENTS_MAC = HOME / "Library" / "LaunchAgents"
PREFIX_MAC = "com.hermes.modelrouter"

SYSTEMD_USER = HOME / ".config" / "systemd" / "user"
PREFIX_LINUX = "hermes-modelrouter"

_lock = threading.RLock()


# ───────────────────────────── Settings ─────────────────────────────

def _default_settings() -> dict:
    return {
        "version": 1,
        "proxies_desired": "on",
        "autoswitch": {
            "enabled": True,
            "claude_limit": 98,
            "default": {"provider": "custom:claude-auto", "model": "claude-opus-5-5", "label": "Claude Opus 5 · auto"},
            "priority": [
                {"provider": "custom:gemini-auto", "model": "gemini-3.8-flash", "label": "Gemini 3.8 Flash · auto"},
            ],
        },
    }

def load_settings() -> dict:
    with _lock:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        base = _default_settings()
        base.update({k: v for k, v in data.items() if k != "autoswitch"})
        base["autoswitch"].update(data.get("autoswitch") or {})
        return base

def save_settings(data: dict) -> dict:
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)
        return data


# ───────────────────────────── Environment & Core ─────────────────────────────

_py_cache = []

def find_python() -> str:
    if _py_cache:
        return _py_cache[0]
    cands = [os.environ.get("AGACCT_PYTHON", "")]
    if IS_WIN:
        cands += [shutil.which("python"), shutil.which("python3"), shutil.which("py"), sys.executable]
    else:
        for v in ("3.14", "3.13", "3.12", "3.11", "3.10"):
            cands += [f"/opt/homebrew/bin/python{v}", f"/usr/local/bin/python{v}", f"/usr/bin/python{v}", shutil.which(f"python{v}") or ""]
        cands += ["/opt/homebrew/bin/python3", "/usr/bin/python3", sys.executable]
    for c in cands:
        if not c or not os.path.exists(c):
            continue
        try:
            if subprocess.run([c, "-c", "import sys; sys.exit(sys.version_info < (3, 10))"], capture_output=True, timeout=5).returncode == 0:
                _py_cache.append(c)
                return c
        except Exception:
            pass
    return sys.executable

def hermes_bin() -> str:
    for c in [shutil.which("hermes"), shutil.which("hermes.cmd"), shutil.which("hermes.exe"),
              str(HOME / ".local" / "bin" / "hermes"),
              str(HERMES_HOME / "hermes-agent" / ".hermes" / "bin" / "hermes"),
              str(HERMES_HOME / "hermes-agent" / ".venv" / "bin" / "hermes"),
              str(HERMES_HOME / "hermes-agent" / ".venv" / "Scripts" / "hermes.exe")]:
        if c and os.path.exists(c):
            return c
    return "hermes"

def hermes_config_set(key: str, value) -> None:
    val = value if isinstance(value, str) else json.dumps(value)
    subprocess.run([hermes_bin(), "config", "set", key, val], capture_output=True, text=True, timeout=60)

def hermes_config_unset(key: str) -> None:
    subprocess.run([hermes_bin(), "config", "unset", key], capture_output=True, text=True, timeout=60)

def read_config() -> dict:
    try:
        import yaml
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        try:
            from hermes_cli.config import load_config_readonly
            return load_config_readonly() or {}
        except Exception:
            return {}

def healthy(port: int, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False

# ───────────────────────────── Account Folders ─────────────────────────────

def agy_slot_numbers() -> list[int]:
    out = []
    if AGY_ACCOUNTS.is_dir():
        for p in AGY_ACCOUNTS.iterdir():
            if p.name.startswith("acc") and p.name[3:].isdigit() and (p / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").is_file():
                out.append(int(p.name[3:]))
    return sorted(out)

def claude_slot_numbers() -> list[int]:
    out = []
    if CLAUDE_ACCOUNTS.is_dir():
        for p in CLAUDE_ACCOUNTS.iterdir():
            if p.name.startswith("acc") and p.name[3:].isdigit() and (p / "credentials.json").is_file():
                out.append(int(p.name[3:]))
    return sorted(out)

def agy_email(n: int) -> str:
    tf = AGY_ACCOUNTS / f"acc{n}" / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    try:
        raw = json.loads(tf.read_text(encoding="utf-8"))
        seg = raw.get("id_token", "").split(".")[1]
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg)).get("email", "")
    except Exception:
        return f"Antigravity acc{n}"

def claude_info(n: int) -> dict:
    port = CLAUDE_SLOT_BASE + n
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as r:
            return json.load(r)
    except Exception:
        return {}

# ─────────���─────────────────── Process Management ─────────────────────────────

UID = getattr(os, "getuid", lambda: 1000)()

def _kill_port(port: int) -> None:
    if IS_WIN:
        try:
            r = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                    subprocess.run(["taskkill", "/F", "/PID", parts[4]], capture_output=True)
        except Exception:
            pass
    elif shutil.which("lsof"):
        r = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=5)
        for pid in r.stdout.split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    time.sleep(0.3)

def _pidfile(label: str) -> Path:
    PIDDIR.mkdir(parents=True, exist_ok=True)
    return PIDDIR / f"{label}.pid"

def spawn_process(label: str, home_dir: Path, script_name: str, port: int, log_name: str, env_vars: dict = None):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGDIR / log_name
    py = find_python()
    script = PROXY_DIR / script_name

    if IS_MAC:
        AGENTS_MAC.mkdir(parents=True, exist_ok=True)
        plist = AGENTS_MAC / f"{label}.plist"
        env_dict = {
            "HOME": str(home_dir),
            "PATH": f"{HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "PYTHONUNBUFFERED": "1"
        }
        if env_vars:
            env_dict.update(env_vars)
        data = plistlib.dumps({
            "Label": label,
            "ProgramArguments": [py, str(script), "--port", str(port)],
            "WorkingDirectory": str(PROXY_DIR),
            "EnvironmentVariables": env_dict,
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(log_file),
            "StandardErrorPath": str(log_file)
        })
        plist.write_bytes(data)
        subprocess.run(["launchctl", "bootout", f"gui/{UID}/{label}"], capture_output=True)
        if port_open(port):
            _kill_port(port)
        subprocess.run(["launchctl", "bootstrap", f"gui/{UID}", str(plist)], capture_output=True)
        return

    # Windows & Linux background process
    if port_open(port):
        _kill_port(port)
    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)
    env["PYTHONUNBUFFERED"] = "1"
    if env_vars:
        env.update(env_vars)

    flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008) if IS_WIN else 0
    with open(log_file, "a", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            [py, str(script), "--port", str(port)],
            cwd=str(PROXY_DIR), env=env, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
            creationflags=flags, start_new_session=True if not IS_WIN else False
        )
    _pidfile(label).write_text(str(proc.pid))

def stop_process(label: str, port: int):
    if IS_MAC:
        subprocess.run(["launchctl", "bootout", f"gui/{UID}/{label}"], capture_output=True)
        (AGENTS_MAC / f"{label}.plist").unlink(missing_ok=True)
    pf = _pidfile(label)
    if pf.is_file():
        try:
            pid = int(pf.read_text().strip())
            if IS_WIN:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        pf.unlink(missing_ok=True)
    if port_open(port):
        _kill_port(port)

# ───────────────────────────── All Proxies Control ─────────────────────────────

def start_all():
    with _lock:
        s = load_settings()
        s["proxies_desired"] = "on"
        save_settings(s)

        # 1. Start Antigravity accounts
        for n in agy_slot_numbers():
            spawn_process(f"{PREFIX_MAC}.agy{n}", AGY_ACCOUNTS / f"acc{n}", "antigravity_proxy.py", AGY_SLOT_BASE + n, f"antigravity-acc{n}.log")
        if agy_slot_numbers():
            spawn_process(f"{PREFIX_MAC}.agyrouter", HOME, "gemini_router.py", AGY_ROUTER_PORT, "gemini-router.log")

        # 2. Start Claude accounts
        for n in claude_slot_numbers():
            cred_file = CLAUDE_ACCOUNTS / f"acc{n}" / "credentials.json"
            spawn_process(f"{PREFIX_MAC}.claude{n}", CLAUDE_ACCOUNTS / f"acc{n}", "claude_proxy.py", CLAUDE_SLOT_BASE + n, f"claude-acc{n}.log", {"CLAUDE_CREDENTIALS_FILE": str(cred_file)})
        if claude_slot_numbers():
            spawn_process(f"{PREFIX_MAC}.clauderouter", HOME, "claude_router.py", CLAUDE_ROUTER_PORT, "claude-router.log")

        # Register providers into Hermes
        sync_hermes_providers()
        return status()

def stop_all():
    with _lock:
        s = load_settings()
        s["proxies_desired"] = "off"
        save_settings(s)

        for n in agy_slot_numbers():
            stop_process(f"{PREFIX_MAC}.agy{n}", AGY_SLOT_BASE + n)
        stop_process(f"{PREFIX_MAC}.agyrouter", AGY_ROUTER_PORT)

        for n in claude_slot_numbers():
            stop_process(f"{PREFIX_MAC}.claude{n}", CLAUDE_SLOT_BASE + n)
        stop_process(f"{PREFIX_MAC}.clauderouter", CLAUDE_ROUTER_PORT)

        return status()

def sync_hermes_providers():
    # 1. Antigravity router provider
    if agy_slot_numbers():
        hermes_config_set("providers.gemini-auto", {
            "name": "Gemini 3.8 Flash · auto",
            "base_url": f"http://127.0.0.1:{AGY_ROUTER_PORT}/v1",
            "api_key": "antigravity",
            "default_model": "gemini-3.8-flash",
            "models": {"gemini-3.8-flash": {}},
            "discover_models": False
        })
    # 2. Claude router provider
    if claude_slot_numbers():
        hermes_config_set("providers.claude-auto", {
            "name": "Claude · auto",
            "base_url": f"http://127.0.0.1:{CLAUDE_ROUTER_PORT}/v1",
            "api_key": "claude",
            "default_model": "claude-opus-5-5",
            "models": {
                "claude-opus-5-5": {},
                "claude-sonnet-4-6": {},
                "claude-3-7-sonnet-20250219": {},
                "claude-3-5-sonnet-20241022": {}
            },
            "discover_models": False
        })

def status():
    agy_slots = agy_slot_numbers()
    claude_slots = claude_slot_numbers()

    ports = [AGY_ROUTER_PORT, CLAUDE_ROUTER_PORT] + [AGY_SLOT_BASE + n for n in agy_slots] + [CLAUDE_SLOT_BASE + n for n in claude_slots]
    health = {}
    for pt in ports:
        health[pt] = healthy(pt, timeout=0.8)

    # Antigravity router queue
    agy_router_st = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{AGY_ROUTER_PORT}/status", timeout=2) as r:
            agy_router_st = json.load(r)
    except Exception:
        pass

    # Claude router queue
    claude_router_st = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CLAUDE_ROUTER_PORT}/status", timeout=2) as r:
            claude_router_st = json.load(r)
    except Exception:
        pass

    agy_accounts = []
    queue_map = {q["slot"]: q for q in (agy_router_st or {}).get("queue", [])}
    for n in agy_slots:
        q = queue_map.get(n) or {}
        agy_accounts.append({
            "slot": n,
            "type": "antigravity",
            "email": agy_email(n),
            "port": AGY_SLOT_BASE + n,
            "proxy": health.get(AGY_SLOT_BASE + n, False),
            "remaining": q.get("remaining"),
            "eligible": q.get("eligible"),
            "reason": q.get("reason"),
            "reset": q.get("reset")
        })

    claude_accounts = []
    c_queue_map = {q["slot"]: q for q in (claude_router_st or {}).get("queue", [])}
    for n in claude_slots:
        q = c_queue_map.get(n) or {}
        claude_accounts.append({
            "slot": n,
            "type": "claude",
            "email": q.get("email") or f"Claude acc{n}",
            "name": q.get("name", ""),
            "port": CLAUDE_SLOT_BASE + n,
            "proxy": health.get(CLAUDE_SLOT_BASE + n, False),
            "used": q.get("used"),
            "remaining": q.get("remaining"),
            "eligible": q.get("eligible"),
            "reason": q.get("reason"),
            "reset": q.get("reset")
        })

    total_accs = len(agy_accounts) + len(claude_accounts)
    running = sum(1 for a in agy_accounts if a["proxy"]) + sum(1 for a in claude_accounts if a["proxy"])

    if total_accs == 0:
        st = "none"
    elif running == total_accs and health.get(AGY_ROUTER_PORT, True) and health.get(CLAUDE_ROUTER_PORT, True):
        st = "on"
    elif running == 0:
        st = "off"
    else:
        st = "partial"

    return {
        "state": st,
        "desired": load_settings()["proxies_desired"],
        "antigravity": {
            "router_up": health.get(AGY_ROUTER_PORT, False),
            "accounts": agy_accounts,
            "count": len(agy_accounts)
        },
        "claude": {
            "router_up": health.get(CLAUDE_ROUTER_PORT, False),
            "accounts": claude_accounts,
            "count": len(claude_accounts)
        },
        "total_accounts": total_accs,
        "running_proxies": running,
        "platform": SYSTEM
    }

def ensure():
    st = status()
    if st["desired"] == "on" and st["state"] in ("off", "partial"):
        return {"acted": True, "report": start_all()}
    return {"acted": False, "state": st["state"]}

# ───────────────────────────── Auto-switch and Priority ─────────────────────────────

def chain_status():
    s = load_settings()
    a = s["autoswitch"]
    entries = []
    all_status = status()
    
    # Evaluate each entry in the priority chain
    for e in [a.get("default")] + list(a.get("priority") or []):
        if not e or not e.get("provider") or not e.get("model"):
            continue
        prov, model = e["provider"], e["model"]
        st, detail = "ok", ""

        if prov == "custom:claude-auto":
            c_info = all_status["claude"]
            if not c_info["router_up"]:
                st, detail = "down", "Claude router down"
            else:
                ready = sum(1 for acc in c_info["accounts"] if acc.get("eligible") is not False)
                detail = f"{ready}/{c_info['count']} Claude accounts ready"
        elif prov == "custom:gemini-auto":
            g_info = all_status["antigravity"]
            if not g_info["router_up"]:
                st, detail = "down", "Antigravity router down"
            else:
                ready = sum(1 for acc in g_info["accounts"] if acc.get("eligible") is not False)
                detail = f"{ready}/{g_info['count']} accounts ready"
        
        entries.append({**e, "status": st, "detail": detail})

    active = 0
    return {
        "enabled": bool(a.get("enabled")),
        "default": a.get("default"),
        "priority": a.get("priority") or [],
        "entries": entries,
        "active": active
    }

def apply_autoswitch() -> dict:
    s = load_settings()
    a = s["autoswitch"]
    full = [a.get("default")] + list(a.get("priority") or [])
    full = [e for e in full if e and e.get("provider") and e.get("model")]
    
    cfg = read_config()
    changed = []
    default = a.get("default")
    if default:
        m = cfg.get("model") or {}
        if m.get("default") != default["model"]:
            hermes_config_set("model.default", default["model"])
            changed.append("model.default")
        if m.get("provider") != default["provider"]:
            hermes_config_set("model.provider", default["provider"])
            changed.append("model.provider")
            
    fallbacks = [{"provider": e["provider"], "model": e["model"]} for e in full[1:]] if a.get("enabled") else []
    if (cfg.get("fallback_providers") or []) != fallbacks:
        hermes_config_set("fallback_providers", fallbacks)
        changed.append("fallback_providers")
    return {"enabled": bool(a.get("enabled")), "chain": full, "written": changed}

def set_autoswitch(patch: dict) -> dict:
    with _lock:
        s = load_settings()
        a = s["autoswitch"]
        if "enabled" in patch:
            a["enabled"] = bool(patch["enabled"])
        if "default" in patch:
            a["default"] = patch["default"]
        if "priority" in patch:
            a["priority"] = patch["priority"]
        save_settings(s)
    apply_autoswitch()
    return chain_status()

# ───────────────────────────── Sign-In / Add Account Logic ─────────────────────────────

_logins = {}

def _open_incognito_browser(url: str) -> None:
    try:
        if IS_MAC and os.path.isdir("/Applications/Google Chrome.app"):
            subprocess.Popen(["open", "-na", "Google Chrome", "--args", "--incognito", url])
            return
        elif IS_WIN:
            for cpath in [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            ]:
                if os.path.isfile(cpath):
                    subprocess.Popen([cpath, "--incognito", url])
                    return
        elif IS_LINUX:
            for b in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
                if shutil.which(b):
                    subprocess.Popen([b, "--incognito", url])
                    return
    except Exception:
        pass
    try:
        webbrowser.open(url)
    except Exception:
        pass

# ── Antigravity Login ──

def agy_login_start(open_browser: bool = True) -> dict:
    spec = importlib.util.spec_from_file_location("_ag_login", PROXY_DIR / "agacct_login.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    
    verifier = mod.b64url(secrets.token_bytes(48))
    challenge = mod.b64url(hashlib.sha256(verifier.encode()).digest())
    url = mod.AUTH_URL + "?" + urllib.parse.urlencode({
        "access_type": "offline", "client_id": mod.ag.CLIENT_ID, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "consent select_account",
        "redirect_uri": mod.REDIRECT_URI, "response_type": "code",
        "scope": " ".join(mod.SCOPES), "state": mod.b64url(secrets.token_bytes(16)),
    })
    sid = secrets.token_urlsafe(12)
    next_slot = 1
    while (AGY_ACCOUNTS / f"acc{next_slot}" / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").exists():
        next_slot += 1

    _logins[sid] = {"type": "antigravity", "verifier": verifier, "at": time.time(), "slot": next_slot}
    if open_browser:
        _open_incognito_browser(url)
    return {"session": sid, "url": url, "slot": next_slot}

def agy_login_complete(session: str, code: str) -> dict:
    s = _logins.get(session)
    if not s or s.get("type") != "antigravity":
        raise ValueError("Sign-in session expired. Please click 'Add Antigravity Account' again.")
    spec = importlib.util.spec_from_file_location("_ag_login", PROXY_DIR / "agacct_login.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    code = mod.extract_code(code or "")
    if not code:
        raise ValueError("No authorization code entered")
    tok = mod.exchange(code, s["verifier"])
    if not tok.get("refresh_token"):
        raise ValueError("Google did not return a refresh token — try again")

    import datetime as dt
    expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(tok.get("expires_in", 3600)))
    data = {
        "token": {
            "access_token": tok["access_token"], "token_type": tok.get("token_type", "Bearer"),
            "refresh_token": tok["refresh_token"],
            "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        },
        "auth_method": "consumer", "id_token": tok.get("id_token", "")
    }

    n = s["slot"]
    home = AGY_ACCOUNTS / f"acc{n}"
    token_dest = home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    token_dest.parent.mkdir(parents=True, exist_ok=True)
    token_dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _logins.pop(session, None)

    # Start proxy for new slot
    spawn_process(f"{PREFIX_MAC}.agy{n}", home, "antigravity_proxy.py", AGY_SLOT_BASE + n, f"antigravity-acc{n}.log")
    spawn_process(f"{PREFIX_MAC}.agyrouter", HOME, "gemini_router.py", AGY_ROUTER_PORT, "gemini-router.log")
    sync_hermes_providers()
    return status()

def remove_agy_account(slot: int) -> dict:
    stop_process(f"{PREFIX_MAC}.agy{slot}", AGY_SLOT_BASE + slot)
    shutil.rmtree(AGY_ACCOUNTS / f"acc{slot}", ignore_errors=True)
    return status()

# ── Claude Login ──

def claude_login_start(open_browser: bool = True) -> dict:
    spec = importlib.util.spec_from_file_location("_claude_login", PROXY_DIR / "claude_login.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    verifier, challenge = mod._generate_pkce()
    oauth_state = secrets.token_urlsafe(32)
    params = {
        "code": "true",
        "client_id": mod._OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": mod._OAUTH_REDIRECT_URI,
        "scope": mod._OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": oauth_state,
    }
    url = f"https://claude.ai/oauth/authorize?{urllib.parse.urlencode(params)}"
    sid = secrets.token_urlsafe(12)
    next_slot = 1
    while (CLAUDE_ACCOUNTS / f"acc{next_slot}" / "credentials.json").exists():
        next_slot += 1

    _logins[sid] = {"type": "claude", "verifier": verifier, "state": oauth_state, "at": time.time(), "slot": next_slot}
    if open_browser:
        _open_incognito_browser(url)
    return {"session": sid, "url": url, "slot": next_slot}

def claude_login_complete(session: str, code: str) -> dict:
    s = _logins.get(session)
    if not s or s.get("type") != "claude":
        raise ValueError("Sign-in session expired. Please click 'Add Claude Account' again.")
    spec = importlib.util.spec_from_file_location("_claude_login", PROXY_DIR / "claude_login.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    code = (code or "").strip()
    if not code:
        raise ValueError("No authorization code entered")
    splits = code.split("#")
    auth_code = splits[0]
    rec_state = splits[1] if len(splits) > 1 else s["state"]

    tok = mod.exchange(auth_code, s["verifier"], rec_state)
    access = tok.get("access_token")
    if not access:
        raise ValueError("No access token returned from Claude")

    data = {
        "claudeAiOauth": {
            "accessToken": access,
            "refreshToken": tok.get("refresh_token", ""),
            "expiresAt": int(time.time() + tok.get("expires_in", 3600)) * 1000
        }
    }
    n = s["slot"]
    home = CLAUDE_ACCOUNTS / f"acc{n}"
    home.mkdir(parents=True, exist_ok=True)
    cred_file = home / "credentials.json"
    cred_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _logins.pop(session, None)

    # Start proxy for new slot
    spawn_process(f"{PREFIX_MAC}.claude{n}", home, "claude_proxy.py", CLAUDE_SLOT_BASE + n, f"claude-acc{n}.log", {"CLAUDE_CREDENTIALS_FILE": str(cred_file)})
    spawn_process(f"{PREFIX_MAC}.clauderouter", HOME, "claude_router.py", CLAUDE_ROUTER_PORT, "claude-router.log")
    sync_hermes_providers()
    return status()

def remove_claude_account(slot: int) -> dict:
    stop_process(f"{PREFIX_MAC}.claude{slot}", CLAUDE_SLOT_BASE + slot)
    shutil.rmtree(CLAUDE_ACCOUNTS / f"acc{slot}", ignore_errors=True)
    return status()
