// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "PatternFetcher.h"

#include "core/entry.h"
#include "runtime/Logger.h"
#include "runtime/HookStatus.h"
#include "patterns/PatternSig.h"
#include "config/Settings.h"

#include <windows.h>
#include <bcrypt.h>
#include <psapi.h>
#include <winhttp.h>

#include <toml++/toml.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <chrono>
#include <vector>

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "winhttp.lib")

namespace PatternFetcher {

    // ── module-private state ────────────────────────────────────────────────

    namespace {

        constexpr std::size_t kMaxBodyBytes = 1u << 20;   // 1 MiB cap before parse
        constexpr DWORD       kHttpTimeoutMs = 10'000;     // 10-second WinHTTP timeout

        constexpr const char* kPrimaryHost = "raw.githubusercontent.com";
        constexpr const char* kCdnHost     = "cdn.jsdelivr.net";
        constexpr const char* kPrimaryPathPrefix = "/KoriaPolis/Steam-Auto-PT/pattern/";
        constexpr const char* kCdnPathPrefix     = "/gh/KoriaPolis/Steam-Auto-PT@pattern/";

        // gitflic mirror lives at midrags/steam-auto-pt on the pattern branch.
        // Per-file raw fetches are gated behind login on gitflic, so we go
        // through the public blob-info JSON API instead. The reply carries
        // the file body in a "blobLines" array — each line is one element
        // with a "body" field. Stitch them with '\n' to rebuild the TOML.
        // Tested URL form: /api/project/<owner>/<repo>/blob?file=<path>&branch=<branch>
        // The response is JSON with a top-level "blobLines": [{"body": ...}, ...].
        // No auth needed for public projects, ddos-guard cookies handled
        // automatically by WinHTTP because we don't keep a session.
        constexpr const char* kGitflicHost = "gitflic.ru";
        constexpr const char* kGitflicApiPrefix = "/api/project/midrags/steam-auto-pt/blob?branch=pattern&file=";

        // entries[subdir][name] -> Entry. The subdir key is a stable string view
        // into a small pool of "steamclient" / "steamui" literals, so we can
        // key the outer map by std::string without allocating per lookup.
        using EntryMap = std::unordered_map<std::string, Entry>;
        std::shared_mutex                        g_mapMutex;
        std::unordered_map<std::string, EntryMap> g_entries;

        // ── small byte/string helpers ───────────────────────────────────────

        std::string ToHexLower(const std::uint8_t* data, std::size_t len) {
            static const char kDigits[] = "0123456789abcdef";
            std::string out;
            out.resize(len * 2);
            for (std::size_t i = 0; i < len; ++i) {
                out[2 * i + 0] = kDigits[(data[i] >> 4) & 0xF];
                out[2 * i + 1] = kDigits[data[i] & 0xF];
            }
            return out;
        }

        // BCrypt-based SHA-256 over a file on disk, streaming in 1 MiB chunks.
        // Returns 64 lowercase hex chars on success, empty string on failure.
        std::string Sha256OfFile(const std::wstring& path) {
            HANDLE hFile = CreateFileW(path.c_str(), GENERIC_READ,
                                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                       nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (hFile == INVALID_HANDLE_VALUE) return {};

            BCRYPT_ALG_HANDLE  hAlg  = nullptr;
            BCRYPT_HASH_HANDLE hHash = nullptr;
            std::array<std::uint8_t, 32> digest{};
            std::vector<std::uint8_t> buf(1u << 20);
            std::string out;

            do {
                if (BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) != 0) break;
                if (BCryptCreateHash(hAlg, &hHash, nullptr, 0, nullptr, 0, 0) != 0)               break;

                bool ok = true;
                for (;;) {
                    DWORD got = 0;
                    if (!ReadFile(hFile, buf.data(), static_cast<DWORD>(buf.size()), &got, nullptr)) {
                        ok = false; break;
                    }
                    if (got == 0) break;
                    if (BCryptHashData(hHash, buf.data(), got, 0) != 0) { ok = false; break; }
                }
                if (!ok) break;
                if (BCryptFinishHash(hHash, digest.data(), static_cast<ULONG>(digest.size()), 0) != 0) break;

                out = ToHexLower(digest.data(), digest.size());
            } while (false);

            if (hHash) BCryptDestroyHash(hHash);
            if (hAlg)  BCryptCloseAlgorithmProvider(hAlg, 0);
            CloseHandle(hFile);
            return out;
        }

        std::string ResolveModuleDiskPath(HMODULE mod) {
            wchar_t buf[MAX_PATH] = {};
            DWORD n = GetModuleFileNameW(mod, buf, MAX_PATH);
            if (n == 0 || n == MAX_PATH) return {};
            // narrow conversion for log strings only; the hash uses the wide path.
            int needed = WideCharToMultiByte(CP_UTF8, 0, buf, -1, nullptr, 0, nullptr, nullptr);
            if (needed <= 0) return {};
            std::string out(static_cast<std::size_t>(needed - 1), '\0');
            WideCharToMultiByte(CP_UTF8, 0, buf, -1, out.data(), needed, nullptr, nullptr);
            return out;
        }

        std::wstring ResolveModuleDiskPathW(HMODULE mod) {
            wchar_t buf[MAX_PATH] = {};
            DWORD n = GetModuleFileNameW(mod, buf, MAX_PATH);
            if (n == 0 || n == MAX_PATH) return {};
            return std::wstring(buf, n);
        }

        std::wstring Utf8ToWide(std::string_view s) {
            if (s.empty()) return {};
            int needed = MultiByteToWideChar(CP_UTF8, 0, s.data(),
                                             static_cast<int>(s.size()), nullptr, 0);
            if (needed <= 0) return {};
            std::wstring out(static_cast<std::size_t>(needed), L'\0');
            MultiByteToWideChar(CP_UTF8, 0, s.data(),
                                static_cast<int>(s.size()), out.data(), needed);
            return out;
        }

        bool IEquals(std::string_view a, std::string_view b) {
            if (a.size() != b.size()) return false;
            for (std::size_t i = 0; i < a.size(); ++i) {
                if (std::tolower(static_cast<unsigned char>(a[i])) !=
                    std::tolower(static_cast<unsigned char>(b[i])))
                    return false;
            }
            return true;
        }

        // ── URL parsing ──────────────────────────────────────────────────────

        struct ParsedUrl {
            bool         https = true;
            std::wstring host;
            INTERNET_PORT port = INTERNET_DEFAULT_HTTPS_PORT;
            std::wstring pathAndQuery;
            std::string  scheme; // for logging
        };

