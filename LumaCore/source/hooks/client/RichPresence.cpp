// LumaCore — Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/RichPresence.h"
#include "hooks/client/SteamStubAuto.h"
#include "hooks/capture/RuntimeCapture.h"
#include "config/LuaLoader.h"
#include "runtime/Logger.h"
#include "core/entry.h"
#include "Steam/Structs.h"
#include "steam_messages.pb.h"
#include <cstring>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>

namespace RichPresence {

    namespace {
        constexpr uint32 kBodyLimit = 262144;
        constexpr uint32 kHdrLimit = 1024;
        constexpr uint32 kPacketLimit = sizeof(MsgHdr) + kHdrLimit + kBodyLimit;
        constexpr uint32 kRichPresenceFlag = 0x1000;

        std::mutex g_lock;
        AppId_t g_visibleApp = 0;
        uint64 g_selfSteamId = 0;

        uint8 g_selfHdr[kHdrLimit]{};
        uint32 g_selfHdrLen = 0;
        uint8 g_selfBody[kBodyLimit]{};
        uint32 g_selfBodyLen = 0;
        bool g_hasSelfTemplate = false;

        uint8 g_stagedPacket[kPacketLimit]{};
        uint32 g_stagedPacketLen = 0;
        bool g_staged = false;

        std::unordered_map<AppId_t, std::vector<std::pair<std::string, std::string>>> g_uploadKvs;

        void CollectKvStrings(const uint8* data, uint32 size,
                              std::vector<std::pair<std::string, std::string>>& out)
        {
            uint32 cursor = 0;
            int depth = 0;
            auto readZ = [&](std::string& value) -> bool {
                uint32 start = cursor;
                while (cursor < size && data[cursor] != 0)
                    ++cursor;
                if (cursor >= size)
                    return false;
                value.assign(reinterpret_cast<const char*>(data + start), cursor - start);
                ++cursor;
                return true;
            };

            while (cursor < size) {
                uint8 type = data[cursor++];
                if (type == 0x08) {
                    if (depth == 0)
                        break;
                    --depth;
                    continue;
                }
                if (type == 0x00) {
                    std::string ignored;
                    if (!readZ(ignored))
                        return;
                    ++depth;
                    continue;
                }
                if (type == 0x01) {
                    std::string key;
                    std::string value;
                    if (!readZ(key) || !readZ(value))
                        return;
                    out.emplace_back(std::move(key), std::move(value));
                    continue;
                }
                return;
            }
        }

        void ApplyPresence(CMsgClientPersonaState& msg,
                           CMsgClientPersonaState::Friend* entry,
                           AppId_t appId)
        {
            if (appId == 0) {
                entry->clear_game_played_app_id();
                entry->clear_gameid();
                entry->clear_game_name();
                entry->clear_rich_presence();
                msg.set_status_flags(msg.status_flags() | kRichPresenceFlag);
                return;
            }

            entry->set_game_played_app_id(appId);
            entry->set_gameid(static_cast<uint64>(appId));
            std::string name = SteamCapture::GetGameNameByAppID(appId);
            if (!name.empty())
                entry->set_game_name(name);

            entry->clear_rich_presence();
            auto it = g_uploadKvs.find(appId);
            const bool hasKv = it != g_uploadKvs.end() && !it->second.empty();
            if (hasKv) {
                for (const auto& kv : it->second) {
                    auto* out = entry->add_rich_presence();
                    out->set_key(kv.first);
                    out->set_value(kv.second);
                }
                msg.set_status_flags(msg.status_flags() | kRichPresenceFlag);
            } else {
                msg.set_status_flags(msg.status_flags() & ~kRichPresenceFlag);
            }
        }

