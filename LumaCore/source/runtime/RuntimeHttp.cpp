// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "RuntimeHttp.h"
#include "Logger.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <string>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>

#pragma comment(lib, "winhttp.lib")

namespace {

    constexpr std::size_t kBodyCap   = 8u * 1024u * 1024u;
    constexpr DWORD       kTimeoutMs = 12'000;
    constexpr std::wstring_view kDefaultUserAgent = L"LumaCore-RuntimeHttp/1.0";

    std::wstring Utf8ToWide(std::string_view s) {
        if (s.empty()) return {};
        int needed = MultiByteToWideChar(CP_UTF8, 0, s.data(),
                                         static_cast<int>(s.size()),
                                         nullptr, 0);
        if (needed <= 0) return {};
        std::wstring out(static_cast<std::size_t>(needed), L'\0');
        MultiByteToWideChar(CP_UTF8, 0, s.data(),
                            static_cast<int>(s.size()),
                            out.data(), needed);
        return out;
    }

    struct Url {
        bool         https = true;
        std::wstring host;
        INTERNET_PORT port = INTERNET_DEFAULT_HTTPS_PORT;
        std::wstring pathAndQuery = L"/";
    };

    bool Parse(std::string_view raw, Url& out) {
        std::wstring w = Utf8ToWide(raw);
        if (w.empty()) return false;

        URL_COMPONENTSW uc{};
        uc.dwStructSize = sizeof(uc);
        wchar_t schemeBuf[16]{}; uc.lpszScheme = schemeBuf; uc.dwSchemeLength = 16;
        std::wstring hostBuf(256, L'\0'); uc.lpszHostName = hostBuf.data(); uc.dwHostNameLength = static_cast<DWORD>(hostBuf.size());
        std::wstring pathBuf(2048, L'\0'); uc.lpszUrlPath = pathBuf.data(); uc.dwUrlPathLength = static_cast<DWORD>(pathBuf.size());
        std::wstring extraBuf(2048, L'\0'); uc.lpszExtraInfo = extraBuf.data(); uc.dwExtraInfoLength = static_cast<DWORD>(extraBuf.size());

        if (!WinHttpCrackUrl(w.c_str(), 0, 0, &uc)) return false;

        std::wstring scheme(uc.lpszScheme, uc.dwSchemeLength);
        if (_wcsicmp(scheme.c_str(), L"https") == 0) {
            out.https = true;
            out.port  = uc.nPort ? uc.nPort : INTERNET_DEFAULT_HTTPS_PORT;
        } else if (_wcsicmp(scheme.c_str(), L"http") == 0) {
            out.https = false;
            out.port  = uc.nPort ? uc.nPort : INTERNET_DEFAULT_HTTP_PORT;
        } else {
            return false;
        }
        out.host.assign(uc.lpszHostName, uc.dwHostNameLength);

        std::wstring full;
        full.assign(uc.lpszUrlPath, uc.dwUrlPathLength);
        full.append(uc.lpszExtraInfo, uc.dwExtraInfoLength);
        out.pathAndQuery = full.empty() ? L"/" : std::move(full);
        return true;
    }

    struct WinHandle {
        HINTERNET h = nullptr;
        WinHandle() = default;
        explicit WinHandle(HINTERNET v) : h(v) {}
        ~WinHandle() { if (h) WinHttpCloseHandle(h); }
        WinHandle(const WinHandle&) = delete;
        WinHandle& operator=(const WinHandle&) = delete;
        operator HINTERNET() const { return h; }
        explicit operator bool() const { return h != nullptr; }
    };
}

