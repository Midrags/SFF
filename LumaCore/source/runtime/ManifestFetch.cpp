// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "ManifestFetch.h"
#include "Logger.h"
#include "RuntimeHttp.h"
#include "config/Settings.h"
#include "config/LuaLoader.h"

#include <charconv>
#include <cctype>
#include <chrono>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <thread>

// I keep the URL substitution dirt simple, three placeholders only.
// The two providers users actually point this thing at (wudrm, steam.run)
// give us either a plain decimal string or a JSON blob with one digit-string
// field. Any sane mirror copies one of those two formats so the parser
// here can stay inline.

namespace {

    std::mutex g_lock;
    std::map<uint64_t, std::shared_future<std::optional<uint64_t>>> g_pending;

    struct LookupKey {
        uint64_t gid = 0;
        uint32_t appId = 0;
        uint32_t depotId = 0;

        bool operator<(const LookupKey& other) const {
            if (gid != other.gid) return gid < other.gid;
            if (appId != other.appId) return appId < other.appId;
            return depotId < other.depotId;
        }
    };

    std::map<LookupKey, std::shared_future<std::optional<uint64_t>>> g_inflight;
    std::map<LookupKey, uint64_t> g_cache;

    std::shared_future<std::optional<uint64_t>> ReadyFuture(std::optional<uint64_t> value) {
        std::promise<std::optional<uint64_t>> p;
        p.set_value(value);
        return p.get_future().share();
    }

    bool ParseDigitsOnly(std::string_view body, uint64_t* out) {
        if (body.empty()) return false;
        // skip CR/LF and stray spaces some endpoints add
        size_t b = 0, e = body.size();
        while (b < e && (body[b] == ' ' || body[b] == '\r' || body[b] == '\n' || body[b] == '\t')) ++b;
        while (e > b && (body[e-1] == ' ' || body[e-1] == '\r' || body[e-1] == '\n' || body[e-1] == '\t')) --e;
        if (b == e) return false;
        for (size_t i = b; i < e; ++i)
            if (body[i] < '0' || body[i] > '9') return false;
        uint64_t v = 0;
        auto [_, ec] = std::from_chars(body.data() + b, body.data() + e, v);
        if (ec != std::errc{}) return false;
        *out = v;
        return true;
    }

    // Pulls the first digit-string out of a "content":"...." or
    // "code":"..." or "manifest_request_code":"..." JSON field. Order
    // is "longest tag first" so a body that has both content and code
    // takes content. No real JSON parser needed; the responses we care
    // about are always tiny scalars.
    bool ParseJsonDigitField(std::string_view body, uint64_t* out) {
        static constexpr std::string_view kKeys[] = {
            "\"manifest_request_code\"", "\"content\"", "\"code\"",
        };
        for (auto key : kKeys) {
            size_t k = body.find(key);
            if (k == std::string_view::npos) continue;
            size_t q1 = body.find('"', k + key.size());
            if (q1 == std::string_view::npos) continue;
            size_t q2 = body.find('"', q1 + 1);
            if (q2 == std::string_view::npos) continue;
            if (ParseDigitsOnly(body.substr(q1 + 1, q2 - q1 - 1), out))
                return true;
        }
        return false;
    }

    // Substitute {gid}/{appid}/{depotid} into the configured template.
    // Anything else is left as is so a future {branch} placeholder won't
    // explode the existing config.
    std::string ExpandTemplate(std::string_view tmpl,
                               uint64_t gid, uint32_t appId, uint32_t depotId) {
        std::string out;
        out.reserve(tmpl.size() + 32);
        for (size_t i = 0; i < tmpl.size(); ) {
            if (tmpl[i] != '{') { out.push_back(tmpl[i++]); continue; }
            size_t end = tmpl.find('}', i + 1);
            if (end == std::string_view::npos) { out.push_back(tmpl[i++]); continue; }
            std::string_view tag = tmpl.substr(i + 1, end - i - 1);
            if (tag == "gid")          out += std::to_string(gid);
            else if (tag == "appid")   out += std::to_string(appId);
            else if (tag == "depotid") out += std::to_string(depotId);
            else { out.append(tmpl.substr(i, end - i + 1)); }
            i = end + 1;
        }
        return out;
    }

