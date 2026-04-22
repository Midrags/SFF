#!/usr/bin/env bash
# SteaMidra Linux Install Script
# Usage: bash steamidra_install.sh [install|uninstall]
#
# Supports three install types (auto-detected):
#   appimage  — SteaMidra*.AppImage next to this script
#   binary    — SteaMidra binary (PyInstaller onefile) next to this script
#   source    — Main.py + requirements.txt next to this script
#
# Environment variables:
#   SKIPVENV=1   Skip venv creation/rebuild (uses existing .venv)

set -euo pipefail

APP_NAME="SteaMidra"
INSTALL_DIR="$HOME/.local/share/SteaMidra"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_THEME_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── notify-send detection ─────────────────────────────────────────────────────
NOTIFY_SEND_AVAILABLE=1
command -v notify-send &>/dev/null && NOTIFY_SEND_AVAILABLE=0

# ── Logging ───────────────────────────────────────────────────────────────────
log_info() {
    echo -e "${GREEN}[SteaMidra]${NC} $1"
    set +eu
    if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
        notify-send -t 5000 "SteaMidra" "$1" 2>/dev/null
    fi
    set -eu
}

log_warn() {
    echo -e "${YELLOW}[SteaMidra]${NC} $1"
    set +eu
    if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
        notify-send -t 5000 -u normal "SteaMidra" "$1" 2>/dev/null
    fi
    set -eu
}

log_error() {
    echo -e "${RED}[SteaMidra]${NC} $1" >&2
    set +eu
    if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
        notify-send -t 10000 -u critical "SteaMidra Error" "$1" 2>/dev/null
    fi
    set -eu
}

# ── Install type detection ────────────────────────────────────────────────────
detect_install_type() {
    # AppImage: any SteaMidra*.AppImage or steamidra*.AppImage next to the script
    for f in "$SCRIPT_DIR"/SteaMidra*.AppImage "$SCRIPT_DIR"/steamidra*.AppImage; do
        [ -f "$f" ] && echo "appimage" && return 0
    done
    # Binary: SteaMidra or SteaMidra.bin onefile next to the script
    if [ -f "$SCRIPT_DIR/SteaMidra" ] || [ -f "$SCRIPT_DIR/SteaMidra.bin" ]; then
        echo "binary" && return 0
    fi
    # Source: Main.py next to the script
    if [ -f "$SCRIPT_DIR/Main.py" ]; then
        echo "source" && return 0
    fi
    echo "unknown"
}

# ── Cleanup old install ───────────────────────────────────────────────────────
cleanup_existing() {
    log_info "Cleaning up existing installation..."
    rm -f "$INSTALL_DIR/SteaMidra.AppImage" 2>/dev/null || true
    rm -f "$INSTALL_DIR/SteaMidra"          2>/dev/null || true
    rm -f "$INSTALL_DIR/SteaMidra.bin"      2>/dev/null || true
    rm -f "$INSTALL_DIR/run.sh"             2>/dev/null || true
    # Remove old source tree but keep .venv and settings
    rm -rf "$INSTALL_DIR/sff"               2>/dev/null || true
    rm -rf "$INSTALL_DIR/static"            2>/dev/null || true
    rm -rf "$INSTALL_DIR/third_party"       2>/dev/null || true
    rm -f  "$INSTALL_DIR/Main.py"           2>/dev/null || true
    rm -f  "$INSTALL_DIR/Main_gui.py"       2>/dev/null || true
}

# ── Icon + desktop entry ──────────────────────────────────────────────────────
install_desktop_entry() {
    local exec_path="$1"
    local terminal="${2:-false}"

    # Copy icon to hicolor theme dir so Icon=SteaMidra resolves everywhere
    mkdir -p "$ICON_THEME_DIR"
    local icon_src=""
    # Try to find the icon: shipped alongside the script, or extract from AppImage
    for candidate in \
        "$SCRIPT_DIR/SteaMidra.png" \
        "$SCRIPT_DIR/SFF.png" \
        "$INSTALL_DIR/SFF.png" \
        "$INSTALL_DIR/SteaMidra.png"; do
        if [ -f "$candidate" ]; then
            icon_src="$candidate"
            break
        fi
    done

    if [ -n "$icon_src" ]; then
        cp -f "$icon_src" "$ICON_THEME_DIR/SteaMidra.png"
        # Refresh icon cache — skip on KDE (gtk-update-icon-cache hangs there)
        if [ -z "${XDG_CURRENT_DESKTOP:-}" ] || [[ "${XDG_CURRENT_DESKTOP:-}" != *"KDE"* ]]; then
            command -v gtk-update-icon-cache  &>/dev/null && gtk-update-icon-cache  "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
            command -v gtk4-update-icon-cache &>/dev/null && gtk4-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
        fi
    else
        log_warn "No icon file found — app launcher will have no icon."
    fi

    # Create desktop entry
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/steamidra.desktop" <<EOF
[Desktop Entry]
Version=1.0
Name=SteaMidra
Comment=Steam game setup and manifest tool
Exec=$exec_path
Icon=SteaMidra
Terminal=$terminal
Type=Application
Categories=Utility;
StartupNotify=false
EOF

    # Refresh desktop database so the entry appears immediately
    command -v update-desktop-database &>/dev/null && \
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    log_info "Desktop entry installed."
}

