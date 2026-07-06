// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/NetPacket.h"
#include "hooks/capture/SteamCapture.h"
#include "config/LuaLoader.h"
#include "core/entry.h"
#include "runtime/HookStatus.h"
#include "runtime/Logger.h"

#include <unordered_map>
#include <mutex>
#include <chrono>
#include <deque>

namespace NetPacket::Handlers::UserStats {

using Clock = std::chrono::steady_clock;

struct StatAttempt {
    AppId_t appId = 0;
    size_t poolIndex = 0;
    size_t poolCount = 0;
    uint64_t steamId = 0;
    uint64_t sequence = 0;
    Clock::time_point seen{};
};

std::unordered_map<uint64_t, StatAttempt> g_JobIdToAppId;
std::deque<StatAttempt> g_RecentPlayerStatsAttempts;
uint64_t g_NextPlayerStatsSequence = 1;
std::mutex g_PlayerStatsAttemptMutex;
std::unordered_map<AppId_t, StatAttempt> g_PendingClientStatsSpoof;
std::mutex g_PendingClientStatsSpoofMutex;
std::mutex g_StatsPoolMutex;
std::unordered_map<AppId_t, size_t> g_NextPoolIndexByApp;
std::unordered_map<AppId_t, size_t> g_PreferredPoolIndexByApp;

constexpr auto kPlayerAttemptWindow = std::chrono::seconds(15);
constexpr size_t kPlayerAttemptCap = 24;

struct PlayerAttemptResolve {
    bool matched = false;
    bool ambiguous = false;
    size_t candidates = 0;
    const char* source = "no-match";
    StatAttempt attempt{};
};

static bool IsOK(int32_t eresult) {
    return eresult == static_cast<int32_t>(k_EResultOK);
}

static bool HasStatsPayload(const CPlayer_GetUserStats_Response& resp) {
    return (resp.has_schema() && !resp.schema().empty()) || resp.stats_size() > 0;
}

static bool HasStatsPayload(const CMsgClientGetUserStatsResponse& resp) {
    return (resp.has_schema() && !resp.schema().empty())
        || resp.stats_size() > 0
        || resp.achievement_blocks_size() > 0;
}

static size_t DefaultPoolIndex(AppId_t appId, const uint64_t* pool, size_t poolCount) {
    uint64_t oldDefault = LuaLoader::GetStatSteamId(appId);
    for (size_t i = 0; i < poolCount; ++i) {
        if (pool[i] == oldDefault) return i;
    }
    return 0;
}

static uint64_t PickStatsSteamId(AppId_t appId, size_t& poolIndex, size_t& poolCount) {
    const uint64_t* pool = LuaLoader::GetStatSteamIdPool(appId, poolCount);
    if (!pool || poolCount == 0) {
        poolIndex = 0;
        poolCount = 1;
        return LuaLoader::GetStatSteamId(appId);
    }

    std::lock_guard<std::mutex> guard(g_StatsPoolMutex);
    auto preferred = g_PreferredPoolIndexByApp.find(appId);
    if (preferred != g_PreferredPoolIndexByApp.end() && preferred->second < poolCount) {
        poolIndex = preferred->second;
        return pool[poolIndex];
    }

    auto next = g_NextPoolIndexByApp.find(appId);
    poolIndex = (next != g_NextPoolIndexByApp.end() && next->second < poolCount)
        ? next->second : DefaultPoolIndex(appId, pool, poolCount);
    return pool[poolIndex];
}

static StatAttempt MakeAttempt(AppId_t appId) {
    StatAttempt attempt;
    attempt.appId = appId;
    attempt.seen = Clock::now();
    return attempt;
}

static uint64_t FillAttemptSteamId(StatAttempt& attempt) {
    attempt.steamId = PickStatsSteamId(attempt.appId, attempt.poolIndex, attempt.poolCount);
    return attempt.steamId;
}

static void EraseRecentPlayerAttemptLocked(uint64_t sequence) {
    for (auto it = g_RecentPlayerStatsAttempts.begin(); it != g_RecentPlayerStatsAttempts.end(); ) {
        if (it->sequence == sequence) {
            it = g_RecentPlayerStatsAttempts.erase(it);
        } else {
            ++it;
        }
    }
}

static void PrunePlayerAttemptsLocked(Clock::time_point now) {
    for (auto it = g_RecentPlayerStatsAttempts.begin(); it != g_RecentPlayerStatsAttempts.end(); ) {
        if (now - it->seen > kPlayerAttemptWindow) {
            it = g_RecentPlayerStatsAttempts.erase(it);
        } else {
            ++it;
        }
    }
    while (g_RecentPlayerStatsAttempts.size() > kPlayerAttemptCap)
        g_RecentPlayerStatsAttempts.pop_front();

    std::erase_if(g_JobIdToAppId, [&now](const auto& e) {
        return now - e.second.seen > std::chrono::seconds(30);
    });
}

static void RecordPlayerAttempt(StatAttempt attempt, bool hasJobId, uint64_t jobId) {
    auto now = Clock::now();
    attempt.seen = now;

    std::lock_guard<std::mutex> guard(g_PlayerStatsAttemptMutex);
    PrunePlayerAttemptsLocked(now);
    attempt.sequence = g_NextPlayerStatsSequence++;
    if (hasJobId)
        g_JobIdToAppId[jobId] = attempt;
    g_RecentPlayerStatsAttempts.push_back(attempt);

    LOG_PKTRT_DEBUG(
        "{{\"evt\":\"UserStats\",\"act\":\"track\",\"sub\":\"GetUserStats\",\"appId\":{},\"seq\":{},\"jobId\":{},\"hasJobId\":{},\"poolIndex\":{},\"poolCount\":{},\"steamId\":{}}}",
        attempt.appId, attempt.sequence, hasJobId ? jobId : 0, hasJobId ? "true" : "false",
        attempt.poolIndex, attempt.poolCount, attempt.steamId);
    HookStatus::RecordStatsState(attempt.appId, "Player.GetUserStats",
                                 attempt.poolIndex, attempt.poolCount,
                                 hasJobId ? "send-jobid" : "send-no-job",
                                 -1, "sent");
}

static PlayerAttemptResolve ResolvePlayerAttempt(const CMsgProtoBufHeader& hdrMsg) {
    PlayerAttemptResolve result;
    auto now = Clock::now();
    std::lock_guard<std::mutex> guard(g_PlayerStatsAttemptMutex);
    PrunePlayerAttemptsLocked(now);

    if (hdrMsg.has_jobid_target()) {
        uint64_t jobId = hdrMsg.jobid_target();
        auto it = g_JobIdToAppId.find(jobId);
        if (it != g_JobIdToAppId.end()) {
            result.matched = true;
            result.source = "jobid";
            result.attempt = it->second;
            g_JobIdToAppId.erase(it);
            EraseRecentPlayerAttemptLocked(result.attempt.sequence);
            return result;
        }
    }

    StatAttempt candidate;
    size_t count = 0;
    for (const auto& attempt : g_RecentPlayerStatsAttempts) {
        if (now - attempt.seen > kPlayerAttemptWindow)
            continue;
        candidate = attempt;
        ++count;
    }

    result.candidates = count;
    if (count == 1) {
        result.matched = true;
        result.source = "recent-fallback";
        result.attempt = candidate;
        EraseRecentPlayerAttemptLocked(candidate.sequence);
        std::erase_if(g_JobIdToAppId, [&candidate](const auto& e) {
            return e.second.sequence == candidate.sequence;
        });
        return result;
    }

    if (count > 1) {
        result.ambiguous = true;
        result.source = "ambiguous";
    }
    return result;
}

static void NoteAttemptResult(const StatAttempt& attempt, bool okWithData) {
    if (!attempt.appId || attempt.poolCount <= 1) return;

    std::lock_guard<std::mutex> guard(g_StatsPoolMutex);
    if (okWithData) {
        g_PreferredPoolIndexByApp[attempt.appId] = attempt.poolIndex;
        g_NextPoolIndexByApp[attempt.appId] = attempt.poolIndex;
        LOG_PKTRT_INFO("{{\"evt\":\"UserStats\",\"act\":\"pool\",\"result\":\"preferred\",\"appId\":{},\"index\":{},\"count\":{}}}",
                       attempt.appId, attempt.poolIndex, attempt.poolCount);
        return;
    }

    auto preferred = g_PreferredPoolIndexByApp.find(attempt.appId);
    if (preferred != g_PreferredPoolIndexByApp.end() && preferred->second == attempt.poolIndex) {
        g_PreferredPoolIndexByApp.erase(preferred);
    }
    g_NextPoolIndexByApp[attempt.appId] = (attempt.poolIndex + 1) % attempt.poolCount;
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"pool\",\"result\":\"advance\",\"appId\":{},\"from\":{},\"next\":{},\"count\":{}}}",
                    attempt.appId, attempt.poolIndex, g_NextPoolIndexByApp[attempt.appId], attempt.poolCount);
}

