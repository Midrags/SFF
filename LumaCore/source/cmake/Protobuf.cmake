# Fetches protobuf v3.15.3, builds both libprotobuf (full, Debug) and
# libprotobuf-lite (Release), plus libprotoc + protoc for code generation.
#
# Pinned to v3.15.3 to match Steam's runtime protobuf ABI exactly.
# Steam uses protobuf ~3.15.x (confirmed by vtable slot analysis).
# Using a newer version causes vtable slot mismatches when Steam calls
# virtual methods on CAppOverview_Change objects, leading to crashes.
#
# Debug  → links libprotobuf      (heavier, DebugString works)
# Release → links libprotobuf-lite (lightweight)

if(TARGET libprotobuf AND TARGET libprotobuf-lite)
    return()
endif()

include(FetchCache)
include(FetchContent)

set(protobuf_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_CONFORMANCE OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(protobuf_WITH_ZLIB OFF CACHE BOOL "" FORCE)
set(protobuf_MSVC_STATIC_RUNTIME ON CACHE BOOL "" FORCE)
set(protobuf_BUILD_LIBPROTOBUF ON CACHE BOOL "" FORCE)
set(protobuf_BUILD_PROTOC_BINARIES ON CACHE BOOL "" FORCE)

FetchContent_Declare(
    protobuf
    GIT_REPOSITORY https://github.com/protocolbuffers/protobuf.git
    GIT_TAG        v3.15.3
    GIT_SHALLOW    TRUE
    GIT_PROGRESS   TRUE
    SOURCE_SUBDIR  cmake
)

set(_saved_CMAKE_WARN_DEPRECATED ${CMAKE_WARN_DEPRECATED})
set(CMAKE_WARN_DEPRECATED OFF CACHE BOOL "" FORCE)
# Opt back in to pre-3.5 policies for protobuf 3.15.
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "" FORCE)
FetchContent_MakeAvailable(protobuf)
set(CMAKE_WARN_DEPRECATED ${_saved_CMAKE_WARN_DEPRECATED} CACHE BOOL "" FORCE)

# Silence warnings in protobuf source.
foreach(_t IN ITEMS libprotobuf libprotobuf-lite libprotoc)
    if(TARGET ${_t})
        if(MSVC)
            target_compile_options(${_t} PRIVATE /w)
        else()
            target_compile_options(${_t} PRIVATE -w)
        endif()
        target_compile_definitions(${_t} PRIVATE _CRT_SECURE_NO_WARNINGS)
    endif()
endforeach()