# ── Launcher wrapper ──────────────────────────────────────────────────────────
create_launcher_script() {
    local target="$1"
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/steamidra" <<EOF
#!/usr/bin/env bash
export QTWEBENGINE_DISABLE_SANDBOX=1
exec "$target" "\$@"
EOF
    chmod +x "$BIN_DIR/steamidra"
    log_info "Launcher created at $BIN_DIR/steamidra"
}

# ── .NET 9 runtime (needed for DepotDownloaderMod) ───────────────────────────
install_dotnet9() {
    if command -v dotnet &>/dev/null && dotnet --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 9\."; then
        log_info ".NET 9 already installed."
        return 0
    fi
    if [ -f "$HOME/.dotnet/dotnet" ] && "$HOME/.dotnet/dotnet" --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 9\."; then
        log_info ".NET 9 already installed at ~/.dotnet."
        return 0
    fi
    log_info "Installing .NET 9 runtime (needed for game downloads)..."
    local TMP
    TMP="$(mktemp)"
    curl -sSL https://dot.net/v1/dotnet-install.sh -o "$TMP"
    chmod +x "$TMP"
    DOTNET_ROOT="$HOME/.dotnet" bash "$TMP" --channel 9.0 --runtime dotnet
    rm -f "$TMP"
    if "$HOME/.dotnet/dotnet" --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 9\."; then
        log_info ".NET 9 installed successfully."
        for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
            [ -f "$rc" ] || continue
            grep -q 'DOTNET_ROOT' "$rc" 2>/dev/null && continue
            echo 'export DOTNET_ROOT="$HOME/.dotnet"' >> "$rc"
            echo 'export PATH="$PATH:$HOME/.dotnet"'  >> "$rc"
        done
    else
        log_error ".NET 9 installation failed. Install manually:"
        log_error "  curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 9.0 --runtime dotnet"
    fi
}

# ── venv helper ───────────────────────────────────────────────────────────────
setup_venv() {
    local dir="$1"
    if [ "${SKIPVENV:-}" = "1" ] && [ -f "$dir/.venv/bin/activate" ]; then
        log_info "Skipping venv setup (SKIPVENV=1 and .venv exists)."
        return 0
    fi
    log_info "Setting up Python virtual environment..."
    python3 -m venv "$dir/.venv"
    if [ -f "$dir/requirements-linux.txt" ]; then
        "$dir/.venv/bin/pip" install --quiet -r "$dir/requirements-linux.txt"
    elif [ -f "$dir/requirements.txt" ]; then
        "$dir/.venv/bin/pip" install --quiet -r "$dir/requirements.txt"
    fi
}

# ── Install: AppImage ─────────────────────────────────────────────────────────
install_appimage() {
    local src=""
    for f in "$SCRIPT_DIR"/SteaMidra*.AppImage "$SCRIPT_DIR"/steamidra*.AppImage; do
        [ -f "$f" ] && src="$f" && break
    done
    [ -z "$src" ] && log_error "No AppImage found in $SCRIPT_DIR" && exit 1

    log_info "Installing AppImage: $(basename "$src")"
    mkdir -p "$INSTALL_DIR"
    local dest="$INSTALL_DIR/SteaMidra.AppImage"
    [ "$src" != "$dest" ] && cp -f "$src" "$dest"
    chmod +x "$dest"

    # Extract icon from AppImage if not shipped separately
    if [ ! -f "$SCRIPT_DIR/SteaMidra.png" ] && [ ! -f "$SCRIPT_DIR/SFF.png" ]; then
        set +e
        APPIMAGE_EXTRACT_AND_RUN=1 "$dest" --appimage-extract squashfs-root/SteaMidra.png 2>/dev/null && \
            cp -f squashfs-root/SteaMidra.png "$SCRIPT_DIR/SteaMidra.png" 2>/dev/null && \
            rm -rf squashfs-root
        set -e
    fi

    create_launcher_script "$dest"
    install_desktop_entry  "$dest" "false"
    log_info "SteaMidra AppImage installed to $INSTALL_DIR"
}

