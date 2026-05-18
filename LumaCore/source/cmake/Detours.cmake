# Defines a static `detours` target by fetching the upstream Microsoft/Detours
# sources. Idempotent — safe to include() from multiple CMakeLists.
if(TARGET detours)
    return()
endif()

include(FetchCache)
include(FetchContent)

FetchContent_Declare(
    detours
    GIT_REPOSITORY https://github.com/microsoft/Detours.git
    GIT_TAG        main
    GIT_SHALLOW    TRUE
    GIT_PROGRESS   TRUE
    # SOURCE_SUBDIR points at a directory with no CMakeLists.txt so that
    # FetchContent_MakeAvailable downloads the source but does NOT add the
    # repo's own (Make-based) build into our project.
    SOURCE_SUBDIR  cmake-noop
)
FetchContent_MakeAvailable(detours)

# Pick the architecture-specific disassembler source.
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    if(CMAKE_SYSTEM_PROCESSOR MATCHES "ARM|aarch64")
        set(DETOURS_ARCH_SRC "${detours_SOURCE_DIR}/src/disolarm64.cpp")
    else()
        set(DETOURS_ARCH_SRC "${detours_SOURCE_DIR}/src/disolx64.cpp")
    endif()
else()
    if(CMAKE_SYSTEM_PROCESSOR MATCHES "ARM|aarch64")
        set(DETOURS_ARCH_SRC "${detours_SOURCE_DIR}/src/disolarm.cpp")
    else()
        set(DETOURS_ARCH_SRC "${detours_SOURCE_DIR}/src/disolx86.cpp")
    endif()
endif()

add_library(detours STATIC
    ${detours_SOURCE_DIR}/src/detours.cpp
    ${detours_SOURCE_DIR}/src/modules.cpp
    ${detours_SOURCE_DIR}/src/disasm.cpp
    ${detours_SOURCE_DIR}/src/image.cpp
    ${detours_SOURCE_DIR}/src/creatwth.cpp
    ${DETOURS_ARCH_SRC}
)
target_include_directories(detours PUBLIC "${detours_SOURCE_DIR}/src")
set_target_properties(detours PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    target_compile_options(detours PRIVATE /w)
else()
    target_compile_options(detours PRIVATE -w)
endif()
