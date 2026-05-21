#pragma once

#include <windows.h>
#include <cstdint>
#include <vector>
#include "hooks/StringFind.h"

// ── VEH one-shot capture entry ───────────────────────────────────────────────
struct CaptureEntry {
    void**      funcPtr;      // &o##Name
    void**      outPtr;       // capture target (e.g. &g_pCUser)
    uint8_t     restoreByte;  // original first byte, saved before arm
    const char* label;
};

// ── X-macro helpers (all include trailing semicolons for list expansion) ─────
// CAPTURE_LIST(X): X(FuncName, CaptureVar)
#define VEH_DECL_CAPTURE(name, out) name##_t o##name; void* out;
#define VEH_ARM(name, out)          ARM_CAPTURE_D(name, out);
// LOCATE_LIST(X): X(FuncName)
#define VEH_DECL_RESOLVE(name)      name##_t o##name;
#define VEH_LOCATE(name)            LC_RESOLVE_D(name);
#define VEH_ZERO_RESOLVE(name)      o##name = nullptr;

// ── ARM_CAPTURE_D ────────────────────────────────────────────────────────────
// Find signature, save original byte, push to g_captures, arm int3.
// Requires g_captures (std::vector<CaptureEntry>) in scope.
#define ARM_CAPTURE_D(name, outVar)                                            \
    do {                                                                        \
        if (auto* _p_ = FIND_SIG(diversion_hModule, name)) {                   \
            o##name = reinterpret_cast<name##_t>(_p_);                         \
            g_captures.push_back({                                              \
                reinterpret_cast<void**>(&o##name),                            \
                reinterpret_cast<void**>(&(outVar)),                           \
                *reinterpret_cast<uint8_t*>(_p_),                              \
                #name                                                           \
            });                                                                 \
            VehUtil::ArmInt3(_p_);                                              \
        }                                                                       \
    } while (0)

// ── ARM_CAPTURE_STR_D ───────────────────────────────────────────────────────
// Like ARM_CAPTURE_D but tries string cross-reference first, then falls back
// to byte pattern. Use when the target function contains a globally unique
// string literal.
#define ARM_CAPTURE_STR_D(name, outVar, strSigs, byteSigs)                     \
    do {                                                                        \
        void* _p_ = nullptr;                                                    \
        for (const auto& _s_ : (strSigs)) {                                     \
            _p_ = StringFind::FindFunction(diversion_hModule,                   \
                                           _s_.str, _s_.occurrence);             \
            if (_p_) break;                                                     \
        }                                                                       \
        if (!_p_) _p_ = FIND_SIG(diversion_hModule, name);                     \
        if (_p_) {                                                              \
            o##name = reinterpret_cast<name##_t>(_p_);                         \
            g_captures.push_back({                                              \
                reinterpret_cast<void**>(&o##name),                            \
                reinterpret_cast<void**>(&(outVar)),                           \
                *reinterpret_cast<uint8_t*>(_p_),                              \
                #name                                                           \
            });                                                                 \
            VehUtil::ArmInt3(_p_);                                              \
        }                                                                       \
    } while (0)

// ── VEH_CLEANUP_CAPTURES ─────────────────────────────────────────────────────
// Restore unarmed int3 sites, zero all pointers, clear the table.
#define VEH_CLEANUP_CAPTURES(captures)                                         \
    do {                                                                        \
        for (auto& _cap_ : (captures)) {                                       \
            if (*_cap_.funcPtr                                                  \
                && *reinterpret_cast<uint8_t*>(*_cap_.funcPtr) == 0xCC)         \
                VehUtil::RestoreByte(*_cap_.funcPtr, _cap_.restoreByte);        \
            *_cap_.funcPtr = nullptr;                                           \
            *_cap_.outPtr  = nullptr;                                           \
        }                                                                       \
        (captures).clear();                                                     \
    } while (0)

namespace VehUtil {
    void ArmInt3(void* target);
    void RestoreByte(void* target, uint8_t original);
}
