cmake_minimum_required(VERSION 3.20)
project(LumaCore VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)

# Allow CMAKE_MSVC_RUNTIME_LIBRARY to control runtime selection for all targets,
# including dependencies pulled in via FetchContent.
if(POLICY CMP0091)
    cmake_policy(SET CMP0091 NEW)
endif()

# Static MSVC runtime everywhere, so the resulting DLL has no extra runtime
# dependencies. Must be set BEFORE FetchContent_MakeAvailable so the fetched
# deps (Lua, Detours, spdlog) inherit it.
set(CMAKE_CONFIGURATION_TYPES "Debug;Release" CACHE STRING "" FORCE)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)

# ---------------------------------------------------------------------------
# Dependency recipes (FetchContent-backed, cached at <repo>/.deps).
# ---------------------------------------------------------------------------
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(Lua)
include(Detours)
include(Spdlog)
include(Protobuf)
include(Tomlplusplus)
include(LogMacros)

# ---------------------------------------------------------------------------
# Protobuf code generation — two variants from the same .proto:
#
#   Debug  → full Message  (protoc --cpp_out)         → links libprotobuf
#   Release → lite MessageLite (protoc --cpp_out=lite) → links libprotobuf-lite
#
# Both land in separate subdirectories of the build tree so the source
# directory stays clean and the right set is picked per configuration.
# ---------------------------------------------------------------------------
set(PROTO_SRC "${CMAKE_CURRENT_SOURCE_DIR}/proto/steam_messages.proto")
set(PROTO_GEN_DIR       "${CMAKE_CURRENT_BINARY_DIR}/proto")
set(PROTO_GEN_LITE_DIR  "${CMAKE_CURRENT_BINARY_DIR}/proto_lite")

# Full Message (Debug)
add_custom_command(
    OUTPUT "${PROTO_GEN_DIR}/steam_messages.pb.cc"
           "${PROTO_GEN_DIR}/steam_messages.pb.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${PROTO_GEN_DIR}"
    COMMAND $<TARGET_FILE:protoc>
        "--cpp_out=${PROTO_GEN_DIR}"
        "-I${CMAKE_CURRENT_SOURCE_DIR}/proto"
        "${PROTO_SRC}"
    DEPENDS "${PROTO_SRC}" protoc
    COMMENT "Generating protobuf full-Message sources (Debug)"
)

# Lite MessageLite (Release)
add_custom_command(
    OUTPUT "${PROTO_GEN_LITE_DIR}/steam_messages.pb.cc"
           "${PROTO_GEN_LITE_DIR}/steam_messages.pb.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${PROTO_GEN_LITE_DIR}"
    COMMAND $<TARGET_FILE:protoc>
        "--cpp_out=lite:${PROTO_GEN_LITE_DIR}"
        "-I${CMAKE_CURRENT_SOURCE_DIR}/proto"
        "${PROTO_SRC}"
    DEPENDS "${PROTO_SRC}" protoc
    COMMENT "Generating protobuf lite-MessageLite sources (Release)"
)

# ---------------------------------------------------------------------------
# LumaCore — the hook DLL injected into Steam (always 64-bit).
# ---------------------------------------------------------------------------
add_library(LumaCore SHARED
    entry.cpp

    # Shared utilities
    utils/Ticket.cpp
    utils/ByteScan.cpp
    utils/Logger.cpp
    utils/Settings.cpp
    utils/LuaLoader.cpp
    utils/VehUtil.cpp
    utils/DirWatch.cpp

    # Per-category hook modules
    hooks/CoreLoader.cpp
    hooks/DepotKeys.cpp
    hooks/IPCBus.cpp
    hooks/CmdUser.cpp
    hooks/CmdUtils.cpp
    # hooks/KeyValues.cpp  # disabled: KeyValues::Install() not called
    hooks/ManifestBind.cpp
    hooks/RuntimeCapture.cpp
    hooks/PacketRouter.cpp
    hooks/SteamUI.cpp
    hooks/PackagePatch.cpp
    hooks/RichPresence.cpp
    hooks/LicenseHooks.cpp
    hooks/StringFind.cpp

    # protobuf generated sources — per-config variant
    $<$<CONFIG:Debug>:${PROTO_GEN_DIR}/steam_messages.pb.cc>
    $<$<CONFIG:Release>:${PROTO_GEN_LITE_DIR}/steam_messages.pb.cc>
)

# Header search path — per-config include directory
target_include_directories(LumaCore PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_BINARY_DIR}/generated
    $<$<CONFIG:Debug>:${PROTO_GEN_DIR}>
    $<$<CONFIG:Release>:${PROTO_GEN_LITE_DIR}>
)

target_link_libraries(LumaCore PRIVATE
    lua_static
    detours
    $<$<CONFIG:Debug>:libprotobuf>
    $<$<CONFIG:Release>:libprotobuf-lite>
    tomlplusplus::tomlplusplus
    $<$<CONFIG:Debug>:spdlog::spdlog>
)

# Logging is compiled in only for Debug; Release reduces LOG_* to no-ops.
target_compile_definitions(LumaCore PRIVATE
    $<$<CONFIG:Debug>:LUMACORE_LOGGING_ENABLED>
)

# ---------------------------------------------------------------------------
# dwmapi.dll hijack — small loader DLL placed alongside Steam.
# ---------------------------------------------------------------------------
add_library(dwmapi SHARED
    proxy/dwmapi.cpp
)
