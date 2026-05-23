#include "SteamUI.h"
#include "CoreLoader.h"
#include "Macros.h"
#include "steam_messages.pb.h"
#include <thread>
#include <chrono>
#include <vector>

namespace {
    using namespace std::chrono_literals;
    constexpr int  MAX_RETRY      = 20;
    constexpr auto RETRY_INTERVAL = 300ms;

    // ── function type aliases ─────────────────────────────────────────────────
    using AddProtobufAsBinary_t = void*(__fastcall*)(void* /*args*/, void* /*proto*/);
    using GetAppByID_t          = void*(__fastcall*)(void* /*controller*/, AppId_t, bool /*create*/);
    using GetTopManager_t       = void*(__fastcall*)();

    // ── resolved function pointers ────────────────────────────────────────────
    inline AddProtobufAsBinary_t oAddProtobufAsBinary = nullptr;
    inline GetAppByID_t          oGetAppByID          = nullptr;
    inline GetTopManager_t       oGetTopManager       = nullptr;

    // CSteamUIAppController offsets (see its Validate() method):
    //   +0xAB8 from top-manager -> CSteamUIAppController*
    //   +1744  m_vecAppOverviewChanged (subscriber vec data ptr)
    //   +1760  m_vecAppOverviewChanged size
    constexpr size_t kControllerInTopManager     = 0xAB8;
    constexpr size_t kSubscriberVecOffset        = 1744;
    constexpr size_t kSubscriberVecSizeOffset    = 1760;

    constexpr size_t kArgsSize                   = 64;
    constexpr size_t kSubscriberInvokeVtableSlot = 4;

    // Cleared so BuildCompleteAppOverviewChange's filter (BIsOwned via
    // vtable[22]) also excludes the app on the next full snapshot.
    constexpr size_t kCSteamAppOwnedFlagOffset   = 28;

    // ── LoadModuleWithPath hook ───────────────────────────────────────────────
    LC_HOOK_DEF(LoadModuleWithPath, HMODULE, const char* path, bool flags) {
        LOG_STEAMUI_INFO("LoadModuleWithPath called with path: {} , flags: {}", path, flags);
        // Wait for steamclient hooks to be installed before redirecting.
        for (int i = 0; i < MAX_RETRY && !g_HooksInstalled.load(); ++i) {
            LOG_STEAMUI_DEBUG("LoadModuleWithPath: waiting for hooks... (attempt {}/{})", i + 1, MAX_RETRY);
            std::this_thread::sleep_for(RETRY_INTERVAL);
        }
        HMODULE h = oLoadModuleWithPath(path, flags);
        if (!strcmp(path, "steamclient64.dll"))
            h = diversion_hModule;
        return h;
    }

    // ── TopManagerCall decode ─────────────────────────────────────────────────
    // The TopManagerCall anchor matches inside MarkAppChange's body.
    // Decode the rel32 at +10 to find the 2-instruction getter:
    //   mov rax, [rip+disp]; ret
    GetTopManager_t DecodeTopManagerGetter(uint8_t* anchor) {
        if (!anchor) return nullptr;
        int32_t rel32 = *reinterpret_cast<const int32_t*>(anchor + 10);
        uint8_t* getter = anchor + 14 + rel32;
        if (getter[0] != 0x48 || getter[1] != 0x8B || getter[2] != 0x05 || getter[7] != 0xC3)
            return nullptr;
        return reinterpret_cast<GetTopManager_t>(getter);
    }

    // Fetch the CSteamUIAppController via the captured getter.
    void* ResolveController() {
        if (!oGetTopManager) return nullptr;
        void* topMgr = oGetTopManager();
        if (!topMgr) return nullptr;
        return *reinterpret_cast<void**>(static_cast<uint8_t*>(topMgr) + kControllerInTopManager);
    }

    // Synthesize a CAppOverview_Change proto with removed_appid=[appId] and
    // dispatch to every registered webhelper subscriber.
    bool EmitRemovedAppIds(void* pController, const AppId_t* ids, size_t count);

    bool EmitRemovedAppId(void* pController, AppId_t appId) {
        return EmitRemovedAppIds(pController, &appId, 1);
    }