# ── Install: binary ───────────────────────────────────────────────────────────
install_binary() {
    local src=""
    [ -f "$SCRIPT_DIR/SteaMidra"     ] && src="$SCRIPT_DIR/SteaMidra"
    [ -f "$SCRIPT_DIR/SteaMidra.bin" ] && src="$SCRIPT_DIR/SteaMidra.bin"
    [ -z "$src" ] && log_error "No SteaMidra binary found in $SCRIPT_DIR" && exit 1

    log_info "Installing binary: $(basename "$src")"
    mkdir -p "$INSTALL_DIR"
    cp -f "$src" "$INSTALL_DIR/SteaMidra"
    chmod +x "$INSTALL_DIR/SteaMidra"

    create_launcher_script "$INSTALL_DIR/SteaMidra"
    install_desktop_entry  "$INSTALL_DIR/SteaMidra" "true"
    log_info "SteaMidra binary installed to $INSTALL_DIR"
}

# ── Install: source ───────────────────────────────────────────────────────────
install_source() {
    if ! command -v python3 &>/dev/null; then
        log_error "python3 not found. Please install Python 3.10+."
        exit 1
    fi

    log_info "Installing from source: $SCRIPT_DIR"
    mkdir -p "$INSTALL_DIR"
    [ "$SCRIPT_DIR" != "$INSTALL_DIR" ] && cp -r "$SCRIPT_DIR/." "$INSTALL_DIR/"

    setup_venv "$INSTALL_DIR"

    cat > "$INSTALL_DIR/run.sh" <<RUNEOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/Main.py" "\$@"
RUNEOF
    chmod +x "$INSTALL_DIR/run.sh"

    create_launcher_script "$INSTALL_DIR/run.sh"
    install_desktop_entry  "$INSTALL_DIR/run.sh" "true"
    log_info "SteaMidra source install complete."
}

# ── Post-install message ──────────────────────────────────────────────────────
installed_message() {
    log_info "SteaMidra installed to $INSTALL_DIR"
    log_info "Run: steamidra   or launch from your application menu."
    if ! echo "$PATH" | grep -q "$BIN_DIR"; then
        log_warn "Add $BIN_DIR to your PATH to use 'steamidra' from any terminal."
        log_warn "  echo 'export PATH=\"\$PATH:$BIN_DIR\"' >> ~/.bashrc && source ~/.bashrc"
    fi
    # Deferred desktop notification (after shell returns)
    (
        sleep 3
        set +eu
        if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
            notify-send -t 8000 "SteaMidra installed" \
                "Installed to $INSTALL_DIR — launch from your application menu." 2>/dev/null
        fi
    ) &
    disown
}

# ── Uninstall ─────────────────────────────────────────────────────────────────
do_uninstall() {
    log_info "Uninstalling SteaMidra..."
    rm -rf "$INSTALL_DIR"
    rm -f  "$BIN_DIR/steamidra"
    rm -f  "$DESKTOP_DIR/steamidra.desktop"
    rm -f  "$ICON_THEME_DIR/SteaMidra.png"
    command -v update-desktop-database &>/dev/null && \
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    log_info "SteaMidra uninstalled."
}

# ── Main ──────────────────────────────────────────────────────────────────────
case "${1:-install}" in
    install)
        INSTALL_TYPE="$(detect_install_type)"
        log_info "Detected install type: $INSTALL_TYPE"
        cleanup_existing
        case "$INSTALL_TYPE" in
            appimage) install_appimage ;;
            binary)   install_binary   ;;
            source)   install_source   ;;
            unknown)
                log_error "No SteaMidra AppImage, binary, or Main.py found in $SCRIPT_DIR"
                log_error "Place steamidra_install.sh alongside SteaMidra.AppImage (or Main.py for source)."
                exit 1
                ;;
        esac
        install_dotnet9
        installed_message
        ;;
    uninstall) do_uninstall ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        exit 1
        ;;
esac
