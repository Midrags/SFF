#!/usr/bin/env bash
# SteaMidra AppImage build script
# Usage: bash build_linux_appimage.sh [--fresh]
#
#   (no flag)  — reuse existing .venv if PyQt6 is already installed (fast)
#   --fresh    — wipe .venv and reinstall everything from scratch
#                (only needed after requirements-linux.txt changes)
#
# Tested on Linux Mint / Ubuntu / Debian with Python 3.12

set -eo pipefail

FORCE_FRESH=0
for arg in "$@"; do
    [ "$arg" = "--fresh" ] && FORCE_FRESH=1
done

APP_NAME="SteaMidra"
APP_VERSION="4.9.0"
ARCH="x86_64"
APPIMAGE_OUT="${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"
APPDIR="${APP_NAME}.AppDir"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Error handler ─────────────────────────────────────────────────────────────
die() {
    echo ""
    echo "==========================================="
    echo "  ERROR: $*"
    echo "==========================================="
    exit 1
}

# ── Prerequisite check ────────────────────────────────────────────────────────
echo "==> Checking prerequisites..."
MISSING=0
command -v python3.12 >/dev/null 2>&1 || { echo "  MISSING: python3.12 — fix: sudo apt install python3.12 python3.12-venv python3.12-dev"; MISSING=1; }
command -v wget       >/dev/null 2>&1 || { echo "  MISSING: wget       — fix: sudo apt install wget"; MISSING=1; }
dpkg -l libfuse2 >/dev/null 2>&1      || { echo "  MISSING: libfuse2   — fix: sudo apt install libfuse2"; MISSING=1; }
[ "$MISSING" = "1" ] && die "Install the missing packages above, then re-run this script."
echo "    All prerequisites present."

# ── Step 1: Virtual environment ───────────────────────────────────────────────
echo ""
echo "==> [1/7] Virtual environment..."
if [ "$FORCE_FRESH" = "1" ] && [ -d ".venv" ]; then
    echo "    --fresh: removing old .venv..."
    rm -rf .venv
fi

if [ ! -d ".venv" ]; then
    echo "    Creating .venv with Python 3.12..."
    python3.12 -m venv .venv \
        || die "Failed to create venv. Try: sudo apt install python3.12-venv python3.12-dev"
else
    echo "    Reusing existing .venv  (pass --fresh to force full reinstall)"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "    Python: $(python --version) | pip: $(pip --version | awk '{print $2}')"

# ── Step 2: Dependencies ──────────────────────────────────────────────────────
if [ "$FORCE_FRESH" = "1" ] || ! python -c "import PyQt6" 2>/dev/null; then
    echo ""
    echo "==> [2/7] Installing dependencies..."
    echo "    NOTE: PyQt6 + WebEngine are ~250 MB — first run takes 5-20 min."
    echo "    You will see download progress below. Wait even if it looks slow."
    echo ""

    pip install -r requirements-linux.txt \
        --timeout 300 \
        --no-cache-dir \
        --progress-bar on \
        || die "pip install failed.\nCheck your internet connection.\nIf you see ResolutionImpossible, make sure you have the latest requirements-linux.txt."

    pip install "steam==1.4.4" --no-deps \
        || die "Failed to install steam package."

    pip install pyinstaller \
        || die "Failed to install pyinstaller."

    echo ""
    echo "    All dependencies installed."
else
    echo ""
    echo "==> [2/7] PyQt6 already installed — skipping pip install."
    echo "    (pass --fresh to force full reinstall)"
    pip install pyinstaller -q 2>/dev/null || pip install pyinstaller
fi

# ── Step 3: PyInstaller ───────────────────────────────────────────────────────
echo ""
echo "==> [3/7] Running PyInstaller (2-5 min)..."
rm -rf build dist
pyinstaller build_sff_linux.spec \
    || die "PyInstaller failed. Check the output above for the specific error."
echo "    Build output: dist/SteaMidra_GUI/"

# ── Step 4: AppDir ────────────────────────────────────────────────────────────
echo ""
echo "==> [4/7] Creating AppDir structure..."
rm -rf "$APPDIR" "$APPIMAGE_OUT"
mkdir -p "${APPDIR}/usr/bin"
cp -r dist/SteaMidra_GUI/* "${APPDIR}/usr/bin/"

if [ -f "SFF.png" ]; then
    cp SFF.png "${APPDIR}/${APP_NAME}.png"
else
    echo "    WARNING: SFF.png not found — AppImage will launch without an icon."
fi

# ── Step 5: AppRun ────────────────────────────────────────────────────────────
echo ""
echo "==> [5/7] Writing AppRun..."
cat > "${APPDIR}/AppRun" << 'APPRUN_EOF'
#!/usr/bin/env bash
SELF="$(readlink -f "$0")"
HERE="${SELF%/*}"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/bin:$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
export QT_PLUGIN_PATH="$HERE/usr/bin/PyQt6/Qt6/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$HERE/usr/bin/PyQt6/Qt6/plugins/platforms"
export QTWEBENGINE_DISABLE_SANDBOX=1
exec "$HERE/usr/bin/SteaMidra_GUI" "$@"
APPRUN_EOF
chmod +x "${APPDIR}/AppRun"
echo "    AppRun written (QTWEBENGINE_DISABLE_SANDBOX=1 set)."

# ── Step 6: .desktop file ─────────────────────────────────────────────────────
echo ""
echo "==> [6/7] Writing .desktop file..."
DESKTOP_FILE="${APPDIR}/${APP_NAME}.desktop"
printf '[Desktop Entry]\n'      >  "$DESKTOP_FILE"
printf 'Name=%s\n' "$APP_NAME" >> "$DESKTOP_FILE"
printf 'Exec=SteaMidra_GUI\n'  >> "$DESKTOP_FILE"
printf 'Icon=%s\n' "$APP_NAME" >> "$DESKTOP_FILE"
printf 'Terminal=false\n'      >> "$DESKTOP_FILE"
printf 'Type=Application\n'    >> "$DESKTOP_FILE"
printf 'Categories=Utility;\n' >> "$DESKTOP_FILE"
echo "    .desktop file written."

# ── Step 7: appimagetool ──────────────────────────────────────────────────────
echo ""
echo "==> [7/7] Packaging AppImage..."
if [ ! -f "appimagetool" ]; then
    echo "    Downloading appimagetool..."
    wget --show-progress -O appimagetool \
        https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage \
        || die "Failed to download appimagetool. Check your internet connection."
    chmod +x appimagetool
fi

ARCH=$ARCH ./appimagetool "$APPDIR" "$APPIMAGE_OUT" \
    || die "appimagetool failed.\nIf you see 'fuse: device not found', fix with: sudo apt install libfuse2"
chmod +x "$APPIMAGE_OUT"

echo ""
echo "======================================================"
echo "  SUCCESS: ${APPIMAGE_OUT}"
echo "  Run with: ./${APPIMAGE_OUT}"
echo "======================================================"
