# Installing Dependencies

Made by Midrag.

## Quick Install (Recommended)

**Run the installer script** — it installs everything AND offers to set up Tor Expert Bundle:

```batch
install_online_fix_requirements.bat
```

Or run pip directly (two commands — both needed):

```batch
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps
```

Why two commands? `steam==1.4.4` has a stale `urllib3<2` constraint that conflicts with Selenium 4.x. Using `--no-deps` skips that outdated check — steam works fine with urllib3 2.x at runtime.

`requirements.txt` covers everything in one file: CLI, GUI (PyQt6), online-fix (Selenium), and Tor fallback (`torpy`).

## Avoid Dependency Conflicts

If you get conflicts with other projects, use a virtual environment:

```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps
```

## What Gets Installed

- **httpx** — HTTP client for web requests
- **beautifulsoup4 / lxml** — HTML parsing for online-fix
- **selenium** — Browser automation for multiplayer fix (Chrome required)
- **seleniumbase** — UC mode for SteamDB Cloudflare bypass (Layer 3)
- **curl_cffi** — Chrome impersonation for SteamDB fast path (Layer 1)
- **PyQt6 / PyQt6-WebEngine** — GUI
- **torpy / pysocks** — Pure-Python Tor fallback for GMRC request codes
- **steam / gevent / protobuf** — Steam CDN and depot access
- All other transitive dependencies

## Multiplayer fix (online-fix.me)

The **Apply multiplayer fix** option uses Selenium + Chrome. Chrome browser must be installed separately.

## Tor Expert Bundle (optional)

SteaMidra uses Tor as an automatic fallback when the primary GMRC endpoint is unreachable. Without it, it falls back to ManifestHub API or manual code entry — the tool still works fine without Tor.

To enable automatic Tor fallback:
1. Run `install_online_fix_requirements.bat` and answer **Y** when asked
2. Or visit: https://www.torproject.org/download/#tor-downloads
3. Download **Expert Bundle** (no browser needed — just the daemon)
4. Unzip anywhere, run `tor.exe` before using the tool (it listens on `:9050`)

## Verifying Installation

```python
python -c "import httpx; import bs4; import PyQt6; print('All dependencies installed!')"
```

## Troubleshooting

### "Failed building wheel for greenlet"
`greenlet==3.2.5` has no pre-built wheel for Python 3.12 on Windows and requires MSVC to build.
`requirements.txt` is pinned to `greenlet==3.2.4` which has a wheel — so this error should not occur.
If you see it, make sure you are using the latest `requirements.txt`.

### Dependency conflicts with other projects
Use a virtual environment (see above).

### "No module named 'httpx'" / other ModuleNotFoundError
Run: `pip install -r requirements.txt`

### pip not found
Make sure Python 3.12 is installed and added to PATH.

## Building EXE

Install requirements first (both commands), then build:

```batch
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps

build_simple.bat        # CLI build
build_simple_gui.bat    # GUI build (requires PyQt6 — already in requirements.txt)
```
