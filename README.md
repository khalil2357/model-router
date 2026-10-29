# Model Router (Multi-Model Router)

Unlimited Antigravity & Claude accounts manager with auto proxies, priority list routing, and model failover for Hermes Agent.

## Features
- **Unlimited Antigravity & Claude Accounts**: Multi-account management with auto proxies.
- **Dynamic Failover & Priority Queue**: Automatically routes to backup models if a model rate limits or fails.
- **Cross-Platform**: Full support for Windows, macOS, and Linux.
- **Desktop UI Integration**: Seamless configuration inside Hermes Desktop settings and dashboard.

---

## Installation via Hermes CLI

Anyone can install this plugin directly from GitHub into Hermes:

```bash
hermes plugins install khalil2357/model-router
```

Or using full Git URL:
```bash
hermes plugins install https://github.com/khalil2357/model-router.git
```

---

## Manual Installation (Windows)

1. Open PowerShell and create the target directories:
```powershell
mkdir -Force "$env:USERPROFILE\.hermes\plugins"
```

2. Clone the repository into your plugins directory:
```powershell
git clone https://github.com/khalil2357/model-router.git "$env:USERPROFILE\.hermes\plugins\multi-model-router"
```

3. Restart Hermes CLI or Hermes Desktop:
```powershell
hermes plugins list
```

---

## Manual Installation (macOS / Linux)

```bash
git clone https://github.com/khalil2357/model-router.git ~/.hermes/plugins/multi-model-router
```
Then restart Hermes.
