// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/SteamStubAuto.h"
#include "runtime/Ticket.h"
#include "runtime/Logger.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <mutex>
#include <string>

namespace {
    std::atomic<AppId_t> g_realAppId{0};
    std::mutex g_routeLock;
    std::string g_imageName;

    std::string LowerAscii(std::string_view text) {
        std::string out(text);
        std::transform(out.begin(), out.end(), out.begin(), [](unsigned char ch) {
            return static_cast<char>(std::tolower(ch));
        });
        return out;
    }

    std::string BaseName(std::string_view path) {
        size_t pos = path.find_last_of("\\/");
        if (pos != std::string_view::npos)
            path.remove_prefix(pos + 1);
        return LowerAscii(path);
    }
}

namespace SteamStubAuto {

    bool ShouldActivate(AppId_t appId, bool hasDepot, bool owned, bool hasManualFlag) {
        return hasDepot
            && !owned
            && !hasManualFlag
            && Ticket::IsKnownSteamDrmApp(appId);
    }

    void Arm(AppId_t realAppId, const char* exePath) {
        std::string image = BaseName(exePath ? std::string_view(exePath) : std::string_view{});
        {
            std::scoped_lock lock(g_routeLock);
            g_imageName = image;
            g_realAppId.store(realAppId, std::memory_order_release);
        }
        LOG_MISC_INFO("SteamStubAuto: armed appid={} exe={}",
                      realAppId, image.empty() ? "-" : image);
    }

    void Clear() {
        AppId_t oldAppId = g_realAppId.exchange(0, std::memory_order_acq_rel);
        std::string oldImage;
        {
            std::scoped_lock lock(g_routeLock);
            oldImage.swap(g_imageName);
        }
        if (oldAppId || !oldImage.empty()) {
            LOG_MISC_DEBUG("SteamStubAuto: cleared appid={} exe={}",
                           oldAppId, oldImage.empty() ? "-" : oldImage);
        }
    }

    bool IsActive() {
        return g_realAppId.load(std::memory_order_acquire) != 0;
    }

    AppId_t RealAppId() {
        return g_realAppId.load(std::memory_order_acquire);
    }

    AppId_t ResolveForImage(std::string_view imageName, AppId_t envAppId) {
        if (envAppId != kOnlineFixAppId)
            return 0;

        AppId_t realAppId = g_realAppId.load(std::memory_order_acquire);
        if (!realAppId)
            return 0;

        const std::string current = BaseName(imageName);
        std::scoped_lock lock(g_routeLock);
        if (g_imageName.empty() || current.empty() || current != g_imageName)
            return 0;

        LOG_MISC_TRACE("SteamStubAuto: resolved image={} appid={}",
                       current, realAppId);
        return realAppId;
    }

}