static bool WriteClientStatsOk(CMsgClientGetUserStatsResponse& resp,
                               AppId_t appId,
                               const char* reason) {
    resp.clear_stats();
    resp.clear_achievement_blocks();
    resp.clear_crc_stats();
    resp.set_eresult(static_cast<int32_t>(k_EResultOK));

    size_t newLen819 = resp.ByteSizeLong();
    if (newLen819 > kBodyCap) {
        LOG_PKTRT_WARN(
            "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"err\":\"overflow\",\"appId\":{},\"size\":{}}}",
            appId, newLen819);
        return false;
    }
    s_rx.BodyLen = static_cast<uint32_t>(newLen819);
    if (!resp.SerializeToArray(s_rx.Body, kBodyCap))
        return false;
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"normalized\":\"{}\",\"appId\":{},\"body\":{}}}",
                    reason, appId, resp.DebugString());
    return true;
}

bool HandleSend_GetUserStats(const uint8_t* pBody, uint32_t cbBody,
                             const uint8_t* pHdr, uint32_t cbHdr) {
    CPlayer_GetUserStats_Request req;
    if (!req.ParseFromArray(pBody, cbBody)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"err\":\"parse-fail\"}}}}");
        return false;
    }
    if (!req.has_appid()) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"err\":\"no-appid\"}}}}");
        return false;
    }

    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"original\":{}}}", req.DebugString());

    AppId_t appId = req.appid();
    AppId_t realAppId = SteamCapture::ResolveAppId();
    if (appId == kOnlineFixAppId
        && realAppId != 0
        && realAppId != kOnlineFixAppId) {
        LOG_PKTRT_INFO("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"redirect\":\"onlinefix\",\"was\":{},\"now\":{}}}",
                   appId, realAppId);
        appId = realAppId;
        req.set_appid(realAppId);
    }
    if (!LuaLoader::IsStatsManagedApp(appId)) {
        LOG_PKTRT_WARN("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"err\":\"no-stats-root\",\"appId\":{}}}", appId);
        return false;
    }

    req.clear_sha_schema();
    StatAttempt attempt = MakeAttempt(appId);
    uint64_t newSteamId = FillAttemptSteamId(attempt);

    CMsgProtoBufHeader hdr;
    bool hasJobId = false;
    uint64_t jobId = 0;
    if (hdr.ParseFromArray(pHdr, cbHdr) && hdr.has_jobid_source()) {
        hasJobId = true;
        jobId = hdr.jobid_source();
        LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"job\":{},\"appId\":{}}}", jobId, appId);
    }
    RecordPlayerAttempt(attempt, hasJobId, jobId);

    req.set_steamid(newSteamId);
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"spoof\":{},\"appId\":{},\"poolIndex\":{},\"poolCount\":{}}}",
                    newSteamId, appId, attempt.poolIndex, attempt.poolCount);

    s_tx.BodyLen = static_cast<uint32_t>(req.ByteSizeLong());
    if (s_tx.BodyLen > kBodyCap) {
        LOG_PKTRT_WARN("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"err\":\"overflow\",\"size\":{}}}", s_tx.BodyLen);
        return false;
    }
    if (!req.SerializeToArray(s_tx.Body, kBodyCap)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"err\":\"encode-fail\"}}}}");
        return false;
    }

    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"GetUserStats\",\"modified\":{}}}", req.DebugString());
    return true;
}

