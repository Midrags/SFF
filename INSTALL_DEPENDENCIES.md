# Installing Dependencies

Made by Midrag.

## Avoid Dependency Conflicts (Recommended)

If you get dependency conflicts with other projects (fastapi, grpcio-tools, spotdl, etc.), use a virtual environment:

```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements-consumer.txt
pip install -r requirements-gui.txt
```

Then run or build from that environment.

## Quick Install (Recommended)

Run the installation script:
```batch
install_online_fix_requirements.bat
```

This will install all required dependencies for the multiplayer fix feature.

## Manual Install

If you prefer to install manually:

```batch
pip install httpx beautifulsoup4 lxml
```

## GUI Build Requirements

For building the GUI executable (`build_simple_gui.bat`):

```batch
pip install -r requirements-gui.txt
```

Or if you already have the full project installed:

```batch
pip install PyQt6 PyQt6-WebEngine PyInstaller
```

## What Gets Installed

- **httpx** - Modern HTTP client for making web requests
- **beautifulsoup4** - HTML parsing library
- **lxml** - Fast XML/HTML parser (backend for BeautifulSoup)

## Why These Dependencies?

The multiplayer fix feature uses HTTP requests to download fixes from online-fix.me. These libraries enable:

- Direct HTTP communication (no browser needed)
- HTML parsing to find download links
- Fast and reliable downloads

## Multiplayer fix (online-fix.me) – HTTP only (no Chrome)

The **Apply multiplayer fix** option uses HTTP requests only: no browser, Chrome, or ChromeDriver needed. It uses **httpx** and **beautifulsoup4** to search, log in, and download from online-fix.me.

If you use the main install (`pip install -e .` or `pip install -r requirements.txt`), these are already included. To install only the online-fix extras: `pip install -r requirements-online-fix.txt`.

**If `pip install -r requirements.txt` fails with a grpcio-tools build error** (common on Windows): use `pip install -r requirements-consumer.txt` instead. This skips grpcio-tools (a dev-only package) and installs all runtime dependencies.

## Verifying Installation

To verify the dependencies are installed correctly:

```python
python -c "import httpx; import bs4; print('All dependencies installed!')"
```

If you see "All dependencies installed!", you're good to go!

## Requirements Files

- **requirements.txt** – Full project (from pyproject.toml)
- **requirements-consumer.txt** – Runtime only, no grpcio-tools (use if grpcio-tools fails)
- **requirements-gui.txt** – GUI build only (PyQt6, PyQt6-WebEngine, PyInstaller)

## Troubleshooting

### Dependency conflicts with fastapi, grpcio-tools, spotdl, etc.
Use a virtual environment so SteaMidra dependencies do not affect other projects:
```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements-consumer.txt
pip install -r requirements-gui.txt
```

### grpcio-tools build error
If pip fails with "Failed to build grpcio-tools when getting requirements to build wheel", use:
```batch
pip install -r requirements-consumer.txt
```

### "No module named 'httpx'"
Run: `pip install httpx`

### "No module named 'colorama'" or other ModuleNotFoundError
Install dependencies: `pip install -r requirements-consumer.txt`

### "No module named 'bs4'"
Run: `pip install beautifulsoup4`

### "No module named 'lxml'"
Run: `pip install lxml`

### pip not found
Make sure Python is installed and added to PATH.

## Building EXE

After installing dependencies, rebuild the EXE:

```batch
build_simple.bat
```

For the GUI build: `build_simple_gui.bat`. Install GUI deps first: `pip install -r requirements-gui.txt`