        bool ParseUrl(std::string_view url, ParsedUrl& out) {
            std::string_view rest = url;
            if (rest.size() >= 8 && IEquals(rest.substr(0, 8), "https://")) {
                out.https = true; out.scheme = "https";
                out.port = INTERNET_DEFAULT_HTTPS_PORT;
                rest.remove_prefix(8);
            } else if (rest.size() >= 7 && IEquals(rest.substr(0, 7), "http://")) {
                out.https = false; out.scheme = "http";
                out.port = INTERNET_DEFAULT_HTTP_PORT;
                rest.remove_prefix(7);
            } else {
                return false;
            }
            std::size_t slash = rest.find('/');
            std::string hostPort(slash == std::string_view::npos ? rest : rest.substr(0, slash));
            std::string_view path = (slash == std::string_view::npos)
                                  ? std::string_view("/")
                                  : rest.substr(slash);

            std::size_t colon = hostPort.find(':');
            if (colon != std::string::npos) {
                // Port substring guard. stoi() throws on empty / non-numeric
                // and on values that don't fit a long. A pattern-repo host
                // with a malformed port (truncated mirror config, paste
                // accident, whatever) used to crash the worker thread because
                // the previous catch(...) was swallowing too much and the
                // INTERNET_PORT cast happened anyway in some clang builds.
                // Now: explicit invalid_argument / out_of_range catches plus
                // a manual 1..65535 fence. On any failure: drop the URL and
                // let the next fallback in the chain run.
                std::string portStr = hostPort.substr(colon + 1);
                hostPort.resize(colon);
                if (portStr.empty()) return false;
                long parsed = 0;
                try {
                    std::size_t consumed = 0;
                    parsed = std::stol(portStr, &consumed, 10);
                    if (consumed != portStr.size()) return false;
                } catch (const std::invalid_argument&) {
                    return false;
                } catch (const std::out_of_range&) {
                    return false;
                }
                if (parsed < 1 || parsed > 65535) return false;
                out.port = static_cast<INTERNET_PORT>(parsed);
            }
            if (hostPort.empty()) return false;
            out.host = Utf8ToWide(hostPort);
            out.pathAndQuery = Utf8ToWide(path);
            return true;
        }

        // ── WinHTTP GET ─────────────────────────────────────────────────────

        struct HttpResult {
            bool        netError = false;     // connect/DNS/timeout/other transport
            int         status   = 0;          // HTTP status when reached, 0 on net error
            std::string body;                 // capped at kMaxBodyBytes
            bool        bodyTooLarge = false;
            std::string note;                 // short error/diagnostic for logs
        };

