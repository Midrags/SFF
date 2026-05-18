#pragma once

// Macros for installing, resolving, and removing Detours hooks in loaded DLL modules.
// The _D variants operate on diversion_hModule (the hooked copy of steamclient64.dll).
// All other variants take an explicit HMODULE so you can target steamui.dll or any other module.

#include <windows.h>
#include <detours.h>
#include "utils/ByteScan.h"
#include "PatternDb.h"
#include "StringFind.h"

// Detours requires you to wrap hook installations and removals in a transaction.
// DetourTransactionBegin() opens the batch. DetourUpdateThread() registers the calling
// thread so Detours can adjust its instruction pointer past any trampolines it creates
// (this prevents the thread from jumping into patched bytes mid-trampoline after Commit).
// DetourTransactionCommit() applies all pending hook changes atomically.
#define HOOK_BEGIN()                          \
    do {                                       \
        DetourTransactionBegin();              \
        DetourUpdateThread(GetCurrentThread())

#define HOOK_END()                            \
        DetourTransactionCommit();             \
    } while (0)

#define UNHOOK_BEGIN()                        \
    do {                                       \
        DetourTransactionBegin();              \
        DetourUpdateThread(GetCurrentThread())

#define UNHOOK_END()                          \
        DetourTransactionCommit();             \
    } while (0)

// Declares a hooked function and the pointer used to call the original.
// One macro expands to three things:
//   1. A function-pointer type alias:  using LoadModuleWithPath_t = HMODULE(__fastcall*)(const char*, bool);
//   2. The original-function pointer:  inline LoadModuleWithPath_t oLoadModuleWithPath = nullptr;
//   3. The hook function signature:    HMODULE __fastcall hkLoadModuleWithPath(const char* path, bool f)
// Write the hook body in braces immediately after the macro.
// Call oLoadModuleWithPath(...) inside the body to invoke the real function.
#define HOOK_FUNC(name, ret, ...)                         \
    using name##_t = ret(__fastcall*)(__VA_ARGS__);        \
    inline name##_t o##name = nullptr;                      \
    ret __fastcall hk##name(__VA_ARGS__)

// Finds the target function by scanning module for its byte pattern (via FIND_SIG),
// stores the original address in o<name>, and tells Detours to redirect calls to hk<name>.
// If the pattern is not found, the hook is silently skipped. Call between HOOK_BEGIN/HOOK_END.
#define INSTALL_HOOK(module, name)                                    \
    do {                                                              \
        void* _p_ = FIND_SIG(module, name);                            \
        if (_p_) {                                                    \
            o##name = (name##_t)_p_;                                  \
            DetourAttach(reinterpret_cast<PVOID*>(&o##name),           \
                         reinterpret_cast<PVOID>(hk##name));           \
        }                                                             \
    } while (0)

#define INSTALL_HOOK_D(name)            INSTALL_HOOK(diversion_hModule, name)

// Same as INSTALL_HOOK but takes an explicit signature array instead of following
// the PatternDb.h naming convention. Use when the array name differs from the function name.
#define INSTALL_HOOK_EX(module, name, sigs)                           \
    do {                                                              \
        void* _p_ = ByteSearch(module, #name, sigs, std::size(sigs));  \
        if (_p_) {                                                    \
            o##name = (name##_t)_p_;                                  \
            DetourAttach(reinterpret_cast<PVOID*>(&o##name),           \
                         reinterpret_cast<PVOID>(hk##name));           \
        }                                                             \
    } while (0)

#define INSTALL_HOOK_EX_D(name, sigs)     INSTALL_HOOK_EX(diversion_hModule, name, sigs)

// Two-stage search: tries to locate the function via string cross-reference first
// (more robust across builds), then falls back to byte patterns if no string hit is found.
// strSigs is a list of StringXRefSig entries; byteSigs is a Signature array from PatternDb.h.
#define INSTALL_HOOK_STR_D(name, strSigs, byteSigs)                           \
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

// Finds the function address and stores it in o<name> without installing a hook.
// Use this to get a callable pointer to an internal Steam function without intercepting it.
// Does not touch Detours — no transaction needed.
#define RESOLVE(module, name) \
    o##name = reinterpret_cast<name##_t>(FIND_SIG(module, name))

#define RESOLVE_D(name)       RESOLVE(diversion_hModule, name)

#define RESOLVE_EX(module, name, sigs) \
    o##name = reinterpret_cast<name##_t>(ByteSearch(module, #name, sigs, std::size(sigs)))

#define RESOLVE_EX_D(name, sigs)  RESOLVE_EX(diversion_hModule, name, sigs)

// Detaches the Detours hook and clears o<name> back to nullptr.
// Checks o<name> before detaching so it is safe to call even if the hook was never installed
// (e.g. because the pattern didn't match at startup). Call between UNHOOK_BEGIN/UNHOOK_END.
#define UNINSTALL_HOOK(name)                                          \
    do {                                                              \
        if (o##name) {                                                \
            DetourDetach(reinterpret_cast<PVOID*>(&o##name),           \
                         reinterpret_cast<PVOID>(hk##name));           \
            o##name = nullptr;                                        \
        }                                                             \
    } while (0)
