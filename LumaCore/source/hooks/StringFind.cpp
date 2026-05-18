#include "StringFind.h"

#include <algorithm>
#include <cstring>
#include <vector>

namespace StringFind {

static PIMAGE_NT_HEADERS GetNtHeaders(HMODULE hMod)
{
    auto* dos = reinterpret_cast<PIMAGE_DOS_HEADER>(hMod);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return nullptr;
    auto* nt = reinterpret_cast<PIMAGE_NT_HEADERS>(
        reinterpret_cast<uint8_t*>(hMod) + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return nullptr;
    return nt;
}

void* FindFunction(HMODULE hMod, const char* targetStr, int occurrence)
{
    if (!hMod || !targetStr || occurrence < 1) return nullptr;

    auto* base = reinterpret_cast<uint8_t*>(hMod);
    auto* nt   = GetNtHeaders(hMod);
    if (!nt) return nullptr;

    const size_t strLen = strlen(targetStr);
    if (strLen == 0) return nullptr;

    // Step 1. Collect every virtual address in the loaded image where targetStr appears
    // as a complete, null-terminated string. Only non-executable sections are scanned
    // (executable sections contain code, not string data), so this avoids false positives.
    std::vector<uintptr_t> stringVAs;
    {
        auto* sec = IMAGE_FIRST_SECTION(nt);
        for (WORD i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++sec) {
            if (sec->Characteristics & IMAGE_SCN_MEM_EXECUTE) continue;
            const DWORD secSize = sec->Misc.VirtualSize;
            if (secSize < strLen + 1) continue;
            const uint8_t* start = base + sec->VirtualAddress;
            const uint8_t* end   = start + secSize;
            for (const uint8_t* p = start; p + strLen < end; ++p) {
                if (memcmp(p, targetStr, strLen) == 0 && p[strLen] == '\0')
                    stringVAs.push_back(reinterpret_cast<uintptr_t>(p));
            }
        }
    }
    if (stringVAs.empty()) return nullptr;

    // Step 2. Scan the first executable section (.text) for RIP-relative LEA instructions
    // that load one of the string addresses collected above.
    // x64 LEA encoding: [REX byte: 0x48..0x4F] [0x8D] [ModRM byte where (byte & 0xC7) == 0x05] [4-byte disp32]
    // The CPU computes the referenced address as: (address of next instruction) + sign_extended(disp32)
    // which equals instrVA + 7 + disp32. A match means this instruction loads the address of our string.
    PIMAGE_SECTION_HEADER textSec = nullptr;
    {
        auto* sec = IMAGE_FIRST_SECTION(nt);
        for (WORD i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++sec) {
            if (sec->Characteristics & IMAGE_SCN_MEM_EXECUTE) {
                textSec = sec;
                break;
            }
        }
    }
    if (!textSec) return nullptr;

    const uint8_t* textStart = base + textSec->VirtualAddress;
    const uint8_t* textEnd   = textStart + textSec->Misc.VirtualSize;

    int found = 0;
    for (const uint8_t* p = textStart; p + 7 <= textEnd; ++p) {
        uint8_t rex = *p;
        if (rex < 0x48 || rex > 0x4F) continue;
        if (p[1] != 0x8D) continue;
        if ((p[2] & 0xC7) != 0x05) continue;

        int32_t disp32 = 0;
        memcpy(&disp32, p + 3, 4);
        uintptr_t refVA = reinterpret_cast<uintptr_t>(p + 7)
                        + static_cast<uintptr_t>(static_cast<intptr_t>(disp32));

        bool hit = false;
        for (uintptr_t sva : stringVAs) {
            if (refVA == sva) { hit = true; break; }
        }
        if (!hit) continue;

        ++found;
        if (found < occurrence) continue;

        // Step 3. The LEA instruction is somewhere inside the function we want, not at its start.
        // .pdata (IMAGE_DIRECTORY_ENTRY_EXCEPTION) holds RUNTIME_FUNCTION entries sorted by BeginAddress.
        // Binary search finds the entry whose range [BeginAddress, EndAddress) contains our instruction.
        // BeginAddress gives us the function entry point.
        uintptr_t instrRVA = reinterpret_cast<uintptr_t>(p)
                           - reinterpret_cast<uintptr_t>(base);
        auto& ed = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
        if (!ed.VirtualAddress || !ed.Size) return const_cast<uint8_t*>(p);

        auto* rfBegin = reinterpret_cast<PRUNTIME_FUNCTION>(base + ed.VirtualAddress);
        auto* rfEnd   = rfBegin + ed.Size / sizeof(RUNTIME_FUNCTION);

        // binary search — array is sorted by BeginAddress
        auto it = std::upper_bound(
            rfBegin, rfEnd, static_cast<DWORD>(instrRVA),
            [](DWORD val, const RUNTIME_FUNCTION& rf) {
                return val < rf.BeginAddress;
            });
        if (it == rfBegin) return nullptr;
        --it;
        if (it->BeginAddress <= static_cast<DWORD>(instrRVA)
            && static_cast<DWORD>(instrRVA) < it->EndAddress)
            return base + it->BeginAddress;

        return nullptr;
    }

    return nullptr;
}

} // namespace StringFind