        // Best-effort HTTPS GET with a hard 10-second total timeout and a 1 MiB
        // body cap. file:// URLs are handled separately (used for local mirror
        // testing per the design's manual integration test).
        HttpResult HttpGet(std::string_view url) {
            HttpResult r{};
            if (url.size() >= 7 && IEquals(url.substr(0, 7), "file://")) {
                std::string p(url.substr(7));
                if (p.size() >= 1 && p.front() == '/') p.erase(0, 1);
                std::wstring wp = Utf8ToWide(p);
                std::ifstream f(std::filesystem::path(wp), std::ios::binary);
                if (!f) { r.netError = true; r.note = "file open failed"; return r; }
                std::ostringstream oss; oss << f.rdbuf();
                std::string body = oss.str();
                if (body.size() > kMaxBodyBytes) {
                    r.bodyTooLarge = true; r.note = "body too large"; r.status = 200;
                    return r;
                }
                r.status = 200; r.body = std::move(body);
                return r;
            }

            ParsedUrl parsed{};
            if (!ParseUrl(url, parsed)) { r.netError = true; r.note = "bad url"; return r; }

            HINTERNET hSession = WinHttpOpen(L"LumaCore-PatternFetcher/1.0",
                                             WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                             WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
            if (!hSession) { r.netError = true; r.note = "WinHttpOpen failed"; return r; }

            WinHttpSetTimeouts(hSession,
                               static_cast<int>(kHttpTimeoutMs),
                               static_cast<int>(kHttpTimeoutMs),
                               static_cast<int>(kHttpTimeoutMs),
                               static_cast<int>(kHttpTimeoutMs));

            HINTERNET hConn = WinHttpConnect(hSession, parsed.host.c_str(), parsed.port, 0);
            if (!hConn) {
                r.netError = true; r.note = "WinHttpConnect failed";
                WinHttpCloseHandle(hSession); return r;
            }

            DWORD reqFlags = parsed.https ? WINHTTP_FLAG_SECURE : 0u;
            HINTERNET hReq = WinHttpOpenRequest(hConn, L"GET", parsed.pathAndQuery.c_str(),
                                                nullptr, WINHTTP_NO_REFERER,
                                                WINHTTP_DEFAULT_ACCEPT_TYPES, reqFlags);
            if (!hReq) {
                r.netError = true; r.note = "WinHttpOpenRequest failed";
                WinHttpCloseHandle(hConn); WinHttpCloseHandle(hSession); return r;
            }

            BOOL ok = WinHttpSendRequest(hReq,
                                         WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                                         WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
            if (ok) ok = WinHttpReceiveResponse(hReq, nullptr);

            if (!ok) {
                DWORD err = GetLastError();
                r.netError = true;
                r.note = "send/receive failed err=" + std::to_string(err);
                WinHttpCloseHandle(hReq); WinHttpCloseHandle(hConn); WinHttpCloseHandle(hSession);
                return r;
            }

            // status
            DWORD status = 0;
            DWORD szStatus = sizeof(status);
            if (!WinHttpQueryHeaders(hReq,
                                     WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                                     WINHTTP_HEADER_NAME_BY_INDEX, &status,
                                     &szStatus, WINHTTP_NO_HEADER_INDEX)) {
                r.netError = true; r.note = "query status failed";
                WinHttpCloseHandle(hReq); WinHttpCloseHandle(hConn); WinHttpCloseHandle(hSession);
                return r;
            }
            r.status = static_cast<int>(status);

            // body, capped
            r.body.reserve(64 * 1024);
            std::array<char, 16 * 1024> buf{};
            for (;;) {
                DWORD avail = 0;
                if (!WinHttpQueryDataAvailable(hReq, &avail)) {
                    r.netError = true; r.note = "query data failed"; r.body.clear(); break;
                }
                if (avail == 0) break;
                while (avail > 0) {
                    DWORD want = std::min<DWORD>(avail, static_cast<DWORD>(buf.size()));
                    DWORD got = 0;
                    if (!WinHttpReadData(hReq, buf.data(), want, &got)) {
                        r.netError = true; r.note = "read failed"; r.body.clear(); break;
                    }
                    if (got == 0) { avail = 0; break; }
                    if (r.body.size() + got > kMaxBodyBytes) {
                        r.bodyTooLarge = true; r.body.clear(); r.note = "body too large";
                        avail = 0; break;
                    }
                    r.body.append(buf.data(), got);
                    avail -= got;
                }
                if (r.netError || r.bodyTooLarge) break;
            }

            WinHttpCloseHandle(hReq);
            WinHttpCloseHandle(hConn);
            WinHttpCloseHandle(hSession);
            return r;
        }

        // ── TOML parsing ─────────────────────────────────────────────────────

        bool ParseRva(std::string_view s, std::uint32_t& out) {
            if (s.empty()) return false;
            std::size_t base = 0;
            std::string trimmed(s);
            // strip 0x / 0X prefix; accept plain hex
            if (trimmed.size() >= 2 && trimmed[0] == '0' &&
                (trimmed[1] == 'x' || trimmed[1] == 'X')) {
                trimmed.erase(0, 2);
            }
            if (trimmed.empty()) return false;
            try {
                unsigned long v = std::stoul(trimmed, &base, 16);
                if (base != trimmed.size()) return false;
                out = static_cast<std::uint32_t>(v);
                return true;
            } catch (...) { return false; }
        }

        bool ValidateSig(std::string_view s) {
            if (s.empty()) return false;
            // basic shape: hex pairs or "??", separated by whitespace/commas.
            bool sawByte = false;
            for (std::size_t i = 0; i < s.size(); ) {
                char c = s[i];
                if (c == ' ' || c == '\t' || c == ',') { ++i; continue; }
                if (i + 1 >= s.size()) return false;
                char a = s[i], b = s[i + 1];
                bool ok = (a == '?' && b == '?') ||
                          (std::isxdigit(static_cast<unsigned char>(a)) &&
                           std::isxdigit(static_cast<unsigned char>(b)));
                if (!ok) return false;
                sawByte = true;
                i += 2;
            }
            return sawByte;
        }

        // Parse a TOML body into name->Entry. Empty result means parse-fail.
        bool ParseToml(std::string_view body, EntryMap& out, std::string& err) {
            out.clear();
            err.clear();
            try {
                auto tbl = toml::parse(body);
                for (const auto& [key, node] : tbl) {
                    auto sub = node.as_table();
                    if (!sub) continue;
                    auto nameNode = (*sub)["name"].value<std::string>();
                    auto rvaNode  = (*sub)["rva"].value<std::string>();
                    auto sigNode  = (*sub)["sig"].value<std::string>();
                    if (!nameNode || !rvaNode || !sigNode) continue;
                    if (nameNode->empty() || rvaNode->empty() || sigNode->empty()) continue;

                    Entry e{};
                    if (!ParseRva(*rvaNode, e.rva)) {
                        err = "rva parse failed for " + *nameNode;
                        return false;
                    }
                    if (!ValidateSig(*sigNode)) {
                        err = "sig parse failed for " + *nameNode;
                        return false;
                    }
                    e.sig = *sigNode;
                    out.emplace(*nameNode, std::move(e));
                }
            } catch (const toml::parse_error& e) {
                std::ostringstream oss;
                oss << "toml parse: " << e.description() << " line "
                    << e.source().begin.line;
                err = oss.str();
                return false;
            } catch (...) {
                err = "toml parse: unknown";
                return false;
            }
            return !out.empty();
        }

        bool FillBuiltInSteamclientCurrent(std::string_view sha, EntryMap& out) {
            if (sha != "3f864358fcf50e49e0a8c6bb8e1bf175e381f5628e4cd4997a59ca5e3976afe5") {
                return false;
            }

            struct BuiltInEntry {
                const char* name;
                uint32_t rva;
                const char* sig;
            };
            static constexpr BuiltInEntry kEntries[] = {
                {"BBuildAndAsyncSendFrame", 0xD1DE90, "48 8B C4 55 48 8D 68 A1 48 81 EC C0 00 00 00 48 89 70 18"},
                {"BIsDlcEnabled", 0x71C050, "40 55 53 56 57 41 56 48 8B EC 48 83 EC ?? 4D 8B"},
                {"BUpdateAppOwnershipTicket", 0x725130, "48 89 5C 24 20 55 56 57 48 8B EC 48 83 EC ?? 41 0F B6 F8 8B"},
                {"BUpdateLicenses", 0xCEB00, "40 53 48 83 EC ?? 48 8B 05 ?? ?? ?? ?? 48 8B D9 C7 44 24 38"},
                {"BuildDepotDependency", 0x4B13A0, "48 8B C4 4C 89 48 20 89 50 10 48 89 48 08 55 57"},
                {"BuildSpawnEnvBlock", 0x9D4660, "4C 89 4C 24 20 4C 89 44 24 18 48 89 54 24 10 48 89 4C 24 08 55 53 56 57 41 54 41 55 41 56 41 57 48 8D AC 24 B8 FE FF FF"},
                {"CUtlBufferEnsureCapacity", 0xCD2480, "48 89 5C 24 08 57 48 83 EC 30 48 8B D9 8D 7A 01"},
                {"CUtlMemoryGrow", 0xE8280, "48 89 5C 24 10 57 48 83 EC 30 8B FA 48 8B D9 8B 51 08 8B 49 10 8D 04 39"},
                {"CheckAppOwnership", 0x9BBA20, "48 8B C4 89 50 10 48 89 48 08 55 53"},
                {"CloseAppCloud", 0xA1E450, "48 89 5C 24 10 57 48 83 EC 30 8B FA 48 8B D9 85 D2"},
                {"ConfigStoreGetBinary", 0x5B3870, "40 53 55 56 57 48 83 EC 38 48 63 FA 49 8B E9"},
                {"EvaluateRemoteStorageSyncState", 0x739DC0, "48 89 5C 24 08 48 89 74 24 20 57 48 83 EC ?? 41 0F B6 F8 8B DA 48 8B F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4C 24 30 45 33 C9 E8 ?? ?? ?? ??"},
                {"GetAppDataFromAppInfo", 0x4A2D70, "40 53 55 56 57 41 56 41 57 48 81 EC 78 01 00 00"},
                {"GetAppIDForCurrentPipe", 0x967600, "8B 81 30 0D 00 00 83 F8 FF 74 ??"},
                {"GetDecryptionKey", 0x9BEBC0, "40 53 55 56 57 48 81 EC 48 01 00 00 8B FA 48 8B"},
                {"GetOrAddAppData", 0x4A40B0, "48 83 EC 58 48 8B 05 ?? ?? ?? ?? 48 89 5C 24 68 48 89 6C 24 70"},
                {"GetPackageInfo", 0x4A4350, "48 89 5C 24 18 89 54 24 10 55 56 57 48 83 EC 20 44 8B 49 20"},
                {"GetPipeClient", 0x878500, "85 D2 74 ?? 44 0F B7 CA 44 3B 49 60"},
                {"GetRemoteStorageSyncState", 0x775880, "40 53 56 57 48 83 EC ?? 8B DA 48 8B F9 BA 40 00 00 00 48 8D 4C 24 30 45 33 C9 41 B8 20 00 00 00 E8 ?? ?? ?? ??"},
                {"GetSubscribedApps", 0x77CBA0, "48 89 5C 24 10 55 56 57 41 56 41 57 48 8B EC 48 83 EC ?? 41 0F B6 D9 41"},
                {"IPCProcessMessage", 0x877B10, "48 89 5C 24 18 48 89 6C 24 20 57 41 54 41 55 41 56 41 57 48 83 EC 30"},
                {"IsAppDlcInstalled", 0x820B40, "48 89 5C 24 20 55 56 57 48 8B EC 48 83 EC ?? 41 8B F8 8B DA 48 8B F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4D D0 45 33 C9 E8 ?? ?? ?? ?? B2 01 48 8D 4D D0 E8 ?? ?? ?? ?? B2 11 48 8D 4D D0 E8 ?? ?? ?? ?? 8B 46 08 48 8D 55 20 41 B8 04 00 00 00 89 45 20 48 8D 4D D0 E8 ?? ?? ?? ?? 41 B8 04 00 00 00 C7 45 20 71 8C"},
                {"IsCloudEnabledForApp", 0x8217E0, "40 53 56 57 48 83 EC ?? 8B DA 48 8B F9 BA 40 00 00 00 48 8D 4C 24 30 45 33 C9 41 B8 20 00 00 00 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? B2 0D 48 8D 4C 24 30 E8 ?? ?? ?? ?? 8B 47 08 48 8D 94 24 90 00 00 00 41 B8 04 00 00 00 89 84 24 90 00 00 00 48 8D 4C 24 30 E8 ?? ?? ?? ?? 41 B8 04 00 00 00 C7 84 24 90 00 00 00 90 27 A7 88"},
                {"IsUserSubscribedAppInTicket", 0x825400, "40 53 56 57 48 83 EC ?? 41 8B F8 48 8B DA 48 8B F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4C 24 30 45 33 C9 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? 8B 46 08 48 8D 94 24 80 00 00 00 41 B8 04 00 00 00 89 84 24 80 00 00 00 48 8D 4C 24 30 E8 ?? ?? ?? ?? 41 B8 04 00 00 00 C7 84 24 80 00 00 00 78 18 45 93"},
                {"KeyValues_FindOrCreateKey", 0xD01190, "48 8B C4 57 48 81 EC 50 04 00 00"},
                {"KeyValues_ReadAsBinary", 0xD03F40, "48 8B C4 44 88 48 20 55 48 8D 68 A9"},
                {"LoadDepotDecryptionKey", 0x5B3870, "40 53 55 56 57 48 83 EC 38 48 63 FA 49 8B E9"},
                {"LoadPackage", 0x49F5C0, "44 89 44 24 18 53 55 56 57 41 55"},
                {"MarkLicenseAsChanged", 0x9C8510, "48 89 5C 24 20 89 54 24 10 55 56 57 48 83 EC 20"},
                {"OptedInMask", 0x5DD630, "89 54 24 10 55 53 56 57 41 54 41 55 48 8D AC 24 38 FF FF FF"},
                {"PchMsgNameFromEMsg", 0xCFF050, "48 89 5C 24 08 57 48 83 EC 20 8B D9 E8 ?? ?? ?? ??"},
                {"ProcessPendingLicenseUpdates", 0x9B2010, "41 56 41 57 48 83 EC 38 83 B9 98 24 00 00 00"},
                {"RecvPkt", 0x596500, "48 8B C4 55 48 8D A8 98 F6 FF FF"},
                {"RequiresLegacyCDKey", 0x83C490, "48 89 5C 24 18 55 56 57 48 83 EC ?? 49 8B E8 ?? ?? ?? ?? F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4C 24 30 45 33 C9 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? B2 01 48 8D"},
                {"RunAutoCloudOnAppExit", 0x83EAD0, "48 89 5C 24 18 48 89 74 24 20 57 48 83 EC ?? 8B DA 48 8B F9 BA 40 00 00 00 48 8D 4C 24 30 45 33 C9 41 B8 20 00 00 00 E8 ?? ?? ?? ??"},
                {"RunAutoCloudOnAppLaunch", 0x83EC40, "48 89 5C 24 18 48 89 74 24 20 57 48 83 EC ?? 8B DA 48 8B F9 BA 40 00 00 00 48 8D 4C 24 30 45 33 C9 41 B8 20 00 00 00 E8 ?? ?? ?? ??"},
                {"SendCallbackToPipe", 0x96CB50, "48 89 5C 24 08 57 48 83 EC 30 41 8B D9 41 8B F8"},
                {"SpawnProcess", 0x9D5CA0, "48 89 5C 24 18 4C 89 4C 24 20 48 89 54 24 10 55 56 57 41 54 41 55 41 56 41 57 48 8D AC 24 30 FF FF FF"},
            };

            out.clear();
            for (const auto& builtIn : kEntries) {
                Entry e{};
                e.rva = builtIn.rva;
                e.sig = builtIn.sig;
                out.emplace(builtIn.name, std::move(e));
            }
            return !out.empty();
        }

        std::size_t MergeBuiltInSteamclientCurrent(std::string_view sha, EntryMap& out) {
            EntryMap builtIn;
            if (!FillBuiltInSteamclientCurrent(sha, builtIn))
                return 0;

            std::size_t added = 0;
            for (auto& pair : builtIn) {
                if (out.emplace(pair.first, std::move(pair.second)).second)
                    ++added;
            }
            return added;
        }

        // ── cache layout ────────────────────────────────────────────────────

        std::filesystem::path CacheDir() {
            // SteamInstallPath is the Steam root (folder containing steam.exe).
            // Per requirement 2.3 the cache is flat: <Steam>\lumacore\pattern\
            // <sha>.toml. The SHA is unique per module on disk so the steamui
            // and steamclient toml never collide on the same Steam build.
            std::filesystem::path root = SteamInstallPath;
            return root / "lumacore" / "pattern";
        }

        std::filesystem::path CachePath(const std::string& sha) {
            return CacheDir() / (sha + ".toml");
        }

        // Sweep surviving *.toml.tmp files in the subdir cache directory.
        // Called on every successful fetch into that dir per R3.7.
        void SweepStaleTemps(const std::filesystem::path& dir) {
            std::error_code ec;
            if (!std::filesystem::exists(dir, ec)) return;
            for (auto it = std::filesystem::directory_iterator(dir, ec);
                 !ec && it != std::filesystem::directory_iterator(); it.increment(ec))
            {
                if (!it->is_regular_file(ec)) continue;
                auto p = it->path();
                auto fn = p.filename().wstring();
                if (fn.size() >= 9 && fn.compare(fn.size() - 9, 9, L".toml.tmp") == 0) {
                    std::error_code rmEc;
                    std::filesystem::remove(p, rmEc);
                    if (rmEc) {
                        LOG_MISC_DEBUG("PatternFetcher: stale tmp sweep failed: {}",
                                       p.string());
                    } else {
                        LOG_MISC_DEBUG("PatternFetcher: removed stale tmp: {}",
                                       p.string());
                    }
                }
            }
        }

        // Atomic write: tmp + MoveFileExA(MOVEFILE_REPLACE_EXISTING).
        // Returns empty string on success, error description on failure.
        std::string WriteCacheAtomic(const std::string& sha,
                                     std::string_view body) {
            auto dir  = CacheDir();
            auto path = CachePath(sha);
            std::error_code ec;
            std::filesystem::create_directories(dir, ec);
            if (ec) return "create_directories: " + ec.message();

            auto tmpPath = path; tmpPath += ".tmp";
            {
                std::ofstream f(tmpPath, std::ios::binary | std::ios::trunc);
                if (!f) return "open tmp failed";
                f.write(body.data(), static_cast<std::streamsize>(body.size()));
                if (!f) return "write tmp failed";
                f.flush();
                if (!f) return "flush tmp failed";
            }
            // Drop the file handle before the rename.
            std::string narrowTmp  = tmpPath.string();
            std::string narrowPath = path.string();
            if (!MoveFileExA(narrowTmp.c_str(), narrowPath.c_str(),
                             MOVEFILE_REPLACE_EXISTING)) {
                DWORD err = GetLastError();
                std::error_code rmEc;
                std::filesystem::remove(tmpPath, rmEc);
                return "MoveFileExA err=" + std::to_string(err);
            }
            // R3.7 sweep on the same dir after a successful write.
            SweepStaleTemps(dir);
            return {};
        }

        // Read and parse the local cache. On parse error or open failure,
        // returns false and populates err so the caller can log the offending
        // body. Per requirement 2.5, an open failure on a present file is
        // surfaced through this same false-return path so LoadFor can fall
        // back to the network and re-write the cache.
        bool ReadCache(const std::string& sha,
                       EntryMap& out, std::string& err) {
            auto path = CachePath(sha);
            std::error_code ec;
            if (!std::filesystem::exists(path, ec)) { err = "cache miss"; return false; }
            std::ifstream f(path, std::ios::binary);
            if (!f) { err = "cache open failed"; return false; }
            std::ostringstream oss; oss << f.rdbuf();
            std::string body = oss.str();
            if (body.size() > kMaxBodyBytes) {
                err = "cache body too large"; return false;
            }
            return ParseToml(body, out, err);
        }

        // ── URL helpers ─────────────────────────────────────────────────────

        std::string BuildPrimaryUrl(const char* subdir, const std::string& sha) {
            std::string out = "https://";
            out += kPrimaryHost;
            out += kPrimaryPathPrefix;
            out += subdir;
            out += '/';
            out += sha;
            out += ".toml";
            return out;
        }

        std::string BuildCdnUrl(const char* subdir, const std::string& sha) {
            std::string out = "https://";
            out += kCdnHost;
            out += kCdnPathPrefix;
            out += subdir;
            out += '/';
            out += sha;
            out += ".toml";
            return out;
        }

        std::string BuildGitflicUrl(const char* subdir, const std::string& sha) {
            // gitflic wants the file path URL-encoded but their API tolerates
            // the bare slash — kept literal because every other character in
            // the file path is hex (lower a-f, 0-9). Saves a percent-encoder.
            std::string out = "https://";
            out += kGitflicHost;
            out += kGitflicApiPrefix;
            out += subdir;
            out += '/';
            out += sha;
            out += ".toml";
            return out;
        }

        // Glue the gitflic blobLines JSON back into the original file body.
        // The shape is a top-level JSON object with a "blobLines" array,
        // each element an object with a "body" string. Concatenate body
        // values with '\n' to reconstruct what the raw file looked like.
        // No real JSON parser; the response is simple enough that a manual
        // walk is faster and avoids dragging another dep into LumaCore.
        // Returns empty string on any structural surprise so the caller
        // demotes the gitflic leg without leaking malformed text into
        // ParseToml.
        std::string StitchGitflicBlobLines(std::string_view body) {
            constexpr std::string_view kKey = "\"blobLines\"";
            size_t k = body.find(kKey);
            if (k == std::string_view::npos) return {};
            size_t arrStart = body.find('[', k);
            if (arrStart == std::string_view::npos) return {};
            // walk array elements, pulling each object's "body" value
            std::string out;
            out.reserve(body.size() / 2);
            size_t pos = arrStart + 1;
            const std::string_view bodyKey = "\"body\"";
            while (pos < body.size()) {
                size_t bk = body.find(bodyKey, pos);
                if (bk == std::string_view::npos) break;
                // find the closing ] of the array; if bk is past it, stop
                size_t arrEnd = body.find(']', pos);
                if (arrEnd != std::string_view::npos && bk > arrEnd) break;
                size_t colon = body.find(':', bk + bodyKey.size());
                if (colon == std::string_view::npos) break;
                size_t q1 = body.find('"', colon);
                if (q1 == std::string_view::npos) break;
                // walk through the JSON-encoded string, honouring \" escapes
                std::string line;
                line.reserve(64);
                bool escaped = false;
                size_t p = q1 + 1;
                for (; p < body.size(); ++p) {
                    char c = body[p];
                    if (escaped) {
                        switch (c) {
                            case 'n': line.push_back('\n'); break;
                            case 't': line.push_back('\t'); break;
                            case 'r': line.push_back('\r'); break;
                            case '"': line.push_back('"');  break;
                            case '\\': line.push_back('\\'); break;
                            case '/': line.push_back('/');  break;
                            default:  line.push_back(c);    break;
                        }
                        escaped = false;
                        continue;
                    }
                    if (c == '\\') { escaped = true; continue; }
                    if (c == '"') break;
                    line.push_back(c);
                }
                if (p >= body.size()) break;
                if (!out.empty()) out.push_back('\n');
                out.append(line);
                pos = p + 1;
                if (out.size() > kMaxBodyBytes) break;
            }
            return out;
        }

        // Substitute {subdir} and {sha} placeholders in a user-mirror template.
        std::string ApplyMirrorTemplate(std::string_view tmpl,
                                        const char* subdir,
                                        const std::string& sha) {
            std::string out;
            out.reserve(tmpl.size() + 64);
            for (std::size_t i = 0; i < tmpl.size(); ) {
                if (tmpl[i] == '{') {
                    if (tmpl.compare(i, 8, "{subdir}") == 0) {
                        out.append(subdir); i += 8; continue;
                    }
                    if (tmpl.compare(i, 5, "{sha}") == 0) {
                        out.append(sha); i += 5; continue;
                    }
                }
                out.push_back(tmpl[i]); ++i;
            }
            return out;
        }

        // Install a parsed map into the global table under exclusive lock.
        void InstallEntries(const char* subdir, EntryMap&& map) {
            std::unique_lock lk(g_mapMutex);
            g_entries[subdir] = std::move(map);
        }

        // Convert the internal EntryMap into the public TomlEntry vector that
        // the entry.cpp orchestration plumbs through HookStatus. The internal
        // map keeps the sig bytes for prologue verification inside Resolve;
        // the public vector only carries name + rva because the consumer only
        // needs to enumerate the resolved hook addresses.
        std::vector<TomlEntry> ToPublicEntries(const EntryMap& map) {
            std::vector<TomlEntry> out;
            out.reserve(map.size());
            for (const auto& [name, e] : map) {
                TomlEntry te{};
                te.name = name;
                te.rva  = e.rva;
                te.sig  = e.sig;
                out.push_back(std::move(te));
            }
            return out;
        }

        // Last-known PatternResult per module handle. entry.cpp passes the
        // module to Get() to retrieve the SHA + parsed entries after LoadFor
        // or LoadCachedSync ran for that module. Hook installer macros also
        // consult this for the ok flag before calling MH_CreateHook.
        std::shared_mutex                              g_resultMutex;
        std::unordered_map<HMODULE, PatternResult>     g_lastResult;
        const PatternResult                             g_emptyResult{};

        void StoreResult(HMODULE module, const PatternResult& r) {
            if (!module) return;
            std::unique_lock lk(g_resultMutex);
            g_lastResult[module] = r;
        }

    } // anonymous namespace

    // ── public surface ──────────────────────────────────────────────────────

    const char* SourceToStr(Source s) {
        switch (s) {
            case Source::None:       return "none";
            case Source::UserMirror: return "user-mirror";
            case Source::Github:     return "github";
            case Source::Cdn:        return "cdn";
            case Source::Gitflic:    return "gitflic";
            case Source::Cache:      return "cache";
        }
        return "?";
    }

    std::optional<Entry> Lookup(const char* subdir, const char* funcName) {
        if (!subdir || !funcName) return std::nullopt;
        std::shared_lock lk(g_mapMutex);
        auto it = g_entries.find(subdir);
        if (it == g_entries.end()) return std::nullopt;
        auto eit = it->second.find(funcName);
        if (eit == it->second.end()) return std::nullopt;
        return eit->second;
    }

    namespace {
        // Hook installers like KVHooks pass bare identifiers (`ReadAsBinary`,
        // `FindOrCreateKey`) to Resolve. Older TOMLs the analyzer emitted
        // carry the namespaced key (`KeyValues_ReadAsBinary`). Try the bare
        // name first, then fall back to the `KeyValues_<name>` form so
        // already-uploaded pattern files keep working.
        std::optional<Entry> LookupWithAlias(const char* subdir, const char* funcName) {
            auto entry = Lookup(subdir, funcName);
            if (entry.has_value()) return entry;

            static constexpr const char* kPrefixed[] = {
                "ReadAsBinary",
                "FindOrCreateKey",
            };
            for (const char* legacy : kPrefixed) {
                if (std::strcmp(funcName, legacy) == 0) {
                    std::string key = "KeyValues_";
                    key += funcName;
                    return Lookup(subdir, key.c_str());
                }
            }
            return std::nullopt;
        }

        // Parses "AA BB ?? CC" into byte/mask vectors. Whitespace and commas
        // separate tokens; "??" is a wildcard. Returns false on any malformed
        // token so the caller can refuse the entry.
        bool ParseTomlSig(const char* str, std::vector<std::uint8_t>& bytes,
                          std::vector<std::uint8_t>& mask) {
            bytes.clear();
            mask.clear();
            auto hex = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                return -1;
            };
            for (const char* p = str; *p; ) {
                if (*p == ' ' || *p == '\t' || *p == ',') { ++p; continue; }
                if (p[0] == '?' && p[1] == '?') {
                    bytes.push_back(0);
                    mask.push_back(0);
                    p += 2;
                    continue;
                }
                int hi = hex(p[0]);
                int lo = hex(p[1]);
                if (hi < 0 || lo < 0) return false;
                bytes.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
                mask.push_back(1);
                p += 2;
            }
            return !bytes.empty();
        }
    } // anonymous namespace

