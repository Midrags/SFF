#!/usr/bin/env bash
# SteaMidra AppImage build script
# Usage: bash build_linux_appimage.sh
# Tested on Linux Mint / Ubuntu / Debian with Python 3.12

set -euo pipefail

APP_NAME="SteaMidra"
APP_VERSION="4.9.0"
ARCH="x86_64"
APPIMAGE_OUT="${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"
APPDIR="${APP_NAME}.AppDir"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> [1/7] Setting up Python virtual environment..."
if [ -d ".venv" ]; then
    echo "    Removing old .venv..."
    rm -rf .venv
fi
python3.12 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
echo "    Python: $(python --version)"
echo "    pip:    $(pip --version)"

echo ""
echo "==> [2/7] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements-linux.txt
pip install steam==1.4.4 --no-deps -q
pip install pyinstaller -q
echo "    Done."

echo ""
echo "==> [3/7] Running PyInstaller..."
rm -rf build dist
pyinstaller build_sff_linux.spec
echo "    Build output: dist/SteaMidra_GUI/"

echo ""
echo "==> [4/7] Creating AppDir structure..."
rm -rf "$APPDIR" "$APPIMAGE_OUT"
mkdir -p "${APPDIR}/usr/bin"
cp -r dist/SteaMidra_GUI/* "${APPDIR}/usr/bin/"
cp SFF.png "${APPDIR}/${APP_NAME}.png"

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
echo "    AppRun written (QTWEBENGINE_DISABLE_SANDBOX=1 included)."

echo ""
echo "==> [6/7] Writing .desktop file..."
DESKTOP_FILE="${APPDIR}/${APP_NAME}.desktop"
printf '[Desktop Entry]\n' > "$DESKTOP_FILE"
printf 'Name=%s\n' "$APP_NAME" >> "$DESKTOP_FILE"
printf 'Exec=SteaMidra_GUI\n' >> "$DESKTOP_FILE"
printf 'Icon=%s\n' "$APP_NAME" >> "$DESKTOP_FILE"
printf 'Terminal=false\n' >> "$DESKTOP_FILE"
printf 'Type=Application\n' >> "$DESKTOP_FILE"
printf 'Categories=Utility;\n' >> "$DESKTOP_FILE"
echo "    Desktop file written."

echo ""
echo "==> [7/7] Packaging AppImage..."
if [ ! -f "appimagetool" ]; then
    echo "    Downloading appimagetool..."
    wget -q -O appimagetool \
        https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool
fi

ARCH=$ARCH ./appimagetool "$APPDIR" "$APPIMAGE_OUT"
chmod +x "$APPIMAGE_OUT"

echo ""
echo "======================================================"
echo "  SUCCESS: ${APPIMAGE_OUT}"
echo "  Run with: ./${APPIMAGE_OUT}"
echo "======================================================"
