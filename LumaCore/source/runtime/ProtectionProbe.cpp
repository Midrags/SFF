// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "ProtectionProbe.h"

#include "runtime/ClockMark.h"
#include "runtime/Logger.h"
#include "RemoteTools.h"
#include "Ticket.h"

#include <windows.h>
#include <tlhelp32.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <cwctype>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {
    struct ProcessKey {
        uint32 pid = 0;
        uint64 creation = 0;

        bool operator==(const ProcessKey&) const = default;
    };

    struct ProcessKeyHash {
        std::size_t operator()(const ProcessKey& key) const noexcept {
            return (static_cast<std::size_t>(key.pid) << 1) ^
                   static_cast<std::size_t>(key.creation ^ (key.creation >> 32));
        }
    };

    enum class Method {
        None,
        LegacySectionName,
        LegacyTextMarker,
        OepTextMarker,
        EntryBindSection,
        TicketCacheHint,
    };

    std::mutex g_lock;
    std::unordered_map<ProcessKey, ProtectionProbe::ScanResult, ProcessKeyHash> g_results;

    struct FileScanCacheEntry {
        uint64 fileSize = 0;
        int64_t writeTicks = 0;
        uint64 bytesScanned = 0;
        Method method = Method::None;
    };

    std::unordered_map<std::wstring, FileScanCacheEntry> g_fileResults;

    constexpr std::array<std::string_view, 5> kLegacySections = {
        ".arch",
        ".srdata",
        ".xpdata",
        ".xdata",
        ".xtls",
    };

    constexpr std::array<unsigned char, 6> kLegacyText = {
        'D', 'E', 'N', 'U', 'V', 'O',
    };

    constexpr std::array<unsigned char, 10> kOepText = {
        0x44, 0x4F, 0x44, 0x45, 0x4E, 0x55, 0x56, 0x4F, 0x44, 0x45,
    };

    constexpr std::array<unsigned char, 10> kOepMovText = {
        0x48, 0xB9, 0x44, 0x4F, 0x44, 0x45, 0x4E, 0x55, 0x56, 0x4F,
    };

    constexpr uint64 kPeScanLimit = 96ull * 1024ull * 1024ull;
    constexpr uint64 kLargeDllScanFloor = 80ull * 1024ull * 1024ull;

    constexpr std::array<std::string_view, 10> kSteamRuntimeDlls = {
        "steamclient.dll",
        "steamclient64.dll",
        "steam_api.dll",
        "steam_api64.dll",
        "tier0_s.dll",
        "tier0_s64.dll",
        "vstdlib_s.dll",
        "vstdlib_s64.dll",
        "gameoverlayrenderer.dll",
        "gameoverlayrenderer64.dll",
    };

    struct SectionRange {
        std::string name;
        uint32 virtualAddress = 0;
        uint32 virtualSize = 0;
        uint32 rawOffset = 0;
        uint32 rawSize = 0;
        uint32 characteristics = 0;

        bool ContainsRva(uint32 rva) const {
            uint32 span = (std::max)(virtualSize, rawSize);
            return span != 0 && rva >= virtualAddress && rva < virtualAddress + span;
        }
    };

    struct PeSnapshot {
        uint32 entryRva = 0;
        std::vector<SectionRange> sections;
    };

    struct ModuleCandidate {
        std::filesystem::path path;
        uint64 fileSize = 0;
        bool executable = false;
        size_t order = 0;
    };

    const char* MethodName(Method method) {
        switch (method) {
            case Method::LegacySectionName: return "legacy_section";
            case Method::LegacyTextMarker:  return "legacy_text";
            case Method::OepTextMarker:     return "oep_text";
            case Method::EntryBindSection:  return "entry_bind_section";
            case Method::TicketCacheHint:   return "ticket_cache_hint";
            default:                        return "none";
        }
    }

    bool IsRouteMethod(Method method) {
        return method == Method::EntryBindSection;
    }

    const char* RouteReason(Method method) {
        if (method == Method::None)
            return "none";
        return IsRouteMethod(method) ? "accepted" : "diagnostic-only";
    }

    std::string PathToUtf8(const std::filesystem::path& path);

    std::string LowerAscii(std::string value) {
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
            return static_cast<char>(std::tolower(ch));
        });
        return value;
    }

    bool EndsWith(std::string_view value, std::string_view suffix) {
        if (value.size() < suffix.size())
            return false;
        return LowerAscii(std::string(value.substr(value.size() - suffix.size()))) ==
               LowerAscii(std::string(suffix));
    }

    bool IsSteamRuntimeName(const std::filesystem::path& path) {
        const std::string name = LowerAscii(PathToUtf8(path.filename()));
        return std::ranges::find(kSteamRuntimeDlls, name) != kSteamRuntimeDlls.end();
    }

    bool StartsWithInsensitive(std::wstring_view value, std::wstring_view prefix) {
        if (prefix.empty() || value.size() < prefix.size())
            return false;
        for (size_t i = 0; i < prefix.size(); ++i) {
            if (std::towlower(value[i]) != std::towlower(prefix[i]))
                return false;
        }
        return true;
    }

    std::wstring NormalizeNativePrefix(std::filesystem::path path) {
        std::wstring text = path.native();
        std::replace(text.begin(), text.end(), L'/', L'\\');
        if (!text.empty() && text.back() != L'\\')
            text.push_back(L'\\');
        return text;
    }

    bool IsWindowsSystemPath(const std::filesystem::path& path) {
        wchar_t systemDir[MAX_PATH] = {};
        wchar_t windowsDir[MAX_PATH] = {};
        GetSystemDirectoryW(systemDir, MAX_PATH);
        GetWindowsDirectoryW(windowsDir, MAX_PATH);

        const std::wstring value = path.native();
        return StartsWithInsensitive(value, NormalizeNativePrefix(systemDir)) ||
               StartsWithInsensitive(value, NormalizeNativePrefix(windowsDir));
    }

    bool BytesContain(const std::vector<unsigned char>& bytes,
                      std::span<const unsigned char> needle) {
        if (needle.empty() || bytes.size() < needle.size())
            return false;
        return std::search(bytes.begin(), bytes.end(),
                           needle.begin(), needle.end()) != bytes.end();
    }

    bool BytesContain(std::span<const unsigned char> bytes,
                      std::span<const unsigned char> needle) {
        if (needle.empty() || bytes.size() < needle.size())
            return false;
        return std::search(bytes.begin(), bytes.end(),
                           needle.begin(), needle.end()) != bytes.end();
    }

    template <typename T>
    bool ReadStruct(const std::vector<unsigned char>& bytes, std::size_t offset, T& out) {
        if (offset > bytes.size() || sizeof(T) > bytes.size() - offset)
            return false;
        std::memcpy(&out, bytes.data() + offset, sizeof(T));
        return true;
    }

    std::optional<PeSnapshot> ReadPeLayout(const std::vector<unsigned char>& bytes) {
        IMAGE_DOS_HEADER dos{};
        if (!ReadStruct(bytes, 0, dos) || dos.e_magic != IMAGE_DOS_SIGNATURE)
            return std::nullopt;
        if (dos.e_lfanew <= 0)
            return std::nullopt;

        const std::size_t ntOff = static_cast<std::size_t>(dos.e_lfanew);
        DWORD signature = 0;
        if (!ReadStruct(bytes, ntOff, signature) || signature != IMAGE_NT_SIGNATURE)
            return std::nullopt;

        IMAGE_FILE_HEADER file{};
        if (!ReadStruct(bytes, ntOff + sizeof(DWORD), file))
            return std::nullopt;
        if (file.NumberOfSections == 0 || file.NumberOfSections > 96)
            return std::nullopt;

        const std::size_t optOff = ntOff + sizeof(DWORD) + sizeof(IMAGE_FILE_HEADER);
        WORD magic = 0;
        if (!ReadStruct(bytes, optOff, magic))
            return std::nullopt;

        uint32 entryRva = 0;
        if (magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC) {
            IMAGE_OPTIONAL_HEADER64 opt{};
            if (!ReadStruct(bytes, optOff, opt))
                return std::nullopt;
            entryRva = opt.AddressOfEntryPoint;
        } else if (magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC) {
            IMAGE_OPTIONAL_HEADER32 opt{};
            if (!ReadStruct(bytes, optOff, opt))
                return std::nullopt;
            entryRva = opt.AddressOfEntryPoint;
        } else {
            return std::nullopt;
        }

        const std::size_t sectionOff = optOff + file.SizeOfOptionalHeader;
        PeSnapshot snap{};
        snap.entryRva = entryRva;
        snap.sections.reserve(file.NumberOfSections);
        for (WORD i = 0; i < file.NumberOfSections; ++i) {
            IMAGE_SECTION_HEADER section{};
            if (!ReadStruct(bytes, sectionOff + static_cast<std::size_t>(i) * sizeof(section), section))
                return std::nullopt;

            SectionRange range{};
            char name[9]{};
            std::memcpy(name, section.Name, 8);
            range.name = LowerAscii(name);
            range.virtualAddress = section.VirtualAddress;
            range.virtualSize = section.Misc.VirtualSize;
            range.rawOffset = section.PointerToRawData;
            range.rawSize = section.SizeOfRawData;
            range.characteristics = section.Characteristics;
            snap.sections.push_back(range);
        }
        return snap;
    }

    std::span<const unsigned char> SectionBytes(const std::vector<unsigned char>& bytes,
                                                const SectionRange& section) {
        if (section.rawOffset >= bytes.size())
            return {};
        std::size_t available = bytes.size() - section.rawOffset;
        std::size_t rawSize = static_cast<std::size_t>(section.rawSize);
        std::size_t size = rawSize < available ? rawSize : available;
        return std::span<const unsigned char>(bytes.data() + section.rawOffset, size);
    }

    Method ScanPeHeaders(const PeSnapshot& pe) {
        if (pe.entryRva != 0) {
            for (const auto& section : pe.sections) {
                if (!section.ContainsRva(pe.entryRva))
                    continue;
                if (section.name == ".bind"
                    && (section.characteristics & IMAGE_SCN_MEM_EXECUTE) != 0)
                    return Method::EntryBindSection;
                break;
            }
        }

        for (const auto& section : pe.sections) {
            for (std::string_view name : kLegacySections) {
                if (section.name == name)
                    return Method::LegacySectionName;
            }
        }

        return Method::None;
    }

    Method ScanPeImage(const std::vector<unsigned char>& bytes, const PeSnapshot& pe) {
        if (Method headerMethod = ScanPeHeaders(pe); headerMethod == Method::LegacySectionName)
            return headerMethod;

        if (pe.entryRva != 0) {
            for (const auto& section : pe.sections) {
                if (!section.ContainsRva(pe.entryRva))
                    continue;
                auto view = SectionBytes(bytes, section);
                if (BytesContain(view, kOepMovText) || BytesContain(view, kOepText))
                    return Method::OepTextMarker;
                if (Method headerMethod = ScanPeHeaders(pe); headerMethod == Method::EntryBindSection)
                    return headerMethod;
                break;
            }
        }

        for (const auto& section : pe.sections) {
            if ((section.characteristics & IMAGE_SCN_MEM_EXECUTE) == 0)
                continue;
            if (BytesContain(SectionBytes(bytes, section), kLegacyText))
                return Method::LegacyTextMarker;
        }

        return Method::None;
    }

    bool HeaderContainsLegacySection(const std::vector<unsigned char>& bytes) {
        std::string text;
        text.reserve(bytes.size());
        for (unsigned char ch : bytes) {
            text.push_back(static_cast<char>(std::tolower(ch)));
        }
        for (std::string_view name : kLegacySections) {
            if (text.find(name) != std::string::npos)
                return true;
        }
        return false;
    }

    bool ReadWholeFile(const std::filesystem::path& path,
                       uint64 fileSize,
                       std::vector<unsigned char>& bytes) {
        if (fileSize == 0 || fileSize > kPeScanLimit)
            return false;
        std::ifstream in(path, std::ios::binary);
        if (!in)
            return false;
        bytes.resize(static_cast<std::size_t>(fileSize));
        in.read(reinterpret_cast<char*>(bytes.data()),
                static_cast<std::streamsize>(bytes.size()));
        return in.gcount() == static_cast<std::streamsize>(bytes.size());
    }

    bool ReadFilePrefix(const std::filesystem::path& path,
                        uint64 fileSize,
                        std::vector<unsigned char>& bytes) {
        if (fileSize == 0)
            return false;
        constexpr uint64 kHeaderBytes = 1024ull * 1024ull;
        const uint64 wanted = (std::min)(fileSize, kHeaderBytes);
        std::ifstream in(path, std::ios::binary);
        if (!in)
            return false;
        bytes.resize(static_cast<std::size_t>(wanted));
        in.read(reinterpret_cast<char*>(bytes.data()),
                static_cast<std::streamsize>(bytes.size()));
        return in.gcount() == static_cast<std::streamsize>(bytes.size());
    }

    Method ScanFile(const std::filesystem::path& path, uint64& bytesScanned) {
        bytesScanned = 0;
        std::error_code ec;
        uint64 fileSize = std::filesystem::exists(path, ec)
            ? static_cast<uint64>(std::filesystem::file_size(path, ec))
            : 0;

        std::vector<unsigned char> prefix;
        if (ReadFilePrefix(path, fileSize, prefix)) {
            bytesScanned = static_cast<uint64>(prefix.size());
            if (auto pe = ReadPeLayout(prefix)) {
                Method method = ScanPeHeaders(*pe);
                if (method != Method::None)
                    return method;
            }
            bytesScanned = 0;
        }

        std::vector<unsigned char> whole;
        if (ReadWholeFile(path, fileSize, whole)) {
            bytesScanned = static_cast<uint64>(whole.size());
            if (auto pe = ReadPeLayout(whole)) {
                Method method = ScanPeImage(whole, *pe);
                if (method != Method::None)
                    return method;
            }
            bytesScanned = 0;
        }

        std::ifstream in(path, std::ios::binary);
        if (!in)
            return Method::None;

        constexpr std::size_t kChunkBytes = 8ull * 1024ull * 1024ull;
        std::vector<unsigned char> chunk(kChunkBytes);
        bool firstChunk = true;

        while (in) {
            in.read(reinterpret_cast<char*>(chunk.data()),
                    static_cast<std::streamsize>(chunk.size()));
            std::streamsize got = in.gcount();
            if (got <= 0)
                break;

            chunk.resize(static_cast<std::size_t>(got));
            bytesScanned += static_cast<uint64>(chunk.size());

            if (firstChunk && HeaderContainsLegacySection(chunk))
                return Method::LegacySectionName;
            if (BytesContain(chunk, kOepText))
                return Method::OepTextMarker;
            if (BytesContain(chunk, kLegacyText))
                return Method::LegacyTextMarker;

            chunk.resize(kChunkBytes);
            firstChunk = false;
        }

        return Method::None;
    }

    std::string PathToUtf8(const std::filesystem::path& path) {
        auto text = path.u8string();
        return std::string(reinterpret_cast<const char*>(text.data()), text.size());
    }

    uint64 SafeFileSize(const std::filesystem::path& path) {
        std::error_code ec;
        if (!std::filesystem::exists(path, ec))
            return 0;
        return static_cast<uint64>(std::filesystem::file_size(path, ec));
    }

    int64_t SafeWriteTicks(const std::filesystem::path& path) {
        std::error_code ec;
        auto stamp = std::filesystem::last_write_time(path, ec);
        if (ec)
            return 0;
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            stamp.time_since_epoch()).count();
    }

    std::wstring NormalizedKey(const std::filesystem::path& path) {
        std::wstring key = path.native();
        std::replace(key.begin(), key.end(), L'/', L'\\');
        std::transform(key.begin(), key.end(), key.begin(), [](wchar_t ch) {
            return static_cast<wchar_t>(std::towlower(ch));
        });
        return key;
    }

    void AddCandidate(std::vector<ModuleCandidate>& out,
                      std::unordered_set<std::wstring>& seen,
                      const std::filesystem::path& path,
                      bool executable,
                      size_t order) {
        if (path.empty())
            return;

        std::wstring key = path.native();
        std::replace(key.begin(), key.end(), L'/', L'\\');
        std::transform(key.begin(), key.end(), key.begin(), [](wchar_t ch) {
            return static_cast<wchar_t>(std::towlower(ch));
        });
        if (!seen.insert(key).second)
            return;

        const uint64 size = SafeFileSize(path);
        if (size == 0)
            return;

        out.push_back(ModuleCandidate{path, size, executable, order});
    }

    Method ScanFileCached(const std::filesystem::path& path,
                          uint64& fileSize,
                          uint64& bytesScanned) {
        fileSize = SafeFileSize(path);
        bytesScanned = 0;
        if (fileSize == 0)
            return Method::None;

        const int64_t writeTicks = SafeWriteTicks(path);
        const std::wstring key = NormalizedKey(path);
        {
            std::scoped_lock lock(g_lock);
            auto it = g_fileResults.find(key);
            if (it != g_fileResults.end()
                && it->second.fileSize == fileSize
                && it->second.writeTicks == writeTicks) {
                bytesScanned = it->second.bytesScanned;
                return it->second.method;
            }
        }

        Method method = ScanFile(path, bytesScanned);
        {
            std::scoped_lock lock(g_lock);
            g_fileResults[key] = FileScanCacheEntry{
                fileSize,
                writeTicks,
                bytesScanned,
                method,
            };
        }
        return method;
    }

    std::filesystem::path GameRootForLaunch(const std::filesystem::path& launchPath) {
        std::filesystem::path root;
        bool seenCommon = false;
        bool addedGameFolder = false;
        for (const auto& part : launchPath.parent_path()) {
            root /= part;
            std::string value = LowerAscii(PathToUtf8(part));
            if (seenCommon && !addedGameFolder) {
                addedGameFolder = true;
                return root;
            }
            if (value == "common")
                seenCommon = true;
        }
        return launchPath.parent_path();
    }

    bool PathLooksLikeShippingExe(const std::filesystem::path& path) {
        std::string name = LowerAscii(PathToUtf8(path.filename()));
        return name.find("win64-shipping.exe") != std::string::npos;
    }

    bool PathLooksLikeWin64Bin(const std::filesystem::path& path) {
        std::string value = LowerAscii(PathToUtf8(path));
        std::replace(value.begin(), value.end(), '/', '\\');
        return value.find("\\binaries\\win64\\") != std::string::npos;
    }

    std::vector<ModuleCandidate> PreSpawnCandidates(const std::filesystem::path& launchPath) {
        std::vector<ModuleCandidate> out;
        std::unordered_set<std::wstring> seen;
        size_t order = 0;
        AddCandidate(out, seen, launchPath, true, order++);

        const std::filesystem::path root = GameRootForLaunch(launchPath);
        std::error_code ec;
        if (!std::filesystem::is_directory(root, ec))
            return out;

        constexpr size_t kMaxCandidates = 128;
        std::filesystem::recursive_directory_iterator it(
            root, std::filesystem::directory_options::skip_permission_denied, ec);
        std::filesystem::recursive_directory_iterator end;
        while (!ec && it != end && out.size() < kMaxCandidates) {
            if (it.depth() > 6) {
                it.disable_recursion_pending();
                it.increment(ec);
                continue;
            }

            const std::filesystem::path path = it->path();
            if (it->is_regular_file(ec)
                && LowerAscii(PathToUtf8(path.extension())) == ".exe") {
                AddCandidate(out, seen, path, true, order++);
            }
            if (ec)
                ec.clear();
            it.increment(ec);
        }

        const std::wstring launchKey = NormalizedKey(launchPath);
        std::stable_sort(out.begin(), out.end(), [&](const auto& lhs, const auto& rhs) {
            const bool lhsLaunch = NormalizedKey(lhs.path) == launchKey;
            const bool rhsLaunch = NormalizedKey(rhs.path) == launchKey;
            if (lhsLaunch != rhsLaunch) return lhsLaunch;

            const bool lhsShipping = PathLooksLikeShippingExe(lhs.path);
            const bool rhsShipping = PathLooksLikeShippingExe(rhs.path);
            if (lhsShipping != rhsShipping) return lhsShipping;

            const bool lhsWin64 = PathLooksLikeWin64Bin(lhs.path);
            const bool rhsWin64 = PathLooksLikeWin64Bin(rhs.path);
            if (lhsWin64 != rhsWin64) return lhsWin64;

            const bool lhsLarge = lhs.fileSize >= kLargeDllScanFloor;
            const bool rhsLarge = rhs.fileSize >= kLargeDllScanFloor;
            if (lhsLarge != rhsLarge) return lhsLarge;

            if (lhs.fileSize != rhs.fileSize)
                return lhs.fileSize > rhs.fileSize;
            return lhs.order < rhs.order;
        });
        return out;
    }

    std::vector<ModuleCandidate> CandidateModules(uint32 pid,
                                                  const std::filesystem::path& mainImage) {
        std::vector<ModuleCandidate> modules;
        std::unordered_set<std::wstring> seen;
        size_t order = 0;

        AddCandidate(modules, seen, mainImage, true, order++);

        for (const auto& module : RemoteTools::EnumerateModules(pid)) {
            std::filesystem::path modulePath = module.path.empty()
                ? std::filesystem::path(module.name)
                : std::filesystem::path(module.path);
            const std::string ext = LowerAscii(PathToUtf8(modulePath.extension()));
            const bool executable = ext == ".exe";
            const bool dll = ext == ".dll";
            if (!executable && !dll)
                continue;
            if (!executable) {
                const uint64 size = SafeFileSize(modulePath);
                if (size < kLargeDllScanFloor)
                    continue;
                if (IsWindowsSystemPath(modulePath) || IsSteamRuntimeName(modulePath))
                    continue;
            }
            AddCandidate(modules, seen, modulePath, executable, order++);
        }

        std::stable_sort(modules.begin(), modules.end(), [](const auto& lhs, const auto& rhs) {
            if (lhs.executable != rhs.executable)
                return lhs.executable;
            if (!lhs.executable && lhs.fileSize != rhs.fileSize)
                return lhs.fileSize > rhs.fileSize;
            return lhs.order < rhs.order;
        });
        return modules;
    }

    Method ScanProcessModules(uint32 pid,
                              const std::filesystem::path& mainImage,
                              std::filesystem::path& matchedPath,
                              uint64& matchedSize,
                              uint64& bytesScanned,
                              size_t& checkedModules) {
        Method method = Method::None;
        for (const auto& candidate : CandidateModules(pid, mainImage)) {
            ++checkedModules;
            bytesScanned = 0;
            method = ScanFile(candidate.path, bytesScanned);
            if (method == Method::None)
                continue;

            matchedPath = candidate.path;
            matchedSize = candidate.fileSize;
            return method;
        }
        bytesScanned = 0;
        return Method::None;
    }

    Method TicketFallback(AppId_t appId) {
        if (appId == 0 || appId == k_uAppIdInvalid)
            return Method::None;
        return Ticket::GetEncryptedTicketFromRegistry(appId).empty()
            ? Method::None
            : Method::TicketCacheHint;
    }
}