void HandleRecv_GetUserStatsResponse(const uint8_t* pHdr, uint32_t cbHdr,
                                     const uint8_t* pBody, uint32_t cbBody) {
    CMsgProtoBufHeader hdrMsg;
    if (!hdrMsg.ParseFromArray(pHdr, cbHdr)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"err\":\"header-parse-fail\"}}}}");
        return;
    }
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"original-header\":{}}}", hdrMsg.DebugString());

    PlayerAttemptResolve resolved = ResolvePlayerAttempt(hdrMsg);
    StatAttempt attempt = resolved.attempt;
    AppId_t appId = attempt.appId;
    const int32_t originalResult = hdrMsg.has_eresult() ? hdrMsg.eresult() : -1;

    CPlayer_GetUserStats_Response resp;
    if (!resp.ParseFromArray(pBody, cbBody)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"err\":\"body-parse-fail\"}}}}");
        return;
    }
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"original-body\":{}}}", resp.DebugString());

    if (!resolved.matched || !LuaLoader::IsStatsManagedApp(appId)) {
        LOG_PKTRT_DEBUG(
            "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"skip\":\"{}\",\"candidates\":{},\"eresult\":{}}}",
            resolved.source, resolved.candidates, originalResult);
        HookStatus::RecordStatsState(0, "Player.GetUserStats", 0, 0,
                                     resolved.source, originalResult,
                                     resolved.ambiguous ? "ambiguous" : "skipped");
        return;
    }

    const bool okWithData = IsOK(originalResult) && HasStatsPayload(resp);
    NoteAttemptResult(attempt, okWithData);
    LOG_PKTRT_INFO(
        "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"match\":\"{}\",\"appId\":{},\"seq\":{},\"eresult\":{},\"poolIndex\":{},\"poolCount\":{}}}",
        resolved.source, appId, attempt.sequence, originalResult, attempt.poolIndex, attempt.poolCount);

    hdrMsg.set_eresult(static_cast<int32_t>(k_EResultOK));
    s_rx.HdrLen = static_cast<uint32_t>(hdrMsg.ByteSizeLong());
    if (s_rx.HdrLen > kHdrCap || !hdrMsg.SerializeToArray(s_rx.Hdr, kHdrCap))
        return;
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"modified-header\":{}}}", hdrMsg.DebugString());

    resp.clear_stats();
    size_t newLen147 = resp.ByteSizeLong();
    if (newLen147 > kBodyCap) {
        LOG_PKTRT_WARN(
            "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"err\":\"overflow\",\"appId\":{},\"size\":{}}}",
            appId, newLen147);
        return;
    }
    s_rx.BodyLen = static_cast<uint32_t>(newLen147);
    if (!resp.SerializeToArray(s_rx.Body, kBodyCap)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"err\":\"encode-fail\"}}}}");
        return;
    }
    s_rx.PatchHdr = true;
    s_rx.PatchBody = true;
    HookStatus::RecordStatsState(appId, "Player.GetUserStats",
                                 attempt.poolIndex, attempt.poolCount,
                                 resolved.source, originalResult,
                                 okWithData ? "ok-with-data-stripped" : "normalized-ok");

    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"GetUserStatsResp\",\"modified-body\":{}}}", resp.DebugString());
}