namespace RuntimeHttp {

Response Get(std::string_view url, std::wstring_view userAgent) {
    Response r;
    Url parsed;
    if (!Parse(url, parsed)) {
        r.diagnostic = "url parse failed";
        return r;
    }

    std::wstring sessionUserAgent(userAgent.empty() ? kDefaultUserAgent : userAgent);
    WinHandle session(WinHttpOpen(sessionUserAgent.c_str(),
                                  WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                  WINHTTP_NO_PROXY_NAME,
                                  WINHTTP_NO_PROXY_BYPASS, 0));
    if (!session) {
        r.diagnostic = "WinHttpOpen failed";
        return r;
    }
    WinHttpSetTimeouts(session, kTimeoutMs, kTimeoutMs, kTimeoutMs, kTimeoutMs);

    WinHandle conn(WinHttpConnect(session, parsed.host.c_str(), parsed.port, 0));
    if (!conn) {
        r.diagnostic = "WinHttpConnect failed";
        return r;
    }

    DWORD reqFlags = parsed.https ? WINHTTP_FLAG_SECURE : 0u;
    WinHandle req(WinHttpOpenRequest(conn, L"GET", parsed.pathAndQuery.c_str(),
                                     nullptr, WINHTTP_NO_REFERER,
                                     WINHTTP_DEFAULT_ACCEPT_TYPES, reqFlags));
    if (!req) {
        r.diagnostic = "WinHttpOpenRequest failed";
        return r;
    }

    if (!WinHttpSendRequest(req, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                            WINHTTP_NO_REQUEST_DATA, 0, 0, 0)
        || !WinHttpReceiveResponse(req, nullptr))
    {
        r.diagnostic = "send/receive err=" + std::to_string(GetLastError());
        return r;
    }

    DWORD status = 0;
    DWORD statusSize = sizeof(status);
    if (!WinHttpQueryHeaders(req,
                             WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX, &status,
                             &statusSize, WINHTTP_NO_HEADER_INDEX)) {
        r.diagnostic = "status query failed";
        return r;
    }
    r.status = static_cast<int>(status);
    r.networkError = false;

    std::array<char, 32 * 1024> buf{};
    for (;;) {
        DWORD avail = 0;
        if (!WinHttpQueryDataAvailable(req, &avail)) {
            r.diagnostic = "data-avail query failed";
            r.networkError = true;
            r.body.clear();
            break;
        }
        if (avail == 0) break;
        while (avail > 0) {
            DWORD want = (avail < static_cast<DWORD>(buf.size()))
                       ? avail
                       : static_cast<DWORD>(buf.size());
            DWORD got = 0;
            if (!WinHttpReadData(req, buf.data(), want, &got)) {
                r.diagnostic = "read failed";
                r.networkError = true;
                r.body.clear();
                avail = 0;
                break;
            }
            if (got == 0) { avail = 0; break; }
            if (r.body.size() + got > kBodyCap) {
                r.diagnostic = "body cap reached";
                r.body.clear();
                r.networkError = true;
                avail = 0;
                break;
            }
            r.body.append(buf.data(), got);
            avail -= got;
        }
        if (r.networkError) break;
    }

    return r;
}

Response Post(std::string_view url, std::string_view body,
              const std::vector<std::string>& extraHeaders) {
    Response r;
    Url parsed;
    if (!Parse(url, parsed)) {
        r.diagnostic = "url parse failed";
        return r;
    }

    WinHandle session(WinHttpOpen(L"LumaCore-RuntimeHttp/1.0",
                                  WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                  WINHTTP_NO_PROXY_NAME,
                                  WINHTTP_NO_PROXY_BYPASS, 0));
    if (!session) {
        r.diagnostic = "WinHttpOpen failed";
        return r;
    }
    WinHttpSetTimeouts(session, kTimeoutMs, kTimeoutMs, kTimeoutMs, kTimeoutMs);

    WinHandle conn(WinHttpConnect(session, parsed.host.c_str(), parsed.port, 0));
    if (!conn) {
        r.diagnostic = "WinHttpConnect failed";
        return r;
    }

    DWORD reqFlags = parsed.https ? WINHTTP_FLAG_SECURE : 0u;
    WinHandle req(WinHttpOpenRequest(conn, L"POST", parsed.pathAndQuery.c_str(),
                                     nullptr, WINHTTP_NO_REFERER,
                                     WINHTTP_DEFAULT_ACCEPT_TYPES, reqFlags));
    if (!req) {
        r.diagnostic = "WinHttpOpenRequest failed";
        return r;
    }

    // Add extra headers
    std::wstring joinedHeaders;
    for (const auto& h : extraHeaders) {
        std::wstring wh = Utf8ToWide(h);
        if (!wh.empty()) {
            joinedHeaders += wh;
            joinedHeaders += L"\r\n";
        }
    }

    if (!WinHttpSendRequest(req,
                            joinedHeaders.empty() ? WINHTTP_NO_ADDITIONAL_HEADERS : joinedHeaders.c_str(),
                            static_cast<DWORD>(joinedHeaders.length()),
                            const_cast<void*>(static_cast<const void*>(body.data())),
                            static_cast<DWORD>(body.size()),
                            static_cast<DWORD>(body.size()), 0)
        || !WinHttpReceiveResponse(req, nullptr))
    {
        r.diagnostic = "send/receive err=" + std::to_string(GetLastError());
        return r;
    }

    DWORD status = 0;
    DWORD statusSize = sizeof(status);
    if (!WinHttpQueryHeaders(req,
                             WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX, &status,
                             &statusSize, WINHTTP_NO_HEADER_INDEX)) {
        r.diagnostic = "status query failed";
        return r;
    }
    r.status = static_cast<int>(status);
    r.networkError = false;

    std::array<char, 32 * 1024> buf{};
    for (;;) {
        DWORD avail = 0;
        if (!WinHttpQueryDataAvailable(req, &avail)) {
            r.diagnostic = "data-avail query failed";
            r.networkError = true;
            r.body.clear();
            break;
        }
        if (avail == 0) break;
        while (avail > 0) {
            DWORD want = (avail < static_cast<DWORD>(buf.size()))
                       ? avail
                       : static_cast<DWORD>(buf.size());
            DWORD got = 0;
            if (!WinHttpReadData(req, buf.data(), want, &got)) {
                r.diagnostic = "read failed";
                r.networkError = true;
                r.body.clear();
                avail = 0;
                break;
            }
            if (got == 0) { avail = 0; break; }
            if (r.body.size() + got > kBodyCap) {
                r.diagnostic = "body cap reached";
                r.body.clear();
                r.networkError = true;
                avail = 0;
                break;
            }
            r.body.append(buf.data(), got);
            avail -= got;
        }
        if (r.networkError) break;
    }

    return r;
}

} // namespace RuntimeHttp
