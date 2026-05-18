#pragma once
#include <cstdint>

// ---- compile-time FNV-1a hash (32-bit) --------
constexpr uint32_t Fnv1aHash(const char* str)
{
    uint32_t hash = 0x811c9dc5;
    while (*str) {
        hash ^= static_cast<uint32_t>(*str++);
        hash *= 0x01000193;
    }
    return hash;
}