    bool EqualsIgnoreCase(std::string_view a, std::string_view b) {
        if (a.size() != b.size()) return false;
        for (size_t i = 0; i < a.size(); ++i) {
            unsigned char ac = static_cast<unsigned char>(a[i]);
            unsigned char bc = static_cast<unsigned char>(b[i]);
            if (std::tolower(ac) != std::tolower(bc)) return false;
        }
        return true;
    }

    std::string_view ExtractHost(std::string_view url) {
        size_t begin = 0;
        size_t scheme = url.find("://");
        if (scheme != std::string_view::npos) begin = scheme + 3;
        size_t end = url.find_first_of("/?#", begin);
        std::string_view host = end == std::string_view::npos
            ? url.substr(begin)
            : url.substr(begin, end - begin);
        size_t at = host.rfind('@');
        if (at != std::string_view::npos) host.remove_prefix(at + 1);
        size_t port = host.find(':');
        if (port != std::string_view::npos) host = host.substr(0, port);
        return host;
    }

    bool UsesProviderCompatAgent(std::string_view url) {
        return EqualsIgnoreCase(ExtractHost(url), "manifest.opensteamtool.com");
    }

    std::optional<uint64_t> RunOnce(uint64_t gid, uint32_t appId, uint32_t depotId) {
        // try the Lua fetch_manifest_code functions first since they
        // let the plugin serve codes without any network at all
        if (LuaLoader::HasManifestCodeFuncEx()) {
            uint64_t code = LuaLoader::CallManifestFetchCodeEx(appId, depotId, gid);
            if (code != 0) {
                LOG_MANIFESTCH_INFO("ManifestFetch: gid={} resolved via Lua fetch_manifest_code_ex code={}", gid, code);
                return code;
            }
            LOG_MANIFESTCH_DEBUG("ManifestFetch: gid={} fetch_manifest_code_ex returned 0, falling through", gid);
        } else if (LuaLoader::HasManifestCodeFunc()) {
            uint64_t code = LuaLoader::CallManifestFetchCode(gid);
            if (code != 0) {
                LOG_MANIFESTCH_INFO("ManifestFetch: gid={} resolved via Lua fetch_manifest_code code={}", gid, code);
                return code;
            }
            LOG_MANIFESTCH_DEBUG("ManifestFetch: gid={} fetch_manifest_code returned 0, falling through", gid);
        }

        const auto& chain = Settings::manifestFetchUrls;
        if (chain.empty()) {
            LOG_MANIFESTCH_DEBUG("ManifestFetch: gid={} skipped, no providers configured", gid);
            return std::nullopt;
        }

        // Fall through the chain in order. First provider that returns a
        // 200 with a parseable code wins. Network failures, non-200, or
        // unparseable bodies just demote that provider for this lookup
        // and let the next one try. The per-provider attempt is bounded
        // by RuntimeHttp's own kTimeoutMs, so a slow first host doesn't
        // strand the depot indefinitely.
        for (size_t i = 0; i < chain.size(); ++i) {
            const std::string& tmpl = chain[i];
            if (tmpl.empty()) continue;
            std::string url = ExpandTemplate(tmpl, gid, appId, depotId);
            LOG_MANIFESTCH_INFO("ManifestFetch: gid={} provider {}/{} GET {}",
                                gid, i + 1, chain.size(), url);

            RuntimeHttp::Response resp{};
            for (int attempt = 0; attempt < 2; ++attempt) {
                resp = UsesProviderCompatAgent(url)
                    ? RuntimeHttp::Get(url, L"OpenSteamTool/1.0")
                    : RuntimeHttp::Get(url);
                if (!resp.networkError && resp.status == 429 && attempt == 0) {
                    LOG_MANIFESTCH_WARN("ManifestFetch: gid={} provider {} HTTP=429 "
                                        "body_bytes={}, retrying once",
                                        gid, i + 1, resp.body.size());
                    std::this_thread::sleep_for(std::chrono::milliseconds(750));
                    continue;
                }
                break;
            }
            if (resp.networkError) {
                LOG_MANIFESTCH_WARN("ManifestFetch: gid={} provider {} net err '{}', "
                                    "trying next", gid, i + 1, resp.diagnostic);
                continue;
            }
            if (resp.status != 200) {
                LOG_MANIFESTCH_WARN("ManifestFetch: gid={} provider {} HTTP={} "
                                    "body_bytes={}, trying next",
                                    gid, i + 1, resp.status, resp.body.size());
                continue;
            }
            uint64_t code = 0;
            if (ParseDigitsOnly(resp.body, &code)
             || ParseJsonDigitField(resp.body, &code))
            {
                LOG_MANIFESTCH_INFO("ManifestFetch: gid={} resolved code={} via provider {}",
                                    gid, code, i + 1);
                return code;
            }
            LOG_MANIFESTCH_WARN("ManifestFetch: gid={} provider {} body unparseable "
                                "(first 64: '{}'), trying next",
                                gid, i + 1,
                                std::string_view(resp.body).substr(0, 64));
        }

        LOG_MANIFESTCH_WARN("ManifestFetch: gid={} all {} providers exhausted",
                            gid, chain.size());
        return std::nullopt;
    }
}

