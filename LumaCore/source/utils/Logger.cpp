#include "Logger.h"

#ifdef LUMACORE_LOGGING_ENABLED

#include "Settings.h"
#include <atomic>
#include <filesystem>
#include <string>

namespace {
    std::atomic_bool g_mainReady{false};

    std::filesystem::path ResolveDllDir(HMODULE selfModule) {
        wchar_t buf[MAX_PATH] = {};
        DWORD len = GetModuleFileNameW(selfModule, buf, MAX_PATH);
        if (len == 0 || len == MAX_PATH) return L".";
        return std::filesystem::path(buf).parent_path();
    }

    spdlog::level::level_enum ToSpdlog(Settings::LogLevel lv) {
        switch (lv) {
        case Settings::LogLevel::Trace: return spdlog::level::trace;
        case Settings::LogLevel::Debug: return spdlog::level::debug;
        case Settings::LogLevel::Info:  return spdlog::level::info;
        case Settings::LogLevel::Warn:  return spdlog::level::warn;
        case Settings::LogLevel::Error: return spdlog::level::err;
        default: return spdlog::level::info;
        }
    }

    std::shared_ptr<spdlog::logger> MakeLogger(const std::string& dir,
                                                const std::string& name) {
        auto path = std::filesystem::path(dir) / (name + ".log");
        auto logger = spdlog::basic_logger_mt(name, path.string(), /*truncate=*/true);
        logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%^%l%$] [tid=%t] [%s:%# %!()] %v");
        logger->flush_on(spdlog::level::trace);
        return logger;
    }
}

namespace Logger {

    void Init(HMODULE selfModule) {
        bool expected = false;
        if (!g_mainReady.compare_exchange_strong(expected, true)) return;

        try {
            auto dir = ResolveDllDir(selfModule);
            auto logDir = (dir / "lumacore").string();
            std::filesystem::create_directories(logDir);
            Main = MakeLogger(logDir, "main");
            Main->set_level(spdlog::level::trace);  // early boot: log everything
            LOG_INFO("Log initialised at {}", logDir);
        } catch (const std::exception&) {
            g_mainReady.store(false);
        }
    }

    void InitModules() {
        if (!g_mainReady) return;

        try {
            std::filesystem::create_directories(Settings::logDir);
            // verbose=true forces trace level on every module logger so we
            // capture everything (IPC, network, hooks, registry probes, etc).
            // Defaults on so users do not need to edit config to send useful
            // logs after a launch failure.
            auto lvl = Settings::verbose ? spdlog::level::trace
                                         : ToSpdlog(Settings::logLevel);

            Main->set_level(lvl);

            auto initOne = [&](std::shared_ptr<spdlog::logger>& logger, const char* name) {
                logger = MakeLogger(Settings::logDir, name);
                logger->set_level(lvl);
            };

            #define LC_MOD(v, n) initOne(v, n);
            #include "ModuleLog.h"
            #undef LC_MOD

            LOG_INFO("Module loggers initialised at {} level={} verbose={}",
                     Settings::logDir, static_cast<int>(lvl),
                     Settings::verbose ? "true" : "false");
        } catch (const std::exception& e) {
            LOG_WARN("InitModules failed: {}", e.what());
        }
    }

}

#endif  // LUMACORE_LOGGING_ENABLED
