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
#include <vector>

namespace {
    std::atomic<AppId_t> g_realAppId{0};
    std::mutex g_routeLock;
    std::vector<std::string> g_imageNames;

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

    bool ShouldActivate(AppId_t appId, bool hasDepot, bool owned,
                        bool hasManualFlag, bool detectedSteamStub) {
        return hasDepot
            && !owned
            && !hasManualFlag
            && detectedSteamStub;
    }

    void Arm(AppId_t realAppId, const char* exePath, std::string_view detectedImagePath) {
        std::string image = BaseName(exePath ? std::string_view(exePath) : std::string_view{});
        std::string detectedImage = BaseName(detectedImagePath);
        {
            std::scoped_lock lock(g_routeLock);
            g_imageNames.clear();
            if (!image.empty())
                g_imageNames.push_back(image);
            if (!detectedImage.empty()
                && std::ranges::find(g_imageNames, detectedImage) == g_imageNames.end())
                g_imageNames.push_back(detectedImage);
            g_realAppId.store(realAppId, std::memory_order_release);
        }
        LOG_MISC_INFO("SteamStubAuto: armed appid={} launch={} detected={}",
                      realAppId,
                      image.empty() ? "-" : image,
                      detectedImage.empty() ? "-" : detectedImage);
    }

    void Clear() {
        AppId_t oldAppId = g_realAppId.exchange(0, std::memory_order_acq_rel);
        std::vector<std::string> oldImages;
        {
            std::scoped_lock lock(g_routeLock);
            oldImages.swap(g_imageNames);
        }
        if (oldAppId || !oldImages.empty()) {
            std::string joined;
            for (const auto& image : oldImages) {
                if (!joined.empty()) joined += ",";
                joined += image;
            }
            LOG_MISC_DEBUG("SteamStubAuto: cleared appid={} exe={}",
                           oldAppId, joined.empty() ? "-" : joined);
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
        if (g_imageNames.empty() || current.empty())
            return 0;
        if (std::ranges::find(g_imageNames, current) == g_imageNames.end())
            return 0;

        LOG_MISC_TRACE("SteamStubAuto: resolved image={} appid={}",
                       current, realAppId);
        return realAppId;
    }

}
