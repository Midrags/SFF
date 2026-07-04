// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/NetPacket.h"
#include "hooks/client/SteamStubAuto.h"
#include "core/entry.h"
#include "runtime/Logger.h"

namespace NetPacket::Handlers::SteamStub {

bool HandleSend(const uint8_t* pBody, uint32_t cbBody) {
    if (!SteamStubAuto::IsActive())
        return false;

    AppId_t realAppId = SteamStubAuto::RealAppId();
    if (!realAppId || realAppId == kOnlineFixAppId)
        return false;

    CMsgClientGamesPlayed msg;
    if (!msg.ParseFromArray(pBody, cbBody)) {
        LOG_PKTRT_WARN("{{\"evt\":\"SteamStubAuto\",\"act\":\"send\",\"err\":\"parse-fail\"}}");
        return false;
    }

    bool patched = false;
    bool sawRelevant = false;
    for (int i = 0; i < msg.games_played_size(); ++i) {
        auto* game = msg.mutable_games_played(i);
        AppId_t appId = static_cast<AppId_t>(game->game_id() & UINT32_MAX);
        const uint32 pid = game->has_process_id() ? game->process_id() : 0;

        if (appId == realAppId) {
            game->set_game_id(kOnlineFixAppId);
            game->clear_game_extra_info();
            patched = true;
            sawRelevant = true;
            LOG_PKTRT_INFO("{{\"evt\":\"SteamStubAuto\",\"act\":\"patch\",\"kind\":\"games_played real->480\",\"was\":{},\"now\":{},\"pid\":{}}}",
                           realAppId, kOnlineFixAppId, pid);
        } else if (appId == kOnlineFixAppId) {
            sawRelevant = true;
            if (game->has_game_extra_info() && !game->game_extra_info().empty()) {
                game->clear_game_extra_info();
                patched = true;
                LOG_PKTRT_INFO("{{\"evt\":\"SteamStubAuto\",\"act\":\"patch\",\"kind\":\"games_played keep-480-clear-name\",\"appId\":{},\"pid\":{}}}",
                               kOnlineFixAppId, pid);
            } else {
                LOG_PKTRT_DEBUG("{{\"evt\":\"SteamStubAuto\",\"act\":\"send\",\"kind\":\"games_played keep-480\",\"appId\":{},\"pid\":{}}}",
                                kOnlineFixAppId, pid);
            }
        }
    }

    if (!patched) {
        if (!sawRelevant) {
            LOG_PKTRT_DEBUG("{{\"evt\":\"SteamStubAuto\",\"act\":\"send\",\"info\":\"no-route-entry\",\"realAppId\":{}}}",
                            realAppId);
        }
        return false;
    }

    s_tx.BodyLen = static_cast<uint32_t>(msg.ByteSizeLong());
    if (s_tx.BodyLen > kBodyCap) {
        LOG_PKTRT_WARN("{{\"evt\":\"SteamStubAuto\",\"act\":\"send\",\"err\":\"overflow\",\"size\":{}}}", s_tx.BodyLen);
        return false;
    }
    if (!msg.SerializeToArray(s_tx.Body, kBodyCap)) {
        LOG_PKTRT_WARN("{{\"evt\":\"SteamStubAuto\",\"act\":\"send\",\"err\":\"encode-fail\"}}");
        return false;
    }

    LOG_PKTRT_DEBUG("{{\"evt\":\"SteamStubAuto\",\"act\":\"send\",\"modified\":{}}}", msg.DebugString());
    return true;
}

} // namespace NetPacket::Handlers::SteamStub
