#include "VehUtil.h"

namespace VehUtil {
    void ArmInt3(void* target) {
        DWORD oldProtect = 0;
        VirtualProtect(target, 1, PAGE_EXECUTE_READWRITE, &oldProtect);
        *static_cast<uint8_t*>(target) = 0xCC;
    }

    void RestoreByte(void* target, uint8_t original) {
        DWORD oldProtect = 0;
        VirtualProtect(target, 1, PAGE_EXECUTE_READWRITE, &oldProtect);
        *static_cast<uint8_t*>(target) = original;
    }
}