    bool EmitRemovedAppIds(void* pController, const AppId_t* ids, size_t count) {
        if (!ids || count == 0) return false;
        alignas(8) uint8_t argsBuf[kArgsSize] = {};

        ::CAppOverview_Change msg;
        for (size_t i = 0; i < count; ++i) msg.add_removed_appid(ids[i]);
        msg.set_update_complete(true);
        oAddProtobufAsBinary(argsBuf, &msg);

        void** vecData = *reinterpret_cast<void***>(
            static_cast<uint8_t*>(pController) + kSubscriberVecOffset);
        uint32_t subCount = *reinterpret_cast<uint32_t*>(
            static_cast<uint8_t*>(pController) + kSubscriberVecSizeOffset);

        if (!vecData || subCount == 0) {
            LOG_STEAMUI_WARN("EmitRemovedAppIds: no subscribers; count={}", count);
            return false;
        }

        for (uint32_t i = 0; i < subCount; ++i) {
            void* subscriber = vecData[i];
            if (!subscriber) continue;
            void** vtable = *reinterpret_cast<void***>(subscriber);
            auto invoke = reinterpret_cast<void(__fastcall*)(void*, void*)>(
                vtable[kSubscriberInvokeVtableSlot]);
            invoke(subscriber, argsBuf);
        }

        return true;
    }

} // anonymous namespace

namespace SteamUI {

    void CoreHook() {
        HMODULE hSteamUI = GetModuleHandleA("steamui.dll");
        if (!hSteamUI) {
            LOG_STEAMUI_WARN("steamui.dll not loaded; SteamUI hooks disabled");
            return;
        }

        LC_TX_OPEN();
        // Byte-pattern only — see PatternDb.h LoadModuleWithPathSigs comment.
        LC_ATTACH(hSteamUI, LoadModuleWithPath);
        LC_TX_COMMIT();

        // Resolve helper functions (no hook, called directly from RemoveAppOverview).
        LC_RESOLVE(hSteamUI, GetAppByID);

        // AddProtobufAsBinary: try string XRef first, fall back to byte pattern.
        {
            void* _p_ = nullptr;
            for (const auto& _s_ : AddProtobufAsBinaryStrSigs) {
                _p_ = StringFind::FindFunction(hSteamUI, _s_.str, _s_.occurrence);
                if (_p_) break;
            }
            if (!_p_) _p_ = FIND_SIG(hSteamUI, AddProtobufAsBinary);
            oAddProtobufAsBinary = reinterpret_cast<AddProtobufAsBinary_t>(_p_);
        }

        auto* anchor = static_cast<uint8_t*>(FIND_SIG(hSteamUI, TopManagerCall));
        oGetTopManager = DecodeTopManagerGetter(anchor);

        LOG_STEAMUI_INFO("Install: GetAppByID={}, AddProtobufAsBinary={}, GetTopManager={}",
                         reinterpret_cast<void*>(oGetAppByID),
                         reinterpret_cast<void*>(oAddProtobufAsBinary),
                         reinterpret_cast<void*>(oGetTopManager));
    }

    void CoreUnhook() {
        LC_TX_OPEN();
        LC_DETACH(LoadModuleWithPath);
        LC_TX_COMMIT();

        oAddProtobufAsBinary = nullptr;
        oGetAppByID          = nullptr;
        oGetTopManager       = nullptr;
    }

    void RemoveAppOverview(AppId_t appId) {
        if (!oAddProtobufAsBinary || !oGetTopManager || !oGetAppByID) {
            LOG_STEAMUI_WARN("RemoveAppOverview: primitives unresolved; appId={}", appId);
            return;
        }

        void* pController = ResolveController();
        if (!pController) {
            LOG_STEAMUI_WARN("RemoveAppOverview: controller singleton not initialized; appId={}", appId);
            return;
        }

        // Clear the host-side CSteamApp owned flag if a CSteamApp exists for
        // this id. Sub-depots (e.g. HL1's 221-234) won't have one — that's
        // fine, just skip the flag-clear and still emit the removal so any
        // stale subscriber state for the id gets cleaned up. Mirrors OST.
        if (void* pApp = oGetAppByID(pController, appId, /*create=*/false)) {
            *reinterpret_cast<uint32_t*>(static_cast<uint8_t*>(pApp) + kCSteamAppOwnedFlagOffset) &= ~1u;
        }

        if (!EmitRemovedAppId(pController, appId)) return;

        LOG_STEAMUI_INFO("RemoveAppOverview: appId={} done", appId);
    }

    // Kept for API stability — only used when callers explicitly want a
    // multi-id dispatch. The live NotifyLicenseChanged path uses per-id
    // RemoveAppOverview because Steam's webhelper handler crashes on
    // multi-id CAppOverview_Change bursts in some build/load combos.
    void RemoveAppOverviewBatch(const AppId_t* ids, size_t count) {
        if (!ids || count == 0) return;
        for (size_t i = 0; i < count; ++i) {
            RemoveAppOverview(ids[i]);
        }
    }

} // namespace SteamUI