    void* Resolve(HMODULE module, const char* funcName) {
        if (!module || !funcName) return nullptr;

        const char* subdir = (module == diversion_hModule) ? "steamclient" : "steamui";
        auto entry = LookupWithAlias(subdir, funcName);
        if (!entry.has_value()) return nullptr;

        MODULEINFO modInfo{};
        if (!GetModuleInformation(GetCurrentProcess(), module, &modInfo, sizeof(MODULEINFO))) {
            LOG_WARN("PatternFetcher::Resolve {}: GetModuleInformation failed (err={})",
                     funcName, GetLastError());
            return nullptr;
        }

        const std::uint32_t imageSize = static_cast<std::uint32_t>(modInfo.SizeOfImage);
        const std::uint32_t rva       = entry->rva;

        std::vector<std::uint8_t> bytes, mask;
        if (!ParseTomlSig(entry->sig.c_str(), bytes, mask)) {
            LOG_WARN("PatternFetcher::Resolve {}: TOML sig unparseable", funcName);
            return nullptr;
        }

        if (rva >= imageSize || bytes.size() > imageSize - rva) {
            LOG_WARN("PatternFetcher::Resolve {}: rva=0x{:X} outside module range "
                     "(size=0x{:X}, patLen={})",
                     funcName, rva, imageSize, bytes.size());
            return nullptr;
        }

        const auto* base      = static_cast<const std::uint8_t*>(modInfo.lpBaseOfDll);
        const auto* candidate = base + rva;

        // Position-fixed byte compare: the analyzer pinned the rva and
        // recorded the prologue bytes. If those bytes still live there, the
        // function is the right one. Wildcards in the sig let through tiny
        // build-to-build wobble (stack adjustments, register choices) without
        // moving the function entry itself.
        for (std::size_t j = 0; j < bytes.size(); ++j) {
            if (mask[j] && candidate[j] != bytes[j]) {
                LOG_WARN("PatternFetcher::Resolve {}: rva=0x{:X} sig mismatch",
                         funcName, rva);
                return nullptr;
            }
        }

        return const_cast<std::uint8_t*>(candidate);
    }

