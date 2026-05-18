// Hook KeyValues::ReadAsBinary — entry point for KV-tree manipulation.
// Manifest depot patching is handled by ManifestBind::BuildDepotDependency.

#include "KeyValues.h"
#include "Macros.h"
#include "entry.h"

namespace {

    HOOK_FUNC(ReadAsBinary, bool, KeyValues* root, void* buf, int depth,
              bool textMode, void* symTable) {
        bool ok = oReadAsBinary(root, buf, depth, textMode, symTable);
        return ok;
    }

    using FindOrCreateKey_t = KeyValues*(*)(KeyValues*, const char*, bool, KeyValues**);
    FindOrCreateKey_t oFindOrCreateKey = nullptr;

    // ── KeyValuesSystem — symbol ↔ string (from vstdlib_s64.dll) ───

    IKeyValuesSystem* GetKeyValuesSystem() {
        static IKeyValuesSystem* sys = []() -> IKeyValuesSystem* {
            HMODULE vstdlib = GetModuleHandleW(L"vstdlib_s64.dll");
            if (!vstdlib) return nullptr;
            auto pfn = (KeyValuesSystemSteam_t)GetProcAddress(vstdlib, "KeyValuesSystemSteam");
            return pfn ? pfn() : nullptr;
        }();
        return sys;
    }

    const char* GetKeyName(int symbol) {
        auto* sys = GetKeyValuesSystem();
        auto name = sys->GetStringForSymbol(symbol);
        LOG_KEYVALUE_TRACE("GetKeyName: symbol={} -> name={}", symbol, name);
        return name ? name : nullptr;
    }

    KeyValues* KV_FindKey(KeyValues* parent, const char* name) {
        return oFindOrCreateKey ? oFindOrCreateKey(parent, name, false, nullptr) : nullptr;
    }

} // anonymous namespace

namespace KeyValues {

    void Install() {
        RESOLVE_EX_D(FindOrCreateKey, KeyValues_FindOrCreateKeySigs);
        if (!oFindOrCreateKey) return;

        HOOK_BEGIN();
        INSTALL_HOOK_EX_D(ReadAsBinary, KeyValues_ReadAsBinarySigs);
        HOOK_END();
    }

    void Uninstall() {
        if (!oReadAsBinary) return;
        UNHOOK_BEGIN();
        UNINSTALL_HOOK(ReadAsBinary);
        UNHOOK_END();
        oFindOrCreateKey = nullptr;
    }

} // namespace KeyValues
