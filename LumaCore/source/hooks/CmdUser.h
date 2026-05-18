#pragma once

#include <cstdint>
#include "Steam/Types.h"

namespace CmdUser {
    void Register();

    // eticket async-call map for GetAPICallResult(154).
    // LookupEticketAsyncCall returns the AppId if recorded, 0 otherwise.
    AppId_t LookupEticketAsyncCall(uint64 hAsyncCall);
    void EraseEticketAsyncCall(uint64 hAsyncCall);
}
