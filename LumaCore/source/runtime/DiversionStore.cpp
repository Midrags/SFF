// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "runtime/DiversionStore.h"

#include "config/Settings.h"

#include <cstdint>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>

namespace DiversionStore {

    namespace {

        namespace fs = std::filesystem;

        constexpr int    kCopyRetries  = 25;
        constexpr DWORD  kRetryDelayMs = 120;
        constexpr size_t kHashChunk    = 1u << 20;

        constexpr uint32_t rotr(uint32_t v, unsigned n) {
            return (v >> n) | (v << (32 - n));
        }

        constexpr uint32_t kShaK[64] = {
            0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
            0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
            0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
            0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
            0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
            0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
            0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
            0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
            0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
            0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
            0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
            0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
            0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
            0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
            0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
            0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
        };

        class Sha256 {
        public:
            Sha256() { Reset(); }

            void Reset() {
                h_[0] = 0x6a09e667u; h_[1] = 0xbb67ae85u;
                h_[2] = 0x3c6ef372u; h_[3] = 0xa54ff53au;
                h_[4] = 0x510e527fu; h_[5] = 0x9b05688cu;
                h_[6] = 0x1f83d9abu; h_[7] = 0x5be0cd19u;
                total_ = 0;
                used_  = 0;
            }

            void Update(const uint8_t* data, size_t n) {
                total_ += n;
                while (n > 0) {
                    if (used_ == 0 && n >= sizeof(buf_)) {
                        Transform(data);
                        data += sizeof(buf_);
                        n    -= sizeof(buf_);
                        continue;
                    }
                    const size_t take = (n < sizeof(buf_) - used_)
                                            ? n : (sizeof(buf_) - used_);
                    std::memcpy(buf_ + used_, data, take);
                    used_ += take;
                    data  += take;
                    n     -= take;
                    if (used_ == sizeof(buf_)) {
                        Transform(buf_);
                        used_ = 0;
                    }
                }
            }

            std::string Final() {
                const uint64_t bitLen = total_ * 8ull;
                const uint8_t  pad    = 0x80;
                Update(&pad, 1);
                const uint8_t zero = 0;
                while (used_ != 56) Update(&zero, 1);
                uint8_t lenBytes[8];
                for (int i = 0; i < 8; ++i)
                    lenBytes[i] =
                        static_cast<uint8_t>(bitLen >> (56 - i * 8));
                Update(lenBytes, 8);

                static const char kHex[] = "0123456789abcdef";
                std::string out;
                out.reserve(64);
                for (int i = 0; i < 8; ++i)
                    for (int b = 3; b >= 0; --b) {
                        out += kHex[(h_[i] >> (b * 8 + 4)) & 0xF];
                        out += kHex[(h_[i] >> (b * 8)) & 0xF];
                    }
                return out;
            }

        private:
            void Transform(const uint8_t* p) {
                uint32_t w[64];
                for (int i = 0; i < 16; ++i)
                    w[i] = (static_cast<uint32_t>(p[i * 4])     << 24) |
                           (static_cast<uint32_t>(p[i * 4 + 1]) << 16) |
                           (static_cast<uint32_t>(p[i * 4 + 2]) <<  8) |
                            static_cast<uint32_t>(p[i * 4 + 3]);
                for (int i = 16; i < 64; ++i) {
                    const uint32_t s0 =
                        rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
                    const uint32_t s1 =
                        rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
                    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
                }
                uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3];
                uint32_t e = h_[4], f = h_[5], g = h_[6], h = h_[7];
                for (int i = 0; i < 64; ++i) {
                    const uint32_t S1  = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
                    const uint32_t ch  = (e & f) ^ (~e & g);
                    const uint32_t t1  = h + S1 + ch + kShaK[i] + w[i];
                    const uint32_t S0  = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
                    const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
                    const uint32_t t2  = S0 + maj;
                    h = g; g = f; f = e; e = d + t1;
                    d = c; c = b; b = a; a = t1 + t2;
                }
                h_[0] += a; h_[1] += b; h_[2] += c; h_[3] += d;
                h_[4] += e; h_[5] += f; h_[6] += g; h_[7] += h;
            }

            uint32_t h_[8];
            uint64_t total_;
            size_t   used_;
            uint8_t  buf_[64];
        };

        bool HashFile(const std::string& path, std::string* hexOut,
                      unsigned long long* sizeOut) {
            HANDLE h = CreateFileA(path.c_str(), GENERIC_READ,
                                   FILE_SHARE_READ | FILE_SHARE_WRITE |
                                       FILE_SHARE_DELETE,
                                   nullptr, OPEN_EXISTING,
                                   FILE_ATTRIBUTE_NORMAL, nullptr);
            if (h == INVALID_HANDLE_VALUE) return false;

            LARGE_INTEGER sz{};
            if (!GetFileSizeEx(h, &sz) || sz.QuadPart < 0) {
                CloseHandle(h);
                return false;
            }

            Sha256 sha;
            std::string chunk(kHashChunk, '\0');
            for (;;) {
                DWORD got = 0;
                if (!ReadFile(h, chunk.data(),
                              static_cast<DWORD>(chunk.size()), &got,
                              nullptr)) {
                    CloseHandle(h);
                    return false;
                }
                if (got == 0) break;
                sha.Update(reinterpret_cast<const uint8_t*>(chunk.data()),
                           got);
            }
            CloseHandle(h);

            if (hexOut)  *hexOut  = sha.Final();
            if (sizeOut) *sizeOut = static_cast<unsigned long long>(sz.QuadPart);
            return true;
        }