namespace ManifestFetch {

    void Submit(uint64_t jobId, uint64_t manifestGid,
                uint32_t appId, uint32_t depotId)
    {
        LookupKey key{manifestGid, appId, depotId};
        std::shared_future<std::optional<uint64_t>> fut;
        std::lock_guard<std::mutex> lock(g_lock);
        if (g_pending.count(jobId)) {
            LOG_MANIFESTCH_DEBUG("ManifestFetch: duplicate Submit for jobId={}", jobId);
            return;
        }

        if (auto cached = g_cache.find(key); cached != g_cache.end()) {
            LOG_MANIFESTCH_INFO("ManifestFetch: jobId={} gid={} using cached code={}",
                                jobId, manifestGid, cached->second);
            g_pending.emplace(jobId, ReadyFuture(cached->second));
            return;
        }

        if (auto inflight = g_inflight.find(key); inflight != g_inflight.end()) {
            LOG_MANIFESTCH_INFO("ManifestFetch: jobId={} gid={} joined in-flight lookup",
                                jobId, manifestGid);
            g_pending.emplace(jobId, inflight->second);
            return;
        }

        auto promise = std::make_shared<std::promise<std::optional<uint64_t>>>();
        fut = promise->get_future().share();
        g_inflight.emplace(key, fut);
        g_pending.emplace(jobId, fut);

        std::thread([key, promise]() {
            std::optional<uint64_t> result = RunOnce(key.gid, key.appId, key.depotId);
            {
                std::lock_guard<std::mutex> lock(g_lock);
                if (result.has_value()) {
                    g_cache[key] = *result;
                }
                g_inflight.erase(key);
            }
            promise->set_value(result);
        }).detach();
    }

    std::optional<uint64_t> Resolve(uint64_t jobId) {
        std::shared_future<std::optional<uint64_t>> fut;
        {
            std::lock_guard<std::mutex> lock(g_lock);
            auto it = g_pending.find(jobId);
            if (it == g_pending.end()) return std::nullopt;
            fut = it->second;
            g_pending.erase(it);
        }
        const int budget = Settings::manifestFetchTimeoutSec > 0
                         ? Settings::manifestFetchTimeoutSec : 12;
        if (fut.wait_for(std::chrono::seconds(budget)) != std::future_status::ready) {
            LOG_MANIFESTCH_WARN("ManifestFetch: jobId={} timed out after {}s", jobId, budget);
            return std::nullopt;
        }
        return fut.get();
    }

    void Discard(uint64_t jobId) {
        std::lock_guard<std::mutex> lock(g_lock);
        g_pending.erase(jobId);
    }
}
