# Defines spdlog::spdlog as a static library via FetchContent. Only intended
# to be used in Debug builds — Release callers should compile with the LOG_*
# macros stubbed out (see src/Log.h) and avoid linking against this target.
if(TARGET spdlog::spdlog)
    return()
endif()

include(FetchCache)
include(FetchContent)

# spdlog uses its bundled fmt by default — that's what we want here so we
# don't need a separate fmt fetch.
set(SPDLOG_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(SPDLOG_FMT_EXTERNAL OFF CACHE BOOL "" FORCE)
set(SPDLOG_BUILD_EXAMPLE OFF CACHE BOOL "" FORCE)
set(SPDLOG_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(SPDLOG_INSTALL OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
    spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG        v1.17.0
    GIT_SHALLOW    TRUE
    GIT_PROGRESS   TRUE
)
FetchContent_MakeAvailable(spdlog)