bool HandleSend_ClientGetUserStats(const uint8_t* pBody, uint32_t cbBody) {
    CMsgClientGetUserStats req;
    if (!req.ParseFromArray(pBody, cbBody)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"err\":\"parse-fail\"}}}}");
        return false;
    }
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"original\":{}}}", req.DebugString());

    if (!req.has_game_id()) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"err\":\"no-game-id\"}}}}");
        return false;
    }
    AppId_t appId = static_cast<AppId_t>(req.game_id());
    AppId_t realAppId = SteamCapture::ResolveAppId();
    if (appId == kOnlineFixAppId
        && realAppId != 0
        && realAppId != kOnlineFixAppId) {
        LOG_PKTRT_INFO(
            "{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"redirect\":\"onlinefix\",\"was\":{},\"now\":{}}}",
            appId, realAppId);
        appId = realAppId;
        req.set_game_id(realAppId);
    }
    if (!LuaLoader::IsStatsManagedApp(appId)) {
        LOG_PKTRT_WARN("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"err\":\"no-stats-root\",\"appId\":{}}}", appId);
        return false;
    }
    req.clear_crc_stats();
    req.set_schema_local_version(-1);

    StatAttempt attempt = MakeAttempt(appId);
    uint64_t newSteamId = FillAttemptSteamId(attempt);
    req.set_steam_id_for_user(newSteamId);
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"spoof\":{},\"appId\":{},\"poolIndex\":{},\"poolCount\":{}}}",
                    newSteamId, appId, attempt.poolIndex, attempt.poolCount);
    HookStatus::RecordStatsState(appId, "ClientGetUserStats",
                                 attempt.poolIndex, attempt.poolCount,
                                 "send-app-map", -1, "sent");

    {
        std::lock_guard<std::mutex> guard(g_PendingClientStatsSpoofMutex);
        auto now = Clock::now();
        std::erase_if(g_PendingClientStatsSpoof, [&now](const auto& e) {
            return now - e.second.seen > std::chrono::seconds(30);
        });
        g_PendingClientStatsSpoof[appId] = attempt;
    }

    s_tx.BodyLen = static_cast<uint32_t>(req.ByteSizeLong());
    if (s_tx.BodyLen > kBodyCap) {
        LOG_PKTRT_WARN("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"err\":\"overflow\",\"size\":{}}}", s_tx.BodyLen);
        return false;
    }
    if (!req.SerializeToArray(s_tx.Body, kBodyCap)) {
        LOG_PKTRT_WARN("{{{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"err\":\"encode-fail\"}}}}");
        return false;
    }

    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"send\",\"sub\":\"ClientGetUserStats\",\"modified\":{}}}", req.DebugString());
    return true;
}