        enum class PublishKind { Published, LostRace, Failed };

        // Temp name carries pid + tick so simultaneous boots never share a
        // swap file. Losing the rename just means the other boot published
        // identical bytes first.
        PublishKind PublishArtifact(const char* steamclientPath,
                                    const fs::path& binDir,
                                    const std::string& shortHash) {
            const fs::path finalPath =
                binDir / ("lcoverlay-" + shortHash + ".dll");
            const fs::path temp =
                binDir / ("lcoverlay-" + shortHash + "-" +
                          std::to_string(GetCurrentProcessId()) + "-" +
                          std::to_string(GetTickCount()) + ".tmp");

            int attempts = 0;
            while (!CopyFileA(steamclientPath, temp.string().c_str(), FALSE)) {
                if (++attempts >= kCopyRetries) return PublishKind::Failed;
                Sleep(kRetryDelayMs);
            }

            if (!MoveFileExA(temp.string().c_str(), finalPath.string().c_str(),
                             MOVEFILE_REPLACE_EXISTING)) {
                DeleteFileA(temp.string().c_str());
                return PublishKind::LostRace;
            }
            return PublishKind::Published;
        }

        void PruneStaleArtifacts(const std::string& binDirStr,
                                 const std::string& keepName) {
            try {
                std::error_code ec;
                const fs::path binDir(binDirStr);
                for (fs::directory_iterator it(binDir, ec), end;
                     !ec && it != end; it.increment(ec)) {
                    if (ec) break;
                    const std::string name = it->path().filename().string();
                    if (name == keepName) continue;
                    if (name.rfind("lcoverlay", 0) != 0) continue;
                    if (name.size() <= 4 ||
                        (name.compare(name.size() - 4, 4, ".dll") != 0 &&
                         name.compare(name.size() - 4, 4, ".tmp") != 0))
                        continue;
                    // Fails on anything another process still maps.
                    DeleteFileA(it->path().string().c_str());
                }
            } catch (...) {
            }
        }

        DWORD WINAPI PruneThread(LPVOID param) {
            std::unique_ptr<std::string> work(
                static_cast<std::string*>(param));
            if (!work) return 0;
            Sleep(3000);
            const size_t sep = work->find('\n');
            if (sep == std::string::npos) return 0;
            PruneStaleArtifacts(work->substr(0, sep), work->substr(sep + 1));
            return 0;
        }

    }  // namespace

    bool Enabled() {
        char env[8] = {};
        const DWORD n = GetEnvironmentVariableA("LUMACORE_MULTIINSTANCE",
                                                env, sizeof(env));
        if (n > 0 && n < sizeof(env)) {
            if (env[0] == '0') return false;
            if (env[0] == '1') return true;
        }
        return Settings::diversionMultiInstance;
    }

    bool Prepare(const char* steamclientPath,
                 const char* steamInstallPath,
                 char* outArtifactPath, DWORD outArtifactCch,
                 std::string* outSourceSha) {
        if (!steamclientPath || !steamInstallPath ||
            !outArtifactPath || outArtifactCch == 0)
            return false;

        std::error_code ec;
        const fs::path binDir = fs::path(steamInstallPath) / "bin";
        fs::create_directories(binDir, ec);
        if (ec) return false;

        std::string srcSha;
        unsigned long long srcSize = 0;
        if (!HashFile(steamclientPath, &srcSha, &srcSize))
            return false;

        const std::string shortHash = srcSha.substr(0, 16);
        const fs::path finalPath =
            binDir / ("lcoverlay-" + shortHash + ".dll");

        // Re-hash whatever sits at the final path: reuses it only when it
        // really is a copy of the live source dll, republishes otherwise.
        auto validExisting = [&]() -> bool {
            std::string curSha;
            unsigned long long curSize = 0;
            if (!HashFile(finalPath.string(), &curSha, &curSize))
                return false;
            return curSize == srcSize && curSha == srcSha;
        };

        if (!validExisting())
            PublishArtifact(steamclientPath, binDir, shortHash);

        if (!validExisting())
            return false;

        strncpy_s(outArtifactPath, outArtifactCch,
                  finalPath.string().c_str(), _TRUNCATE);
        if (outSourceSha) *outSourceSha = srcSha;
        return true;
    }

    void StartDeferredPrune(const char* steamInstallPath,
                            const char* currentArtifactPath) {
        if (!steamInstallPath || !currentArtifactPath) return;
        const std::string binDir =
            (fs::path(steamInstallPath) / "bin").string();
        auto work = new std::string(binDir + "\n" + currentArtifactPath);
        HANDLE h = CreateThread(nullptr, 0, PruneThread, work, 0, nullptr);
        if (!h) {
            delete work;
            return;
        }
        CloseHandle(h);
    }

}  // namespace DiversionStore
