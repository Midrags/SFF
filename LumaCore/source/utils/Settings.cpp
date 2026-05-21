#include "Settings.h"
#include "Logger.h"
#include <toml++/toml.hpp>
#include <filesystem>
#include <string_view>

namespace Settings {

    // Lookup table: TOML string → LogLevel enum.
    // Returns the current logLevel unchanged if the input string isn't recognised.
    static LogLevel ParseLogLevel(std::string_view s)
    {
        static const struct { std::string_view name; LogLevel lvl; } kLevels[] = {
            { "trace", LogLevel::Trace },
            { "debug", LogLevel::Debug },
            { "info",  LogLevel::Info  },
            { "warn",  LogLevel::Warn  },
            { "error", LogLevel::Error },
        };
        for (const auto& entry : kLevels)
            if (entry.name == s) return entry.lvl;
        return logLevel;
    }

    static const char* LevelName(LogLevel lvl)
    {
        switch (lvl) {
        case LogLevel::Trace: return "trace";
        case LogLevel::Debug: return "debug";
        case LogLevel::Info:  return "info";
        case LogLevel::Warn:  return "warn";
        case LogLevel::Error: return "error";
        default:              return "unknown";
        }
    }

    void Load(const std::string& configPath)
    {
        std::filesystem::path cfgPath(configPath);
        logDir = (cfgPath.parent_path() / "lumacore").string();

        if (!std::filesystem::exists(cfgPath)) {
            LOG_INFO("Settings: config not found at '{}', using defaults", configPath);
            return;
        }

        try {
            auto tbl = toml::parse_file(configPath);

            // [log]
            if (auto logTbl = tbl["log"].as_table()) {
                if (auto lvl = (*logTbl)["level"].value<std::string>())
                    logLevel = ParseLogLevel(*lvl);
            }

            // [lua]
            if (auto luaTbl = tbl["lua"].as_table()) {
                if (auto arr = (*luaTbl)["paths"].as_array()) {
                    for (const auto& elem : *arr) {
                        if (auto s = elem.value<std::string>())
                            luaPaths.push_back(*s);
                    }
                }
            }

            LOG_INFO("Settings: log.level={} lua.paths_count={}",
                     LevelName(logLevel), static_cast<uint32_t>(luaPaths.size()));

        } catch (const toml::parse_error& e) {
            LOG_WARN("Settings: TOML parse error: {}", e.what());
        } catch (...) {
            LOG_WARN("Settings: load failed, using defaults");
        }
    }

}
