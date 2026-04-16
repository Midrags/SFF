# Python Setup

How to run SteaMidra from source or build the EXE yourself.

> Most users should use the pre-built EXE from [GitHub Releases](https://github.com/Midrags/SFF/releases/latest). This guide is for developers and advanced users only.

---

## Prerequisites

- Python 3.11 or newer — download from [python.org](https://www.python.org/)
- pip (included with Python)
- Git (optional, for cloning the repo)

---

## Install dependencies

Two commands are required. The second bypasses a stale `urllib3<2` constraint in `steam==1.4.4` that conflicts with Selenium 4.x — Steam works fine at runtime with urllib3 2.x:

```batch
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps
```

For the multiplayer fix feature, also run:

```batch
install_online_fix_requirements.bat
```

**Optional** (Windows desktop notifications):

```batch
pip install -r requirements-optional.txt
```

---

## Virtual environment (recommended)

If you have other Python projects and want to avoid dependency conflicts:

```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps
```

---

## Running from source

**CLI:**

```batch
python Main.py
```

**GUI:**

```batch
python Main_gui.py
```

---

## Building the EXE

**CLI EXE:**

```batch
build_simple.bat
```

Then run `dist\SteaMidra.exe`.

**GUI EXE:**

```batch
build_simple_gui.bat
```

Then run `dist\SteaMidra_GUI.exe`.

---

## Problems?

See [Troubleshooting](TROUBLESHOOTING.md) for common errors, or ask on [Discord](https://discord.gg/V8aZqnbB84).