    void Reset() {
        std::unique_lock lk(g_mapMutex);
        g_entries.clear();
        std::unique_lock lk2(g_resultMutex);
        g_lastResult.clear();
    }

    const PatternResult& Get(HMODULE moduleHandle) {
        if (!moduleHandle) return g_emptyResult;
        std::shared_lock lk(g_resultMutex);
        auto it = g_lastResult.find(moduleHandle);
        if (it == g_lastResult.end()) return g_emptyResult;
        return it->second;
    }

    namespace {
        // Centralise the "did this body pass our signature gate" decision
        // so every leg of the fetch chain runs the same check. Returns
        // true when the caller can safely consume the body, false when
        // the leg must be demoted (and the next leg tried).
        //
        // sigUrl is body_url + ".sig". A 404 is treated as "no signature
        // shipped"; with require_signed=false that's accepted with a warn,
        // with require_signed=true it's a hard reject. Bad signatures are
        // always a hard reject regardless of the flag because that's the
        // tampering signal we actually care about.
        bool VerifyLegBody(const char* legLabel,
                           const char* subdir,
                           const std::string& bodyUrl,
                           std::string_view body)
        {
            std::string sigUrl = bodyUrl + ".sig";
            HttpResult sigResp = HttpGet(sigUrl);

            std::string_view sigBody;
            if (sigResp.status == 200 && !sigResp.netError && !sigResp.bodyTooLarge) {
                sigBody = sigResp.body;
            }
            // 404 / non-200 / network error all collapse to "no sig" and
            // PatternSig::Verify will return Missing.

            PatternSig::Result vr = PatternSig::Verify(body, sigBody);
            if (vr == PatternSig::Result::Ok) {
                return true;
            }

            const bool fatal = (vr == PatternSig::Result::BadSignature) ||
                               (vr == PatternSig::Result::InvalidShape) ||
                               Settings::patternRequireSigned;

            if (fatal) {
                LOG_PKGCH_WARN(
                    "PatternFetcher: {} leg for {} REJECTED, signature {} (require_signed={})",
                    legLabel, subdir, PatternSig::ResultToStr(vr),
                    Settings::patternRequireSigned ? "true" : "false");
                return false;
            }

            LOG_PKGCH_WARN(
                "PatternFetcher: {} leg for {} accepted UNSIGNED, signature {} "
                "(require_signed=false; flip to true once sigs ship)",
                legLabel, subdir, PatternSig::ResultToStr(vr));
            return true;
        }

