#!/usr/bin/env bash
# SteaMidra Linux Install Script
# Usage: bash steamidra_install.sh [install|uninstall]

set -euo pipefail

APP_NAME="SteaMidra"
INSTALL_DIR="$HOME/.local/share/SteaMidra"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
_yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
_red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
_info()   { printf '[SteaMidra] %s\n' "$*"; }

detect_appimage() {
    for f in "$SCRIPT_DIR"/SteaMidra*.AppImage "$SCRIPT_DIR"/steamidra*.AppImage; do
        [ -f "$f" ] && echo "$f" && return 0
    done
    return 1
}

detect_source() {
    [ -f "$SCRIPT_DIR/Main.py" ] && echo "$SCRIPT_DIR" && return 0
    return 1
}

install_dotnet9() {
    if command -v dotnet &>/dev/null && dotnet --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 9\."; then
        _green ".NET 9 already installed."
        return 0
    fi
    if [ -f "$HOME/.dotnet/dotnet" ] && "$HOME/.dotnet/dotnet" --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 9\."; then
        _green ".NET 9 already installed at ~/.dotnet."
        return 0
    fi
    _info "Installing .NET 9 runtime..."
    local TMP
    TMP="$(mktemp)"
    curl -sSL https://dot.net/v1/dotnet-install.sh -o "$TMP"
    chmod +x "$TMP"
    DOTNET_ROOT="$HOME/.dotnet" bash "$TMP" --channel 9.0 --runtime dotnet
    rm -f "$TMP"
    if "$HOME/.dotnet/dotnet" --list-runtimes 2>/dev/null | grep -q "Microsoft.NETCore.App 9\."; then
        _green ".NET 9 installed successfully."
        if ! grep -q 'DOTNET_ROOT' "$HOME/.bashrc" 2>/dev/null; then
            echo 'export DOTNET_ROOT="$HOME/.dotnet"' >> "$HOME/.bashrc"
            echo 'export PATH="$PATH:$HOME/.dotnet"' >> "$HOME/.bashrc"
        fi
        if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
            if ! grep -q 'DOTNET_ROOT' "$HOME/.zshrc" 2>/dev/null; then
                echo 'export DOTNET_ROOT="$HOME/.dotnet"' >> "$HOME/.zshrc"
                echo 'export PATH="$PATH:$HOME/.dotnet"' >> "$HOME/.zshrc"
            fi
        fi
    else
        _red ".NET 9 installation failed. Install manually: curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 9.0 --runtime dotnet"
    fi
}

create_desktop_entry() {
    local exec_cmd="$1"
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/steamidra.desktop" <<EOF
[Desktop Entry]
Name=SteaMidra
Comment=Steam game setup and manifest tool
Exec=$exec_cmd
Terminal=true
Type=Application
Categories=Utility;
StartupNotify=false
EOF
    _green "Desktop entry created."
}

create_launcher_script() {
    local target="$1"
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/steamidra" <<EOF
#!/usr/bin/env bash
exec "$target" "\$@"
EOF
    chmod +x "$BIN_DIR/steamidra"
    _green "Launcher created at $BIN_DIR/steamidra"
}

do_install() {
    _info "Starting SteaMidra installation..."
    mkdir -p "$INSTALL_DIR"

    local appimage
    local source_dir

    if appimage="$(detect_appimage 2>/dev/null)"; then
        _info "AppImage detected: $appimage"
        chmod +x "$appimage"
        local dest="$INSTALL_DIR/SteaMidra.AppImage"
        if [ "$appimage" != "$dest" ]; then
            cp -f "$appimage" "$dest"
        fi
        create_launcher_script "$dest"
        create_desktop_entry "$dest"
        _green "SteaMidra AppImage installed."

    elif source_dir="$(detect_source 2>/dev/null)"; then
        _info "Source install detected: $source_dir"
        if [ "$source_dir" != "$INSTALL_DIR" ]; then
            cp -r "$source_dir/." "$INSTALL_DIR/"
        fi

        _info "Setting up Python virtual environment..."
        python3 -m venv "$INSTALL_DIR/.venv"
        if [ -f "$INSTALL_DIR/requirements.txt" ]; then
            "$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
        fi

        cat > "$INSTALL_DIR/run.sh" <<RUNEOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/Main.py" "\$@"
RUNEOF
        chmod +x "$INSTALL_DIR/run.sh"

        create_launcher_script "$INSTALL_DIR/run.sh"
        create_desktop_entry "$INSTALL_DIR/run.sh"
        _green "SteaMidra source install complete."
    else
        _red "No SteaMidra.AppImage or Main.py found in $SCRIPT_DIR"
        _red "Place steamidra_install.sh in the same folder as SteaMidra.AppImage"
        exit 1
    fi

    _info "Installing .NET 9 runtime (needed for game downloads)..."
    install_dotnet9

    if ! echo "$PATH" | grep -q "$BIN_DIR"; then
        _yellow "Note: Add $BIN_DIR to your PATH to use 'steamidra' command."
        _yellow "  Add to ~/.bashrc: export PATH=\"\$PATH:$BIN_DIR\""
    fi

    _green ""
    _green "Installation complete! Run: steamidra"
    _green "Or open SteaMidra from your application menu."
}

do_uninstall() {
    _info "Uninstalling SteaMidra..."
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_DIR/steamidra"
    rm -f "$DESKTOP_DIR/steamidra.desktop"
    _green "SteaMidra uninstalled."
}

case "${1:-install}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        exit 1
        ;;
esac
