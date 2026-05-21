#include "entry.h"
#include "DirWatch.h"
#include "LuaLoader.h"
#include "hooks/SteamCapture.h"
#include "Logger.h"
#include <atomic>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace DirWatch {

    static constexpr DWORD kBufBytes   = 65536;
    static constexpr DWORD kDebounceMs = 500;

    // ── WatchSlot: encapsulates all per-directory watch state ──────────────────
    // Each monitored directory gets one slot. Open() acquires the directory handle
    // and arms the first overlapped read. Harvest() drains one completed read into
    // the caller-supplied accumulator map (full path -> action) and immediately
    // re-arms. Close() tears down the slot cleanly.
    struct WatchSlot {
        std::string path;
        HANDLE      hDir   = nullptr;
        HANDLE      hEvent = nullptr;
        OVERLAPPED  ov     = {};
        char        buf[kBufBytes]{};

        bool Open() {
            hEvent = CreateEventA(nullptr, FALSE, FALSE, nullptr);
            if (!hEvent) return false;
            ov.hEvent = hEvent;

            hDir = CreateFileA(path.c_str(),
                FILE_LIST_DIRECTORY,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                nullptr, OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
                nullptr);
            if (hDir == INVALID_HANDLE_VALUE) {
                LOG_PACKAGE_WARN("DirWatch: failed to open '{}' (err={})", path, GetLastError());
                CloseHandle(hEvent);
                hDir = hEvent = nullptr;
                return false;
            }
            return Arm();
        }

        bool Arm() {
            DWORD nb = 0;
            if (!ReadDirectoryChangesW(hDir, buf, kBufBytes, FALSE,
                                       FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE,
                                       &nb, &ov, nullptr)) {
                if (GetLastError() != ERROR_IO_PENDING) {
                    LOG_PACKAGE_WARN("DirWatch: ReadDirectoryChangesW failed (err={})",
                                     GetLastError());
                    return false;
                }
            }
            return true;
        }

        // Drain one completed overlapped result into acc (full-path -> last-action map).
        // Re-arms immediately so events that arrive during the debounce window aren't lost.
        void Harvest(std::unordered_map<std::string, DWORD>& acc,
                     std::vector<std::string>& ordering)
        {
            DWORD nb = 0;
            if (!GetOverlappedResult(hDir, &ov, &nb, FALSE) || !nb) { Arm(); return; }

            const FILE_NOTIFY_INFORMATION* rec =
                reinterpret_cast<const FILE_NOTIFY_INFORMATION*>(buf);
            while (rec) {
                DWORD act = rec->Action;
                if (act == FILE_ACTION_ADDED || act == FILE_ACTION_MODIFIED
                        || act == FILE_ACTION_REMOVED) {
                    std::wstring_view fn(rec->FileName, rec->FileNameLength / sizeof(wchar_t));
                    if (fn.size() >= 4 && fn.substr(fn.size() - 4) == L".lua") {
                        std::string name(fn.size(), '\0');
                        for (size_t i = 0; i < fn.size(); ++i)
                            name[i] = static_cast<char>(fn[i]);
                        std::string full = path + "\\" + name;
                        LOG_PACKAGE_INFO("Lua file {}: {}",
                            act == FILE_ACTION_ADDED    ? "added"    :
                            act == FILE_ACTION_MODIFIED ? "modified" : "removed", name);
                        if (!acc.count(full)) ordering.push_back(full);
                        acc[full] = act;
                    }
                }
                if (!rec->NextEntryOffset) break;
                rec = reinterpret_cast<const FILE_NOTIFY_INFORMATION*>(
                    reinterpret_cast<const char*>(rec) + rec->NextEntryOffset);
            }
            Arm();
        }

        void Close() {
            if (hDir && hDir != INVALID_HANDLE_VALUE) { CloseHandle(hDir); hDir = nullptr; }
            if (hEvent) { CloseHandle(hEvent); hEvent = nullptr; }
        }

        bool Valid() const { return hDir && hDir != INVALID_HANDLE_VALUE; }
    };

    static std::atomic<bool> g_alive{false};
    static std::thread        g_MonitorThread;
    static std::vector<std::string> g_dirs;

    // ── MonitorThread ──────────────────────────────────────────────────────────
    static void MonitorThread()
    {
        // Build one WatchSlot per directory.
        std::vector<WatchSlot> slots(g_dirs.size());
        for (size_t i = 0; i < slots.size(); ++i) {
            slots[i].path = g_dirs[i];
            if (slots[i].Open())
                LOG_PACKAGE_INFO("DirWatch: watching '{}'", g_dirs[i]);
        }

        // Collect only the valid slots into the event/index arrays for WaitForMultipleObjects.
        std::vector<HANDLE> evts;
        std::vector<size_t> idxMap;
        evts.reserve(slots.size());
        idxMap.reserve(slots.size());
        for (size_t i = 0; i < slots.size(); ++i) {
            if (slots[i].Valid()) {
                evts.push_back(slots[i].hEvent);
                idxMap.push_back(i);
            }
        }

        if (evts.empty()) {
            LOG_PACKAGE_WARN("DirWatch: no directories could be opened");
            for (auto& s : slots) s.Close();
            return;
        }

        const DWORD nEvts = static_cast<DWORD>(evts.size());

        while (g_alive) {
            DWORD wr = WaitForMultipleObjects(nEvts, evts.data(), FALSE, 1000);
            if (!g_alive) break;
            if (wr == WAIT_TIMEOUT) continue;
            if (wr < WAIT_OBJECT_0 || wr >= WAIT_OBJECT_0 + nEvts) continue;

            std::unordered_map<std::string, DWORD> acc;
            std::vector<std::string> ordering;

            slots[idxMap[wr - WAIT_OBJECT_0]].Harvest(acc, ordering);

            // Debounce: keep draining until a quiet period of kDebounceMs.
            while (g_alive) {
                DWORD dr = WaitForMultipleObjects(nEvts, evts.data(), FALSE, kDebounceMs);
                if (!g_alive || dr == WAIT_TIMEOUT) break;
                if (dr < WAIT_OBJECT_0 || dr >= WAIT_OBJECT_0 + nEvts) break;
                slots[idxMap[dr - WAIT_OBJECT_0]].Harvest(acc, ordering);
            }

            if (!ordering.empty()) {
                LOG_PACKAGE_INFO("DirWatch: processing {} Lua file change(s)", ordering.size());
                for (const auto& fullPath : ordering) {
                    if (acc[fullPath] == FILE_ACTION_REMOVED)
                        LuaLoader::UnloadFile(fullPath);
                    else
                        LuaLoader::ParseFile(fullPath);
                }
                SteamCapture::NotifyLicenseChanged();
                LOG_PACKAGE_INFO("DirWatch: refresh completed");
            }
        }

        for (auto& s : slots) s.Close();
        LOG_PACKAGE_INFO("DirWatch: stopped");
    }

    void Start(const std::vector<std::string>& directories) {
        if (g_alive.exchange(true)) {
            LOG_PACKAGE_WARN("DirWatch: already running");
            return;
        }
        g_dirs          = directories;
        g_MonitorThread = std::thread(MonitorThread);
    }

    void Stop() {
        if (!g_alive) return;
        g_alive = false;
        if (g_MonitorThread.joinable())
            g_MonitorThread.join();
    }
}
