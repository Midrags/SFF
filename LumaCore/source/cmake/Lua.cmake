# Defines a static `lua_static` target by fetching the official Lua 5.5
# source release. Idempotent.
if(TARGET lua_static)
    return()
endif()

include(FetchCache)
include(FetchContent)

FetchContent_Declare(
    lua
    URL https://www.lua.org/ftp/lua-5.5.0.tar.gz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    TLS_VERIFY OFF
)
FetchContent_MakeAvailable(lua)

# The Lua tarball ships only Makefiles, so we build a static library here.
file(GLOB LUA_CORE_SOURCES "${lua_SOURCE_DIR}/src/*.c")
list(REMOVE_ITEM LUA_CORE_SOURCES
    "${lua_SOURCE_DIR}/src/lua.c"
    "${lua_SOURCE_DIR}/src/luac.c")

add_library(lua_static STATIC ${LUA_CORE_SOURCES})
target_include_directories(lua_static PUBLIC "${lua_SOURCE_DIR}/src")
set_target_properties(lua_static PROPERTIES POSITION_INDEPENDENT_CODE ON)