        // Network fetch chain: user-mirror (optional) -> github primary -> cdn.
        // Returns the first body that fetched, parsed, AND signature-verified
        // cleanly. The caller owns the cache write so we can keep the parse
        // result and the body close together. fetchedBody is the raw TOML
        // text that landed; map is the parsed entry table the caller installs.
        bool FetchFromNetwork(const char* subdir, const std::string& sha,
                              std::string& fetchedBody, EntryMap& map,
                              Source& sourceOut, std::string& errOut)
        {
            sourceOut = Source::None;
            errOut.clear();

            // ── Step 0: optional user-mirror additive first try ─────────────
            if (!Settings::patternMirror.empty()) {
                std::string url = ApplyMirrorTemplate(Settings::patternMirror,
                                                      subdir, sha);
                HttpResult h = HttpGet(url);
                if (h.status == 200 && !h.bodyTooLarge && !h.netError && !h.body.empty()) {
                    if (!VerifyLegBody("user-mirror", subdir, url, h.body)) {
                        // sig rejected; fall through to github primary
                    } else {
                        std::string perr;
                        EntryMap parsed;
                        if (ParseToml(h.body, parsed, perr)) {
                            fetchedBody = std::move(h.body);
                            map         = std::move(parsed);
                            sourceOut   = Source::UserMirror;
                            return true;
                        }
                        LOG_MISC_DEBUG("PatternFetcher: user-mirror parse failed for {} ({}); "
                                       "falling through to github primary", subdir, perr);
                    }
                } else if (h.bodyTooLarge) {
                    LOG_MISC_DEBUG("PatternFetcher: user-mirror body >1MiB for {}; "
                                   "falling through to github primary", subdir);
                } else {
                    LOG_MISC_DEBUG("PatternFetcher: user-mirror failed for {} (status={} "
                                   "neterr={} note='{}'); falling through to github primary",
                                   subdir, h.status, h.netError ? 1 : 0, h.note);
                }
            }

            // ── Step 1: GitHub primary leg (with 404 short-circuit) ──────────
            bool primary404 = false;
            {
                std::string url = BuildPrimaryUrl(subdir, sha);
                HttpResult h = HttpGet(url);
                if (h.status == 200 && !h.bodyTooLarge && !h.netError && !h.body.empty()) {
                    if (!VerifyLegBody("github", subdir, url, h.body)) {
                        // sig rejected; fall through to cdn
                    } else {
                        std::string perr;
                        EntryMap parsed;
                        if (ParseToml(h.body, parsed, perr)) {
                            fetchedBody = std::move(h.body);
                            map         = std::move(parsed);
                            sourceOut   = Source::Github;
                            return true;
                        }
                        LOG_MISC_DEBUG("PatternFetcher: github primary parse failed for {} ({})",
                                       subdir, perr);
                    }
                } else if (h.status == 404) {
                    primary404 = true;
                }
            }

            // ── Step 2: jsDelivr CDN (skipped on primary 404) ────────────────
            if (!primary404) {
                std::string url = BuildCdnUrl(subdir, sha);
                HttpResult h = HttpGet(url);
                if (h.status == 200 && !h.bodyTooLarge && !h.netError && !h.body.empty()) {
                    if (!VerifyLegBody("cdn", subdir, url, h.body)) {
                        // sig rejected; fall through to gitflic
                    } else {
                        std::string perr;
                        EntryMap parsed;
                        if (ParseToml(h.body, parsed, perr)) {
                            fetchedBody = std::move(h.body);
                            map         = std::move(parsed);
                            sourceOut   = Source::Cdn;
                            return true;
                        }
                        LOG_MISC_DEBUG("PatternFetcher: cdn parse failed for {} ({})",
                                       subdir, perr);
                    }
                }
            }

            // ── Step 3: gitflic.ru fallback for blocked regions ──────────────
            // Hits the public blob-info JSON API and stitches blobLines back
            // into a TOML body before parsing. Skipped when github primary
            // returned 404 (means the file genuinely doesn't exist yet, not
            // a network issue) and when the user explicitly disables it.
            if (!primary404 && Settings::patternGitflicEnabled) {
                std::string url = BuildGitflicUrl(subdir, sha);
                HttpResult h = HttpGet(url);
                if (h.status == 200 && !h.bodyTooLarge && !h.netError && !h.body.empty()) {
                    std::string stitched = StitchGitflicBlobLines(h.body);
                    if (stitched.empty()) {
                        LOG_MISC_DEBUG("PatternFetcher: gitflic stitch failed for {} "
                                       "(body shape changed?)", subdir);
                    } else {
                        // gitflic publishes blobLines around the same body
                        // the maintainer signed, so the .sig sits next to
                        // the canonical TOML on github. Reuse the github
                        // primary URL for the .sig fetch so the gitflic
                        // mirror does not need its own sig endpoint.
                        std::string sigPeerUrl = BuildPrimaryUrl(subdir, sha);
                        if (!VerifyLegBody("gitflic", subdir, sigPeerUrl, stitched)) {
                            // sig rejected; bail out of the network chain
                        } else {
                            std::string perr;
                            EntryMap parsed;
                            if (ParseToml(stitched, parsed, perr)) {
                                fetchedBody = std::move(stitched);
                                map         = std::move(parsed);
                                sourceOut   = Source::Gitflic;
                                return true;
                            }
                            LOG_MISC_DEBUG("PatternFetcher: gitflic parse failed for {} ({})",
                                           subdir, perr);
                        }
                    }
                } else {
                    LOG_MISC_DEBUG("PatternFetcher: gitflic failed for {} (status={} "
                                   "neterr={} note='{}')",
                                   subdir, h.status, h.netError ? 1 : 0, h.note);
                }
            }

            errOut = "all network legs failed";
            return false;
        }
    } // anonymous namespace