namespace ProtectionProbe {
    ScanResult ScanBeforeSpawn(AppId_t appId, const std::string& imagePath) {
        if (imagePath.empty() || !EndsWith(imagePath, ".exe"))
            return {};

        const ClockMark::Span scanTime;
        std::filesystem::path launchPath = std::filesystem::u8path(imagePath);
        std::vector<ModuleCandidate> candidates = PreSpawnCandidates(launchPath);

        ScanResult result{};
        result.valid = true;
        result.method = MethodName(Method::None);
        result.routeReason = RouteReason(Method::None);
        result.imagePath = PathToUtf8(launchPath);

        uint64 totalScanned = 0;
        size_t checked = 0;
        Method bestMethod = Method::None;
        std::filesystem::path bestPath;
        uint64 bestFileSize = 0;
        uint64 bestBytesScanned = 0;
        size_t bestChecked = 0;
        for (const auto& candidate : candidates) {
            ++checked;
            uint64 fileSize = 0;
            uint64 bytesScanned = 0;
            Method method = ScanFileCached(candidate.path, fileSize, bytesScanned);
            totalScanned += bytesScanned;
            if (method == Method::None)
                continue;

            if (bestMethod == Method::None) {
                bestMethod = method;
                bestPath = candidate.path;
                bestFileSize = fileSize;
                bestBytesScanned = bytesScanned;
                bestChecked = checked;
            }

            if (IsRouteMethod(method)) {
                bestMethod = method;
                bestPath = candidate.path;
                bestFileSize = fileSize;
                bestBytesScanned = bytesScanned;
                bestChecked = checked;
                break;
            }
        }

        if (bestMethod != Method::None) {
            result.detected = true;
            result.routeAccepted = IsRouteMethod(bestMethod);
            result.method = MethodName(bestMethod);
            result.routeReason = RouteReason(bestMethod);
            result.imagePath = PathToUtf8(bestPath);
            result.fileSize = bestFileSize;
            result.bytesScanned = bestBytesScanned;
            result.candidates = bestChecked;
            LOG_MISC_INFO("ProtectionProbe(pre-spawn): appid={} detected=true routeAccepted={} routeReason={} method={} file_size={} scanned={} total_scanned={} candidates={} elapsed_ms={:.3f} image={}",
                          appId,
                          result.routeAccepted,
                          result.routeReason,
                          result.method,
                          result.fileSize,
                          result.bytesScanned,
                          totalScanned,
                          result.candidates,
                          scanTime.Ms(),
                          result.imagePath);
            return result;
        }

        result.bytesScanned = totalScanned;
        result.candidates = checked;
        LOG_MISC_INFO("ProtectionProbe(pre-spawn): appid={} detected=false routeAccepted=false routeReason=none method=none scanned={} candidates={} elapsed_ms={:.3f} image={}",
                      appId,
                      result.bytesScanned,
                      result.candidates,
                      scanTime.Ms(),
                      result.imagePath);
        return result;
    }

