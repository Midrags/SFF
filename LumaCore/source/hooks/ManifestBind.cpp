#include "ManifestBind.h"
#include "Macros.h"
#include "entry.h"
#include <charconv>
#include <format>
#include <string>
#include <windows.h>
#include <winhttp.h>

#pragma comment(lib, "winhttp.lib")

// ═══════════════════════════════════════════════════════════════════
//  Manifest override hooks:
//    BuildDepotDependency — patches depot entries' gid/size directly
//      in the output vector.
// ═══════════════════════════════════════════════════════════════════
namespace {

    // ── helper ─────────────────────────────────────────────────────

    std::string DepotEntryDebug(const DepotEntry& e) {
        return std::format("DepotId={} AppId={} Gid={} Size={} Dlc={} Lcs={} Carry={} Shared={}",
            e.DepotId, e.AppId, e.ManifestGid, e.ManifestSize, e.DlcAppId,
            (int)e.LcsRequired, (int)e.bNotNewTarget, (int)e.SharedInstall);
    }

    // ── BuildDepotDependency hook ──────────────────────────────────
    // After Steam builds the depot list for an app, patch ManifestGid
    // and ManifestSize for any depots we have overrides for.

    HOOK_FUNC(BuildDepotDependency, bool, void* pUserAppMgr, AppId_t AppId,
              void* pUserConfig, CUtlVector<DepotEntry>* pDepotInfo,
              CUtlVector<DepotEntry>* pSharedDepotInfo, void* pSteamApp,
              uint32* pBuildId, bool* pbBetaFallback)
    {
        bool result = oBuildDepotDependency(pUserAppMgr, AppId, pUserConfig,
            pDepotInfo, pSharedDepotInfo, pSteamApp, pBuildId, pbBetaFallback);

        LOG_MANIFEST_TRACE("BuildDepotDependency: AppId={} pUserConfig=0x{:X} result={} pSteamApp=0x{:X} pBuildId={} pbBetaFallback={}",
            AppId, (uintptr_t)pUserConfig, result, (uintptr_t)pSteamApp,
            pBuildId ? *pBuildId : 0, pbBetaFallback ? *pbBetaFallback : false);
        if (pDepotInfo) {
            LOG_MANIFEST_TRACE("pDepotInfo->nCount={}", pDepotInfo->m_Size);
            for (uint32 i = 0; i < pDepotInfo->m_Size; ++i) {
                LOG_MANIFEST_TRACE("  [{}] {}", i, DepotEntryDebug(pDepotInfo->m_Memory.m_pMemory[i]));
            }
        }
        if (pSharedDepotInfo) {
            LOG_MANIFEST_TRACE("pSharedDepotInfo->nCount={}", pSharedDepotInfo->m_Size);
            for (uint32 i = 0; i < pSharedDepotInfo->m_Size; ++i) {
                LOG_MANIFEST_TRACE("  shared[{}] {}", i, DepotEntryDebug(pSharedDepotInfo->m_Memory.m_pMemory[i]));
            }
        }

        if (!result) return result;

        const auto& overrides = LuaLoader::GetManifestOverrides();
        if (overrides.empty()) return result;

        if (pDepotInfo && pDepotInfo->m_Size) {
            for (uint32 i = 0; i < pDepotInfo->m_Size; ++i) {
                DepotEntry& e = pDepotInfo->m_Memory.m_pMemory[i];
                auto it = overrides.find(e.DepotId);
                if (it != overrides.end()) {
                    // if size=0 in the override, keep the original size(affects download display but not the actual download)
                    uint64_t newSize = it->second.size ? it->second.size : e.ManifestSize;
                    LOG_MANIFEST_INFO("BuildDepotDependency: patching depot {} gid={}->{} size={}->{}",
                        e.DepotId, e.ManifestGid, it->second.gid,
                        e.ManifestSize, newSize);
                    e.ManifestGid  = it->second.gid;
                    e.ManifestSize = newSize;
                }
            }
        }
        return result;
    }

} // anonymous namespace

