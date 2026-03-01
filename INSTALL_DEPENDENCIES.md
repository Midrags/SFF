# Installing Dependencies

Made by Midrag.

## Quick Install (Recommended)

Install all dependencies (CLI, GUI, and online-fix) with a single command:

```batch
pip install -r requirements.txt
```

If that fails with a grpcio-tools build error (common on Windows):

```batch
pip install -r requirements-consumer.txt
```

## Avoid Dependency Conflicts

If you get dependency conflicts with other projects (fastapi, grpcio-tools, spotdl, etc.), use a virtual environment:

```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements-consumer.txt
```

Then run or build from that environment.

## GUI Build Requirements

For building the GUI executable (`build_simple_gui.bat`), install the full requirements first:

```batch
pip install -r requirements.txt
```

Or if grpcio-tools fails:

```batch
pip install -r requirements-consumer.txt
```

Then run `build_simple_gui.bat`.

## What Gets Installed

- **httpx** - Modern HTTP client for making web requests
- **beautifulsoup4** - HTML parsing library
- **lxml** - Fast XML/HTML parser (backend for BeautifulSoup)

## Why These Dependencies?

The multiplayer fix feature uses HTTP requests to download fixes from online-fix.me. These libraries enable:

- Direct HTTP communication (no browser needed)
- HTML parsing to find download links
- Fast and reliable downloads

## Multiplayer fix (online-fix.me)

The **Apply multiplayer fix** option uses HTTP requests to download fixes from online-fix.me. It uses **httpx**, **beautifulsoup4**, and **selenium**. All of these are included in the main requirements.

**If `pip install -r requirements.txt` fails with a grpcio-tools build error** (common on Windows): use `pip install -r requirements-consumer.txt` instead. This skips grpcio-tools (a dev-only package) and installs all runtime dependencies.

## Verifying Installation

To verify the dependencies are installed correctly:

```python
python -c "import httpx; import bs4; print('All dependencies installed!')"
```

If you see "All dependencies installed!", you're good to go!

## Requirements Files

- **requirements.txt** – Full project (CLI, GUI, online-fix in one)
- **requirements-consumer.txt** – Runtime only, no grpcio-tools (use if grpcio-tools fails)

## Troubleshooting

### Dependency conflicts with fastapi, grpcio-tools, spotdl, etc.
Use a virtual environment so SteaMidra dependencies do not affect other projects:
```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements-consumer.txt
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

For the GUI build: `build_simple_gui.bat`. Install full requirements first: `pip install -r requirements-consumer.txt`
