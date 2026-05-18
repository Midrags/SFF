#pragma once

#include <string>
#include <vector>
#include <windows.h>

namespace Settings {

    enum class LogLevel { Trace, Debug, Info, Warn, Error };

    void Load(const std::string& configPath);

    // [log]
    inline LogLevel logLevel = LogLevel::Debug;

    // derived from configPath: <steam>/lumacore/
    inline std::string logDir;

    // [lua]
    inline std::vector<std::string> luaPaths;

}