    PatternResult LoadFor(HMODULE moduleHandle, const char* subdir) {
        PatternResult r{};
        r.source = "none";
        r.networkResult = "not-run";
        if (!moduleHandle || !subdir) return r;

        std::wstring diskPathW = ResolveModuleDiskPathW(moduleHandle);
        if (diskPathW.empty()) {
            LOG_MISC_DEBUG("PatternFetcher::LoadFor {}: GetModuleFileName failed", subdir);
            r.error = "module-path-failed";
            HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                            r.networkResult, r.error);
            return r;
        }

        r.sha = Sha256OfFile(diskPathW);
        if (r.sha.size() != 64) {
            LOG_MISC_DEBUG("PatternFetcher::LoadFor {}: sha256 failed", subdir);
            r.sha.clear();
            r.error = "sha256-failed";
            HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                            r.networkResult, r.error);
            return r;
        }

        // ── Cache-first per requirement 2.4 ────────────────────────────────
        // If <Steam>\lumacore\pattern\<sha>.toml exists at startup and parses,
        // skip the network entirely. ReadCache already treats an open failure
        // on a present file as a parse miss so requirement 2.5 can fall
        // through to the network path below.
        {
            EntryMap cmap; std::string cerr;
            if (ReadCache(r.sha, cmap, cerr)) {
                std::size_t merged = 0;
                if (IEquals(subdir, "steamclient"))
                    merged = MergeBuiltInSteamclientCurrent(r.sha, cmap);
                r.entries = ToPublicEntries(cmap);
                r.ok      = true;
                r.source  = "cache";
                r.cacheHit = true;
                r.networkResult = "skipped-cache";
                InstallEntries(subdir, std::move(cmap));
                StoreResult(moduleHandle, r);
                HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                                r.networkResult, r.error);
                LOG_MISC_DEBUG("PatternFetcher: {} cache hit sha={} entries={} mergedBuiltIns={}",
                               subdir, r.sha, static_cast<unsigned>(r.entries.size()),
                               static_cast<unsigned>(merged));
                return r;
            }
            r.error = cerr;
            LOG_MISC_DEBUG("PatternFetcher: {} cache miss/open-failed ({}); "
                           "falling through to network",
                           subdir, cerr);
        }

        {
            EntryMap builtIn;
            if (IEquals(subdir, "steamclient")
             && FillBuiltInSteamclientCurrent(r.sha, builtIn))
            {
                r.entries = ToPublicEntries(builtIn);
                r.ok      = true;
                r.source  = "built-in";
                r.networkResult = "skipped-built-in";
                InstallEntries(subdir, std::move(builtIn));
                StoreResult(moduleHandle, r);
                HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                                r.networkResult, r.error);
                LOG_MISC_WARN("PatternFetcher: {} built-in fallback sha={} entries={}",
                              subdir, r.sha, static_cast<unsigned>(r.entries.size()));
                return r;
            }
        }

        // ── Network fallback per requirements 2.2, 2.5, 2.6 ───────────────
        std::string body;
        EntryMap    map;
        Source      src   = Source::None;
        std::string fetchErr;
        if (!FetchFromNetwork(subdir, r.sha, body, map, src, fetchErr)) {
            r.networkResult = "failed";
            if (!r.error.empty()) r.error += "; ";
            r.error += fetchErr;
            LOG_MISC_DEBUG("PatternFetcher::LoadFor {}: {} (sha={})",
                           subdir, fetchErr, r.sha);
            StoreResult(moduleHandle, r);  // ok=false, sha set
            HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                            r.networkResult, r.error);
            return r;
        }

        // Persist to cache before parsing's consumer ships out, per
        // requirements 2.3 and 2.7. WriteCacheAtomic creates the parent
        // directory on demand.
        std::string werr = WriteCacheAtomic(r.sha, body);
        if (!werr.empty()) {
            LOG_MISC_DEBUG("PatternFetcher::LoadFor {}: cache write failed ({})",
                           subdir, werr);
            // Cache write is best-effort. A failed write does not invalidate
            // the parsed entries we already hold — the next session will
            // re-fetch from the network and try again.
        }

        std::size_t merged = 0;
        if (IEquals(subdir, "steamclient"))
            merged = MergeBuiltInSteamclientCurrent(r.sha, map);

        r.entries = ToPublicEntries(map);
        r.ok      = true;
        r.source  = SourceToStr(src);
        r.networkResult = "hit";
        r.error.clear();
        InstallEntries(subdir, std::move(map));
        StoreResult(moduleHandle, r);
        HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                        r.networkResult, r.error);

        LOG_MISC_DEBUG("PatternFetcher: {} network hit sha={} source={} entries={} mergedBuiltIns={}",
                       subdir, r.sha, SourceToStr(src),
                       static_cast<unsigned>(r.entries.size()),
                       static_cast<unsigned>(merged));
        return r;
    }

    PatternResult LoadForSteamUiDeferred() {
        // Wait briefly for steamui.dll to map; LoadModuleWithPath fires this
        // path the moment the loader resolves the module. Bail after a few
        // seconds so a stalled Steam install never wedges the worker.
        for (int i = 0; i < 100; ++i) {
            HMODULE ui = GetModuleHandleA("steamui.dll");
            if (ui) return LoadFor(ui, "steamui");
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        return PatternResult{};
    }

    PatternResult LoadCachedSync(HMODULE moduleHandle, const char* subdir) {
        PatternResult r{};
        if (!moduleHandle || !subdir) return r;

        std::wstring diskPathW = ResolveModuleDiskPathW(moduleHandle);
        if (diskPathW.empty()) return r;

        r.sha = Sha256OfFile(diskPathW);
        if (r.sha.size() != 64) {
            r.sha.clear();
            return r;
        }

        EntryMap cmap; std::string cerr;
        if (ReadCache(r.sha, cmap, cerr)) {
            if (IEquals(subdir, "steamclient"))
                (void)MergeBuiltInSteamclientCurrent(r.sha, cmap);
            r.entries = ToPublicEntries(cmap);
            r.ok      = true;
            r.source  = "cache";
            r.cacheHit = true;
            r.networkResult = "cache-only";
            InstallEntries(subdir, std::move(cmap));
            StoreResult(moduleHandle, r);
            HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                            r.networkResult, r.error);
            return r;
        }
        r.source = "none";
        r.networkResult = "cache-only";
        r.error = cerr;
        StoreResult(moduleHandle, r);  // cache miss: ok=false, sha set
        HookStatus::RecordPatternStatus(subdir, r.source, r.cacheHit,
                                        r.networkResult, r.error);
        return r;
    }

}
