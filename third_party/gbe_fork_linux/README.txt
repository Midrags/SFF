Goldberg Emulator Fork — Linux native files (offline fallback)
==============================================================

SteaMidra downloads these files automatically at runtime from:
  https://github.com/Detanup01/gbe_fork/releases/latest
  Asset: emu-linux-release.tar.bz2

This folder is only used as an OFFLINE FALLBACK if the download fails.
To use it, extract emu-linux-release.tar.bz2 here manually.

Required files (from release/ inside the archive):
  libsteam_api.so       — 64-bit Goldberg steam_api replacement
  libsteam_api32.so     — 32-bit Goldberg steam_api replacement

Optional tools (from release/tools/ inside the archive):
  generate_interfaces_x64 — generates steam_interfaces.txt from .so

NOTE: third_party/gbe_fork/ holds the WINDOWS DLLs (.dll files).
      This folder holds LINUX .so files ONLY.
