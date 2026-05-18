#pragma once

// Searches the memory of a loaded DLL for a specific byte sequence and returns a pointer to the match.
// Write the pattern as space-separated hex pairs: "48 8B C4 4C 89 48 20 89 50 10 48 89 48 08 55 ?? 48 8D".
// Replace any byte you don't care about with ??, which matches any value at that position.

#include <windows.h>
#include <initializer_list>

struct Signature {
    const char* label;      // build identifier used for logging and preferred-match selection, e.g. "1778803745"
    const char* signature;  // hex pattern string, e.g. "48 8B C4 ?? 56 57 41 54 41 55"
    int matchIndex = 1;     // if the pattern appears more than once in the image, take the Nth occurrence (1-based)
};

// Searches the loaded DLL for each Signature entry, preferring the one whose label matches
// the running Steam build ID. Falls back through the remaining entries in order if the
// preferred one misses. Logs the result for every attempt when logging is enabled.
void* ByteSearch(HMODULE module, const char* funcName, std::initializer_list<Signature> sigs);

// Same search logic as above, but takes a raw pointer and count instead of an initializer_list.
// Use this with PatternDb.h arrays: ByteSearch(mod, "Foo", FooSigs, std::size(FooSigs)).
void* ByteSearch(HMODULE module, const char* funcName, const Signature* sigs, size_t count);

// Convenience macro that follows the naming convention used in PatternDb.h.
// FIND_SIG(module, LoadModuleWithPath) expands to:
//   ByteSearch(module, "LoadModuleWithPath", LoadModuleWithPathSigs, std::size(LoadModuleWithPathSigs))
// Every *Sigs array in PatternDb.h is named after the function it targets.
#define FIND_SIG(module, name) ByteSearch(module, #name, name##Sigs, std::size(name##Sigs))

// Overwrites nSize bytes at pAddress with the bytes from pNewBytes.
// Uses VirtualProtect to temporarily make the page writable (code pages are read+execute by default),
// copies the bytes, then calls FlushInstructionCache so the CPU discards any stale cached instructions.
// Returns 1 on success, 0 if VirtualProtect fails.
int PatchMemoryBytes(void* pAddress, const void* pNewBytes, SIZE_T nSize);