bool HandleRecv_ClientGetUserStatsResponse(const uint8_t* pBody, uint32_t cbBody) {
    CMsgClientGetUserStatsResponse resp;
    if (!resp.ParseFromArray(pBody, cbBody))
        return false;
    LOG_PKTRT_DEBUG("{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"original\":{}}}", resp.DebugString());
    if (!resp.has_game_id()) {
        LOG_PKTRT_DEBUG("{{{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"skip\":\"no-game-id\"}}}}");
        return false;
    }
    AppId_t gameId = static_cast<AppId_t>(resp.game_id());
    AppId_t realAppId = SteamCapture::ResolveAppId();
    if (gameId == kOnlineFixAppId
        && realAppId != 0
        && realAppId != kOnlineFixAppId) {
        LOG_PKTRT_INFO(
            "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"redirect\":\"onlinefix\",\"was\":{},\"now\":{}}}",
            gameId, realAppId);
        gameId = realAppId;
    }
    if (!LuaLoader::IsStatsManagedApp(gameId)) {
        LOG_PKTRT_DEBUG("{{{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"skip\":\"no-stats-root\"}}}}");
        return false;
    }

    bool wasSpoofed = false;
    StatAttempt attempt;
    {
        std::lock_guard<std::mutex> guard(g_PendingClientStatsSpoofMutex);
        auto it = g_PendingClientStatsSpoof.find(gameId);
        if (it != g_PendingClientStatsSpoof.end()) {
            wasSpoofed = true;
            attempt = it->second;
            g_PendingClientStatsSpoof.erase(it);
        }
    }
    if (!wasSpoofed) {
        if (IsOK(resp.eresult())) {
            LOG_PKTRT_DEBUG(
                "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"skip\":\"not-spoofed-ok\",\"appId\":{}}}",
                gameId);
            HookStatus::RecordStatsState(gameId, "ClientGetUserStats", 0, 0,
                                         "not-spoofed", resp.eresult(),
                                         "ok-passthrough");
            return false;
        }
        LOG_PKTRT_INFO(
            "{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"fix\":\"not-spoofed-failure\",\"appId\":{},\"eresult\":{}}}",
            gameId, resp.eresult());
        HookStatus::RecordStatsState(gameId, "ClientGetUserStats", 0, 0,
                                     "not-spoofed", resp.eresult(),
                                     "not-spoofed-failure-normalized");
        return WriteClientStatsOk(resp, gameId, "not-spoofed-failure-normalized");
    }

    const bool okWithData = IsOK(resp.eresult()) && HasStatsPayload(resp);
    NoteAttemptResult(attempt, okWithData);
    HookStatus::RecordStatsState(gameId, "ClientGetUserStats",
                                 attempt.poolIndex, attempt.poolCount,
                                 "app-map", resp.eresult(),
                                 okWithData ? "ok-with-data-stripped" : "spoofed-normalized");
    LOG_PKTRT_DEBUG("{{{{\"evt\":\"UserStats\",\"act\":\"recv\",\"sub\":\"ClientGetUserStatsResp\",\"stripped\":1}}}}");
    return WriteClientStatsOk(resp, gameId, "spoofed");
}

} // namespace NetPacket::Handlers::UserStats