        bool StagePersonaUpdate(AppId_t appId)
        {
            if (!g_hasSelfTemplate)
                return false;

            CMsgClientPersonaState msg;
            if (!msg.ParseFromArray(g_selfBody, g_selfBodyLen))
                return false;

            CMsgClientPersonaState::Friend* self = nullptr;
            for (int i = 0; i < msg.friends_size(); ++i) {
                auto* f = msg.mutable_friends(i);
                if (f->has_friendid() && f->friendid() == g_selfSteamId) {
                    self = f;
                    break;
                }
            }
            if (!self)
                return false;

            ApplyPresence(msg, self, appId);

            const uint32 bodyLen = static_cast<uint32>(msg.ByteSizeLong());
            const uint32 packetLen = sizeof(MsgHdr) + g_selfHdrLen + bodyLen;
            if (bodyLen > kBodyLimit || packetLen > kPacketLimit) {
                LOG_MISCCH_WARN("RichPresence: staged persona update too large ({})", packetLen);
                return false;
            }

            auto* hdr = reinterpret_cast<MsgHdr*>(g_stagedPacket);
            hdr->eMsg = static_cast<EMsg>(
                static_cast<uint32>(k_EMsgClientPersonaState) | kMsgHdrProtoFlag);
            hdr->headerLength = g_selfHdrLen;
            std::memcpy(g_stagedPacket + sizeof(MsgHdr), g_selfHdr, g_selfHdrLen);
            if (!msg.SerializeToArray(g_stagedPacket + sizeof(MsgHdr) + g_selfHdrLen,
                                      static_cast<int>(bodyLen))) {
                return false;
            }

            g_stagedPacketLen = packetLen;
            g_staged = true;
            LOG_MISCCH_INFO("RichPresence: staged local persona update for appid={} bytes={}",
                            appId, packetLen);
            return true;
        }
    }

    bool HandleRecv(const uint8* pBody, uint32 cbBody,
                    uint8* pOutBuf, uint32 outBufSize, uint32* pOutSize)
    {
        CMsgClientPersonaState msg;
        if (!msg.ParseFromArray(pBody, cbBody)) {
            LOG_MISCCH_WARN("RichPresence: failed to parse CMsgClientPersonaState");
            return false;
        }

        {
            std::lock_guard<std::mutex> guard(g_lock);
            CMsgClientPersonaState::Friend* self = nullptr;
            for (int i = 0; i < msg.friends_size(); ++i) {
                auto* f = msg.mutable_friends(i);
                if (f->has_friendid() && f->friendid() == g_selfSteamId) {
                    self = f;
                    break;
                }
            }
            if (self && cbBody <= sizeof(g_selfBody)) {
                std::memcpy(g_selfBody, pBody, cbBody);
                g_selfBodyLen = cbBody;
                g_hasSelfTemplate = g_selfHdrLen != 0;

                if (!SteamStubAuto::IsActive()
                    && g_visibleApp != 0) {
                    ApplyPresence(msg, self, g_visibleApp);
                    const uint32 sz = static_cast<uint32>(msg.ByteSizeLong());
                    if (sz <= outBufSize && msg.SerializeToArray(pOutBuf, static_cast<int>(outBufSize))) {
                        *pOutSize = sz;
                        LOG_MISCCH_INFO("RichPresence: refreshed local self state for appid={}", g_visibleApp);
                        return true;
                    }
                }
            }
        }

        AppId_t realAppId = SteamCapture::ResolveAppId();
        if (!realAppId) {
            LOG_MISCCH_TRACE("RichPresence: no realAppId (no -onlinefix active), skip");
            return false;
        }
        if (!LuaLoader::HasDepot(realAppId)) {
            LOG_MISCCH_TRACE("RichPresence: realAppId={} not in depot list, skip", realAppId);
            return false;
        }
        if (SteamStubAuto::IsActive()) {
            LOG_MISCCH_TRACE("RichPresence: steamstub-auto keeps persona on 480, skip");
            return false;
        }

        bool patched = false;
        int seen480 = 0;
        for (int i = 0; i < msg.friends_size(); ++i) {
            auto* f = msg.mutable_friends(i);
            if (static_cast<AppId_t>(f->game_played_app_id()) != kOnlineFixAppId)
                continue;
            ++seen480;

            std::string name = SteamCapture::GetGameNameByAppID(realAppId);
            f->set_game_played_app_id(realAppId);
            f->set_gameid(static_cast<uint64>(realAppId));
            if (!name.empty())
                f->set_game_name(name);

            LOG_MISCCH_INFO("RichPresence: patched friendid={} 480 -> {} ({})",
                          f->friendid(), realAppId, name);
            patched = true;
        }

        if (!patched) {
            LOG_MISCCH_TRACE("RichPresence: realAppId={} active, friends={} seen480={} (nothing to patch)",
                           realAppId, msg.friends_size(), seen480);
            return false;
        }

        uint32 sz = static_cast<uint32>(msg.ByteSizeLong());
        if (sz > outBufSize) {
            LOG_MISCCH_WARN("RichPresence: serialized size {} exceeds buffer {}", sz, outBufSize);
            return false;
        }
        if (!msg.SerializeToArray(pOutBuf, static_cast<int>(outBufSize))) {
            LOG_MISCCH_WARN("RichPresence: failed to SerializeToArray");
            return false;
        }

        *pOutSize = sz;
        return true;
    }

