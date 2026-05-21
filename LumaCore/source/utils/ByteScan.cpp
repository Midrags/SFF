#include "ByteScan.h"
#include "Logger.h"
#include <cstdint>
#include <psapi.h>
#include <string>
#include <vector>

// The running Steam build ID, set once at startup by entry.cpp's DetectSteamBuildId().
// ByteSearch reads this here but never writes it. Empty string means detection failed
// and ByteSearch falls back to trying all signature entries in declaration order.
extern std::string g_steamBuildId;

// Converts a single hex character to its numeric value, or -1 on invalid input.
static int HexDigit(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// Converts a hex-pattern string into two parallel arrays: byte values and match flags.
// Concrete byte "4C" → bytes[i]=0x4C, mask[i]=1. Wildcard "??" → bytes[i]=0, mask[i]=0.
// Returns false on empty input or any token that isn't a valid hex pair or "??".
static bool ParseSignature(const char* str, std::vector<uint8_t>& bytes, std::vector<uint8_t>& mask)
{
    bytes.clear();
    mask.clear();

    for (const char* p = str; *p; ) {
        if (*p == ' ' || *p == '\t' || *p == ',') { ++p; continue; }

        if (p[0] == '?' && p[1] == '?') {
            bytes.push_back(0);
            mask.push_back(0);
            p += 2;
            continue;
        }

        int hi = HexDigit(p[0]);
        int lo = HexDigit(p[1]);
        if (hi < 0 || lo < 0) return false;

        bytes.push_back(static_cast<uint8_t>((hi << 4) | lo));
        mask.push_back(1);
        p += 2;
    }
    return !bytes.empty();
}

// Scans a loaded module's image for a byte pattern.
// Uses memchr on the first concrete (non-wildcard) byte to skip large stretches of mismatches,
// which is significantly faster than a byte-by-byte walk on large images.
// matchIndex controls which occurrence to return (1 = first, 2 = second, etc.).
static void* ScanOne(HMODULE module, const std::vector<uint8_t>& bytes,
                     const std::vector<uint8_t>& mask, int matchIndex)
{
    MODULEINFO modInfo{};
    if (!GetModuleInformation(GetCurrentProcess(), module, &modInfo, sizeof(MODULEINFO)))
        return nullptr;

    const uint8_t* base    = static_cast<const uint8_t*>(modInfo.lpBaseOfDll);
    const SIZE_T   imgSize = modInfo.SizeOfImage;
    const SIZE_T   patLen  = bytes.size();

    if (imgSize < patLen) return nullptr;

    // Locate the first concrete byte in the pattern to use as an anchor.
    // memchr on the anchor byte is far faster than testing every start offset.
    SIZE_T  anchorOff  = SIZE_T(-1);
    uint8_t anchorByte = 0;
    for (SIZE_T k = 0; k < patLen; ++k) {
        if (mask[k]) { anchorOff = k; anchorByte = bytes[k]; break; }
    }

    const SIZE_T scanEnd = imgSize - patLen;  // last valid pattern-start offset
    int hits = 0;

    if (anchorOff == SIZE_T(-1)) {
        // All-wildcard pattern — every start position matches.
        return (hits + 1 == matchIndex) ? const_cast<uint8_t*>(base) : nullptr;
    }

    // For each anchor hit at (base + aPos), the candidate pattern start is (aPos - anchorOff).
    const uint8_t* scanFrom = base + anchorOff;
    SIZE_T         left     = scanEnd + 1;

    while (left) {
        const uint8_t* aHit = static_cast<const uint8_t*>(memchr(scanFrom, anchorByte, left));
        if (!aHit) break;

        const uint8_t* start = aHit - anchorOff;
        bool ok = true;
        for (SIZE_T j = 0; j < patLen; ++j) {
            if (mask[j] && start[j] != bytes[j]) { ok = false; break; }
        }
        if (ok && ++hits == matchIndex)
            return const_cast<uint8_t*>(start);

        SIZE_T consumed = static_cast<SIZE_T>(aHit + 1 - scanFrom);
        if (consumed >= left) break;
        left    -= consumed;
        scanFrom = aHit + 1;
    }
    return nullptr;
}

// Combines ParseSignature and ScanOne for a single Signature entry.
// Logs a warning and returns nullptr if the pattern string is malformed.
static void* TrySig(HMODULE module, const char* funcName, const Signature& sig)
{
    std::vector<uint8_t> bytes, mask;
    if (!ParseSignature(sig.signature, bytes, mask)) {
        LOG_WARN("ByteSearch: {} — bad signature '{}'", funcName ? funcName : "", sig.label);
        return nullptr;
    }
    return ScanOne(module, bytes, mask, sig.matchIndex);
}

// Core search logic shared by both ByteSearch overloads.
// Pass 1: if g_steamBuildId is known, find the entry whose label matches it and try that one first.
//         This fast path avoids scanning the entire image with the wrong pattern on most runs.
// Pass 2: try every other entry in order, skipping whichever was already tried in pass 1.
// If nothing matches, logs a warning listing the build ID and every label that was tried.
static void* ByteSearchImpl(HMODULE module, const char* funcName,
                            const Signature* sigs, size_t count)
{
    // 1. Try the entry whose label matches the current build.
    if (!g_steamBuildId.empty()) {
        for (size_t i = 0; i < count; ++i) {
            if (sigs[i].label && g_steamBuildId == sigs[i].label) {
                if (void* addr = TrySig(module, funcName, sigs[i])) {
                    if (funcName)
                        LOG_DEBUG("ByteSearch: {} matched build-id '{}'",
                                  funcName, sigs[i].label);
                    return addr;
                }
                if (funcName)
                    LOG_DEBUG("ByteSearch: {} build-id '{}' did NOT match, "
                              "falling back to try-all", funcName, sigs[i].label);
                break;  // at most one entry per build id; stop searching the array
            }
        }
    }

    // 2. Try everything else in order.
    for (size_t i = 0; i < count; ++i) {
        // Skip the preferred entry we already tried (no point retrying it).
        if (!g_steamBuildId.empty() && sigs[i].label && g_steamBuildId == sigs[i].label)
            continue;
        if (void* addr = TrySig(module, funcName, sigs[i])) {
            if (funcName)
                LOG_DEBUG("ByteSearch: {} matched fallback '{}'", funcName, sigs[i].label);
            return addr;
        }
    }

    // 3. Nothing matched.
    if (!funcName) return nullptr;

    std::string failedList;
    for (size_t i = 0; i < count; ++i) {
        if (!failedList.empty()) failedList += ", ";
        failedList += "'";
        failedList += sigs[i].label;
        failedList += "'";
    }
    LOG_WARN("ByteSearch FAILED: {} (build={}) — tried: {}",
             funcName, g_steamBuildId.empty() ? "unknown" : g_steamBuildId.c_str(),
             failedList);
    return nullptr;
}

// Forwards to ByteSearchImpl using the initializer_list's contiguous storage.
void* ByteSearch(HMODULE module, const char* funcName, std::initializer_list<Signature> sigs)
{
    return ByteSearchImpl(module, funcName, sigs.begin(), sigs.size());
}

// Forwards to ByteSearchImpl using a raw pointer and count (used with PatternDb.h inline arrays).
void* ByteSearch(HMODULE module, const char* funcName, const Signature* sigs, size_t count)
{
    return ByteSearchImpl(module, funcName, sigs, count);
}

// Writes nSize bytes from pNewBytes into the memory at pAddress.
// The target is typically inside a loaded DLL's code section, which is read+execute but not writable.
// VirtualProtect temporarily marks the page as PAGE_EXECUTE_READWRITE, the bytes are copied,
// then FlushInstructionCache tells the CPU to discard any cached decoded instructions at that range
// so the patched bytes take effect immediately.
int PatchMemoryBytes(void* pAddress, const void* pNewBytes, SIZE_T nSize)
{
    if (!pAddress || !pNewBytes || nSize == 0) return 0;

    DWORD oldProtect = 0;
    if (!VirtualProtect(pAddress, nSize, PAGE_EXECUTE_READWRITE, &oldProtect))
        return 0;

    memcpy(pAddress, pNewBytes, nSize);
    FlushInstructionCache(GetCurrentProcess(), pAddress, nSize);

    DWORD tmp = 0;
    VirtualProtect(pAddress, nSize, oldProtect, &tmp);
    return 1;
}
