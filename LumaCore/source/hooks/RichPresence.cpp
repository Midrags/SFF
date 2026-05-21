#include "RichPresence.h"
#include "RuntimeCapture.h"
#include "utils/LuaLoader.h"
#include "utils/Logger.h"
#include "entry.h"
#include "steam_messages.pb.h"

namespace RichPresence {

    bool HandleRecv(const uint8* pBody, uint32 cbBody,
                    uint8* pOutBuf, uint32 outBufSize, uint32* pOutSize)
    {
        CMsgClientPersonaState msg;
        if (!msg.ParseFromArray(pBody, cbBody)) {
            LOG_MISC_WARN("RichPresence: failed to parse CMsgClientPersonaState");
            return false;
        }

        AppId_t realAppId = SteamCapture::ResolveAppId();
        if (!realAppId || !LuaLoader::HasDepot(realAppId))
            return false;

        bool patched = false;
        for (int i = 0; i < msg.friends_size(); ++i) {
            auto* f = msg.mutable_friends(i);
            if (static_cast<AppId_t>(f->game_played_app_id()) != kOnlineFixAppId)
                continue;

            std::string name = SteamCapture::GetGameNameByAppID(realAppId);
            f->set_game_played_app_id(realAppId);
            f->set_gameid(static_cast<uint64>(realAppId));
            if (!name.empty())
                f->set_game_name(name);

            LOG_MISC_INFO("RichPresence: patched friendid={} 480 -> {} ({})",
                          f->friendid(), realAppId, name);
            patched = true;
        }

        if (!patched) return false;

        uint32 sz = static_cast<uint32>(msg.ByteSizeLong());
        if (sz > outBufSize) {
            LOG_MISC_WARN("RichPresence: serialized size {} exceeds buffer {}", sz, outBufSize);
            return false;
        }
        if (!msg.SerializeToArray(pOutBuf, static_cast<int>(outBufSize))) {
            LOG_MISC_WARN("RichPresence: failed to SerializeToArray");
            return false;
        }

        *pOutSize = sz;
        return true;
    }

}
