#ifndef HOOKMANAGER_H
#define HOOKMANAGER_H

#include "entry.h"
#include "PatternDb.h"

namespace SteamUI {
    void CoreHook();
    void CoreUnhook();
}

namespace LumaCore {
    void Attach();
    void Detach();
}


#endif // HOOKMANAGER_H
