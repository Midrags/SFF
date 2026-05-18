# Defines tomlplusplus::tomlplusplus as a header-only interface target via
# FetchContent. Idempotent.
if(TARGET tomlplusplus::tomlplusplus)
    return()
endif()

include(FetchCache)
include(FetchContent)

FetchContent_Declare(
    tomlplusplus
    GIT_REPOSITORY https://github.com/marzer/tomlplusplus.git
    GIT_TAG        v3.4.0
    GIT_SHALLOW    TRUE
    GIT_PROGRESS   TRUE
)
FetchContent_MakeAvailable(tomlplusplus)
