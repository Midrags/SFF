#pragma once

// Hook plumbing macros for LumaCore. Wraps Microsoft Detours for attaching/detaching
// function hooks inside loaded DLL modules.
// _D variants target diversion_hModule (the hooked copy of steamclient64.dll).
// All others take an explicit HMODULE to target steamui.dll or any other loaded image.

#include <windows.h>
#include <detours.h>
#include "utils/ByteScan.h"
#include "PatternDb.h"
#include "StringFind.h"

// Open a Detours transaction. DetourTransactionBegin starts the batch;
// DetourUpdateThread registers the calling thread so Detours adjusts its
// instruction pointer past any trampolines before Commit fires.
// Always pair with LC_TX_COMMIT.
#define LC_TX_OPEN()                          \
    do {                                       \
        DetourTransactionBegin();              \
        DetourUpdateThread(GetCurrentThread())

// Close and apply the open Detours transaction atomically.
#define LC_TX_COMMIT()                        \
        DetourTransactionCommit();             \
    } while (0)

// Declare a hooked function and its original-pointer trampoline.
// Expands to:
//   1. A function-pointer typedef:   typedef HMODULE(__fastcall* LoadModuleWithPath_t)(const char*, bool);
//   2. The trampoline pointer:        inline LoadModuleWithPath_t oLoadModuleWithPath = nullptr;
//   3. The hook function signature:   HMODULE __fastcall hkLoadModuleWithPath(const char* path, bool flags)
// Write the hook body in braces immediately after. Call o<name>(...) to invoke the original.
#define LC_HOOK_DEF(name, ret, ...)                           \
    typedef ret(__fastcall* name##_t)(__VA_ARGS__);            \
    inline name##_t o##name = nullptr;                          \
    ret __fastcall hk##name(__VA_ARGS__)

// Locate the target via FIND_SIG, store the original in o<name>, redirect to hk<name>.
// Silently skips if the pattern is not found. Call inside LC_TX_OPEN / LC_TX_COMMIT.
#define LC_ATTACH(module, name)                                       \
    do {                                                              \
        void* _p_ = FIND_SIG(module, name);                            \
        if (_p_) {                                                    \
            o##name = (name##_t)_p_;                                  \
            DetourAttach(reinterpret_cast<PVOID*>(&o##name),           \
                         reinterpret_cast<PVOID>(hk##name));           \
        }                                                             \
    } while (0)

#define LC_ATTACH_D(name)            LC_ATTACH(diversion_hModule, name)

// Like LC_ATTACH but accepts an explicit signature array instead of using the
// PatternDb.h naming convention. Use when the array name differs from the function name.
#define LC_ATTACH_EX(module, name, sigs)                              \
    do {                                                              \
        void* _p_ = ByteSearch(module, #name, sigs, std::size(sigs));  \
        if (_p_) {                                                    \
            o##name = (name##_t)_p_;                                  \
            DetourAttach(reinterpret_cast<PVOID*>(&o##name),           \
                         reinterpret_cast<PVOID>(hk##name));           \
        }                                                             \
    } while (0)

#define LC_ATTACH_EX_D(name, sigs)     LC_ATTACH_EX(diversion_hModule, name, sigs)

// Attach via string XRef only. Use when no reliable byte pattern exists.
#define LC_ATTACH_STR_ONLY_D(name, strSigs)                                   \
    do {                                                                       \
        void* _p_ = nullptr;                                                   \
        for (const auto& _s_ : (strSigs)) {                                    \
            _p_ = StringFind::FindFunction(diversion_hModule,                  \
                                           _s_.str, _s_.occurrence);            \
            if (_p_) break;                                                    \
        }                                                                      \
        if (_p_) {                                                             \
            o##name = (name##_t)_p_;                                           \
            DetourAttach(reinterpret_cast<PVOID*>(&o##name),                   \
                         reinterpret_cast<PVOID>(hk##name));                   \
        }                                                                      \
    } while (0)

// Two-stage attach: string cross-reference first (robust across builds),
// byte-pattern fallback if no string hit. strSigs = StringXRefSig list; byteSigs = Signature array.
#define LC_ATTACH_STR_D(name, strSigs, byteSigs)                              \
    do {                                                                       \
        void* _p_ = nullptr;                                                   \
        for (const auto& _s_ : (strSigs)) {                                    \
            _p_ = StringFind::FindFunction(diversion_hModule,                  \
                                           _s_.str, _s_.occurrence);            \
            if (_p_) break;                                                    \
        }                                                                      \
        if (!_p_) _p_ = ByteSearch(diversion_hModule, #name,                  \
                                    (byteSigs), std::size((byteSigs)));         \
        if (_p_) {                                                             \
            o##name = (name##_t)_p_;                                           \
            DetourAttach(reinterpret_cast<PVOID*>(&o##name),                   \
                         reinterpret_cast<PVOID>(hk##name));                   \
        }                                                                      \
    } while (0)

// Resolve a function address into o<name> without hooking it.
// Use to call internal Steam functions directly. No Detours transaction needed.
#define LC_RESOLVE(module, name) \
    o##name = reinterpret_cast<name##_t>(FIND_SIG(module, name))

#define LC_RESOLVE_D(name)       LC_RESOLVE(diversion_hModule, name)

#define LC_RESOLVE_EX(module, name, sigs) \
    o##name = reinterpret_cast<name##_t>(ByteSearch(module, #name, sigs, std::size(sigs)))

#define LC_RESOLVE_EX_D(name, sigs)  LC_RESOLVE_EX(diversion_hModule, name, sigs)

// Two-stage resolve: string XRef first, byte-pattern fallback.
#define LC_RESOLVE_STR_D(name, strSigs, byteSigs)                              \
    do {                                                                        \
        void* _p_ = nullptr;                                                    \
        for (const auto& _s_ : (strSigs)) {                                     \
            _p_ = StringFind::FindFunction(diversion_hModule,                   \
                                           _s_.str, _s_.occurrence);             \
            if (_p_) break;                                                     \
        }                                                                       \
        if (!_p_) _p_ = ByteSearch(diversion_hModule, #name,                   \
                                    (byteSigs), std::size((byteSigs)));          \
        o##name = reinterpret_cast<name##_t>(_p_);                              \
    } while (0)

// Remove a Detours hook and clear the trampoline pointer to nullptr.
// Safe to call even if the hook was never installed (pattern miss at startup).
// Call inside LC_TX_OPEN / LC_TX_COMMIT.
#define LC_DETACH(name)                                               \
    do {                                                              \
        if (o##name) {                                                \
            DetourDetach(reinterpret_cast<PVOID*>(&o##name),           \
                         reinterpret_cast<PVOID>(hk##name));           \
            o##name = nullptr;                                        \
        }                                                             \
    } while (0)