    ScanResult ScanOnce(uint32 pid, uint64 creation, AppId_t appId, const std::string& imagePath) {
        if (pid == 0 || creation == 0 || imagePath.empty())
            return {};
        if (!EndsWith(imagePath, ".exe"))
            return {};

        ProcessKey key{pid, creation};
        {
            std::scoped_lock lock(g_lock);
            auto it = g_results.find(key);
            if (it != g_results.end())
                return it->second;
        }

        const ClockMark::Span scanTime;
        uint64 bytesScanned = 0;
        std::filesystem::path path = std::filesystem::u8path(imagePath);
        std::filesystem::path matchedPath = path;
        uint64 fileSize = 0;
        size_t modulesChecked = 0;
        Method method = Method::None;
        method = ScanProcessModules(pid, path, matchedPath, fileSize, bytesScanned, modulesChecked);
        if (method == Method::None)
            method = TicketFallback(appId);

        LOG_IPCCH_INFO("ProtectionProbe: pid={} appid={} detected={} method={} file_size={} scanned={} modules={} elapsed_ms={:.3f} image={}",
                       pid,
                       appId,
                       method == Method::None ? "false" : "true",
                       MethodName(method),
                       fileSize,
                       bytesScanned,
                       modulesChecked,
                       scanTime.Ms(),
                       PathToUtf8(matchedPath));

        ScanResult result{};
        result.valid = true;
        result.detected = method != Method::None;
        result.method = MethodName(method);
        result.imagePath = PathToUtf8(matchedPath);
        result.fileSize = fileSize;
        result.bytesScanned = bytesScanned;
        result.candidates = modulesChecked;
        {
            std::scoped_lock lock(g_lock);
            g_results[key] = result;
        }
        return result;
    }
}

