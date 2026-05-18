#pragma once

#include <windows.h>

// Describes one string cross-reference search target.
// Steam functions often reference unique string literals (error messages, names)
// that stay stable across builds even when the surrounding byte pattern changes.
// Use this to locate a function by the string it references rather than its bytes.
struct StringXRefSig {
    const char* label;     // identifier for logging, e.g. "1778803745" or "v1"
    const char* str;       // the exact null-terminated string the target function contains a LEA to
    int         occurrence; // 1-based: if multiple functions reference the same string, pick the Nth one
};

namespace StringFind {
    // Finds a function by tracing which code references a known string literal.
    // Step 1: scans all non-executable sections (e.g. .rdata) for every address
    //         that holds the exact bytes of targetStr followed by a null terminator.
    // Step 2: scans the first executable section (.text) for RIP-relative LEA instructions
    //         (opcode pattern: REX 8D [mod=00 r/m=101] disp32) whose computed target
    //         address matches one of the string addresses found in step 1.
    //         The `occurrence` parameter selects which LEA hit to use (1 = first, 2 = second, ...).
    // Step 3: looks up the instruction's offset in the .pdata exception directory (binary search
    //         on RUNTIME_FUNCTION BeginAddress), which gives the start of the enclosing function.
    // Returns nullptr if the string is not found, no LEA references it, or .pdata has no entry.
    void* FindFunction(HMODULE hMod, const char* targetStr, int occurrence = 1);
}