    void TrackGamesPlayed(const uint8* pBody, uint32 cbBody,
                          const uint8* pHdr, uint32 cbHdr)
    {
        CMsgClientGamesPlayed msg;
        if (!msg.ParseFromArray(pBody, cbBody))
            return;

        std::lock_guard<std::mutex> guard(g_lock);
        if (g_selfSteamId == 0) {
            CMsgProtoBufHeader hdr;
            if (hdr.ParseFromArray(pHdr, cbHdr) && hdr.has_steamid() && hdr.steamid()) {
                g_selfSteamId = hdr.steamid();
                if (cbHdr <= sizeof(g_selfHdr)) {
                    std::memcpy(g_selfHdr, pHdr, cbHdr);
                    g_selfHdrLen = cbHdr;
                }
                LOG_MISCCH_DEBUG("RichPresence: captured local steamid 0x{:X}", g_selfSteamId);
            }
        } else if (cbHdr <= sizeof(g_selfHdr)) {
            std::memcpy(g_selfHdr, pHdr, cbHdr);
            g_selfHdrLen = cbHdr;
        }

        AppId_t tailApp = 0;
        if (msg.games_played_size() > 0) {
            tailApp = static_cast<AppId_t>(
                msg.games_played(msg.games_played_size() - 1).game_id() & UINT32_MAX);
        }

        if (SteamStubAuto::IsActive()) {
            if (tailApp != 0 && tailApp != kOnlineFixAppId) {
                LOG_MISCCH_INFO("RichPresence: steamstub-auto suppressed local persona appid={}", tailApp);
            }
            return;
        }

        AppId_t next = 0;
        if (tailApp != 0 && tailApp != kOnlineFixAppId && LuaLoader::HasDepot(tailApp))
            next = tailApp;

        if (next == g_visibleApp)
            return;

        g_visibleApp = next;
        if (next == 0) {
            LOG_MISCCH_DEBUG("RichPresence: game stack no longer needs local persona update");
        } else {
            LOG_MISCCH_INFO("RichPresence: tracking local persona update for appid={}", next);
        }
        StagePersonaUpdate(next);
    }

    void TrackUpload(const uint8* pBody, uint32 cbBody)
    {
        CMsgClientRichPresenceUpload upload;
        if (!upload.ParseFromArray(pBody, cbBody) || !upload.has_rich_presence_kv())
            return;

        std::lock_guard<std::mutex> guard(g_lock);
        if (SteamStubAuto::IsActive()) {
            LOG_MISCCH_TRACE("RichPresence: steamstub-auto skipped rich presence upload");
            return;
        }
        if (g_visibleApp == 0)
            return;

        const std::string& rawKv = upload.rich_presence_kv();
        auto& kvs = g_uploadKvs[g_visibleApp];
        kvs.clear();
        CollectKvStrings(reinterpret_cast<const uint8*>(rawKv.data()),
                         static_cast<uint32>(rawKv.size()), kvs);
        LOG_MISCCH_DEBUG("RichPresence: captured {} kv pair(s) for appid={}",
                         kvs.size(), g_visibleApp);
        StagePersonaUpdate(g_visibleApp);
    }

    void DeliverPending(void* pThis, CNetPacket* pPacket,
                        bool (*callOriginal)(void*, CNetPacket*))
    {
        if (!pPacket || !callOriginal)
            return;

        uint8 staged[kPacketLimit];
        uint32 stagedLen = 0;
        {
            std::lock_guard<std::mutex> guard(g_lock);
            if (!g_staged || g_stagedPacketLen == 0)
                return;
            stagedLen = g_stagedPacketLen;
            std::memcpy(staged, g_stagedPacket, stagedLen);
            g_staged = false;
        }

        uint8* originalData = pPacket->m_pubData;
        uint32 originalSize = pPacket->m_cubData;
        pPacket->m_pubData = staged;
        pPacket->m_cubData = stagedLen;
        callOriginal(pThis, pPacket);
        pPacket->m_pubData = originalData;
        pPacket->m_cubData = originalSize;
        LOG_MISCCH_INFO("RichPresence: delivered staged persona packet bytes={}", stagedLen);
    }

}
