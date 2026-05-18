#include "Settings.h"
#include "Logger.h"
#include <toml++/toml.hpp>
#include <filesystem>

namespace Settings {

    void Load(const std::string& configPath) {
        std::filesystem::path p(configPath);
        logDir = (p.parent_path() / "lumacore").string();

        if (!std::filesystem::exists(configPath)) {
            LOG_INFO("Config file not found, using defaults");
            return;
        }

        try {
            auto tbl = toml::parse_file(configPath);

            // [log]
            if (auto log = tbl["log"].as_table()) {
                if (auto val = (*log)["level"].value<std::string>()) {
                    if (*val == "trace")           logLevel = LogLevel::Trace;
                    else if (*val == "debug")       logLevel = LogLevel::Debug;
                    else if (*val == "info")        logLevel = LogLevel::Info;
                    else if (*val == "warn")        logLevel = LogLevel::Warn;
                    else if (*val == "error")       logLevel = LogLevel::Error;
                }
            }

            // [lua]
            if (auto lua = tbl["lua"].as_table()) {
                if (auto arr = (*lua)["paths"].as_array()) {
                    for (auto& elem : *arr) {
                        if (auto str = elem.value<std::string>()) {
                            luaPaths.push_back(*str);
                        }
                    }
                }
            }

            LOG_INFO("Settings loaded: log.level={} lua.paths={}",
                     [&](){
                         switch (logLevel) {
                         case LogLevel::Trace: return "trace";
                         case LogLevel::Debug: return "debug";
                         case LogLevel::Info:  return "info";
                         case LogLevel::Warn:  return "warn";
                         case LogLevel::Error: return "error";
                         default: return "???";
                         }
                     }(),
                     (uint32_t)luaPaths.size());

        } catch (const toml::parse_error& e) {
            LOG_WARN("Config parse error: {}", e.what());
        } catch (...) {
            LOG_WARN("Config load failed, using defaults");
        }
    }

}