// ═══════════════════════════════════════════════════════════════════
//  Manifest request-code HTTP provider
//  Async-called from PacketRouter::Manifest::HandleSend to satisfy
//  ContentServerDirectory.GetManifestRequestCode#1 when the Steam
//  server rejects the request for config-managed apps.
// ═══════════════════════════════════════════════════════════════════
namespace {

    static bool FetchSteamRun(uint64_t manifest_gid, uint64_t* outRequestCode)
    {
        HINTERNET hSession = WinHttpOpen(L"LumaCore/1.0",
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        if (!hSession) return false;

        WinHttpSetTimeouts(hSession, 5000, 5000, 10000, 10000);

        HINTERNET hConnect = WinHttpConnect(hSession, L"manifest.steam.run",
            INTERNET_DEFAULT_HTTPS_PORT, 0);
        if (!hConnect) { WinHttpCloseHandle(hSession); return false; }

        wchar_t path[96];
        swprintf_s(path, L"/api/manifest/%llu", manifest_gid);

        HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", path,
            nullptr, WINHTTP_NO_REFERER,
            WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
        if (!hRequest) {
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return false;
        }

        bool success = false;
        if (WinHttpSendRequest(hRequest,
                WINHTTP_NO_ADDITIONAL_HEADERS, 0, nullptr, 0, 0, 0) &&
            WinHttpReceiveResponse(hRequest, nullptr))
        {
            DWORD statusCode = 0, sz = sizeof(statusCode);
            WinHttpQueryHeaders(hRequest,
                WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                WINHTTP_HEADER_NAME_BY_INDEX,
                &statusCode, &sz, WINHTTP_NO_HEADER_INDEX);

            LOG_MANIFEST_INFO("FetchSteamRun: gid={} HTTP {}", manifest_gid, statusCode);

            if (statusCode == 200) {
                std::string body;
                DWORD avail = 0;
                while (WinHttpQueryDataAvailable(hRequest, &avail) && avail) {
                    size_t off = body.size();
                    body.resize(off + avail);
                    DWORD nRead = 0;
                    if (!WinHttpReadData(hRequest,
                            body.data() + off, avail, &nRead)) break;
                    body.resize(off + nRead);
                    if (body.size() > 4096) break;
                }
                // Parse {"content":"CODE"}
                if (size_t kpos = body.find("\"content\""); kpos != std::string::npos) {
                    if (size_t q1 = body.find('"', kpos + 9); q1 != std::string::npos) {
                        if (size_t q2 = body.find('"', q1 + 1); q2 != std::string::npos) {
                            uint64_t code = 0;
                            auto [ptr, ec] = std::from_chars(
                                body.data() + q1 + 1,
                                body.data() + q2, code);
                            if (ec == std::errc{}) {
                                *outRequestCode = code;
                                success = true;
                            }
                        }
                    }
                }
            }
        }

        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return success;
    }

} // anonymous namespace

namespace ManifestBind {

    bool FetchManifestRequestCode(uint64_t manifestGid, uint64_t* outCode,
                                   uint32_t appId, uint32_t depotId)
    {
        LOG_MANIFEST_INFO("FetchManifestRequestCode: app={} depot={} gid={}",
                          appId, depotId, manifestGid);
        if (FetchSteamRun(manifestGid, outCode)) {
            LOG_MANIFEST_INFO("FetchManifestRequestCode: got code={} from manifest.steam.run",
                              *outCode);
            return true;
        }
        LOG_MANIFEST_WARN("FetchManifestRequestCode: manifest.steam.run failed for gid={}",
                          manifestGid);
        return false;
    }

    void Install() {
        HOOK_BEGIN();
        INSTALL_HOOK_D(BuildDepotDependency);
        HOOK_END();
    }

    void Uninstall() {
        UNHOOK_BEGIN();
        UNINSTALL_HOOK(BuildDepotDependency);
        UNHOOK_END();
    }
}
