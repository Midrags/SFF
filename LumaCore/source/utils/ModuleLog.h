// Registry of per-module log channels for LumaCore.
//
// Each LC_MOD(VarName, "filename") line registers one module logger.
// The file is included twice with different definitions of LC_MOD:
//   - Logger.h uses it to declare a shared_ptr<spdlog::logger> for each module.
//   - Logger.cpp uses it to create the spdlog file sinks.
// cmake/LogMacros.cmake reads it a third time to generate the LOG_<MOD>_* macros
// that hook code uses (e.g. LOG_IPC_INFO, LOG_MANIFEST_WARN).
//
// To add a new module: add one LC_MOD line here, then re-run CMake so the
// macro header gets regenerated. No other files need to change.

LC_MOD(IPC,           "ipc")
LC_MOD(NetPacket,     "netpacket")
LC_MOD(Manifest,      "manifest")
LC_MOD(KeyValue,      "keyvalue")
LC_MOD(DecryptionKey, "decryptionkey")
LC_MOD(Misc,          "misc")
LC_MOD(Achievement,   "achievement")
LC_MOD(Pics,          "pics")
LC_MOD(OnlineFix,     "onlinefix")
LC_MOD(Package,       "package")
LC_MOD(License,       "license")
LC_MOD(SteamUI,       "steamui")
