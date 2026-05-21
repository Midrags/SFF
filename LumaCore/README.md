# LumaCore

LumaCore is the DLL component that SteaMidra injects into Steam to handle family-sharing bypass, depot key loading, achievement spoofing, and legacy CD-key suppression.

It ships as two files placed in the Steam installation directory:

- `dwmapi.dll` — thin proxy that Steam loads on startup; immediately loads LumaCore.dll
- `LumaCore.dll` — the main hook library

## How it works

At Steam startup, `dwmapi.dll` runs before any game code and loads `LumaCore.dll`.  LumaCore then:

1. Copies `steamclient64.dll` to `bin\lcoverlay.dll` so it can be loaded and hooked independently of the live client.
2. Reads the current Steam build ID from `steam.exe!GetBootstrapperVersion` so byte-pattern searches pick the most accurate signature for the running build.
3. Installs a set of Detours hooks into the loaded `lcoverlay.dll` copy.
4. Starts a Lua directory watcher that monitors `config/stplug-in/` for `.lua` files written by SteaMidra.

When a Lua file appears or changes, LumaCore parses it, loads depot decryption keys and ownership records, and calls `SteamCapture::NotifyLicenseChanged` to inject the new ownership data into Steam without restarting.

## Features

See [docs/LumaCore.md](docs/LumaCore.md) for a full description of every hook and feature.

## Building

Requirements: CMake 3.20+, MSVC (Visual Studio 2022), 64-bit target only.

```bat
build.bat
```

The build script downloads all dependencies (Lua 5.4, Microsoft Detours, spdlog, protobuf, toml++) via CMake FetchContent on the first run.  Subsequent runs are incremental.  Output DLLs are copied to `Releases/Release/` and `Releases/Debug/` beside `build.bat`.

## Credits

See [CREDITS.md](CREDITS.md).

## License

LumaCore is part of SteaMidra and is distributed under the GNU General Public License v3.  See the root `LICENSE` file for the full text.
