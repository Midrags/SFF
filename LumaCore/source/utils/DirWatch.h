#pragma once

#include <windows.h>
#include <string>
#include <vector>

namespace DirWatch {
    void Start(const std::vector<std::string>& directories);
    void Stop();
}