#pragma once

#include "entry.h"

namespace Ticket {
    // Reads the app ownership ticket cached by Steam under
    //   HKCU\Software\Valve\Steam\Apps\<AppId>\AppTicket  (REG_BINARY)
    // Returns an empty vector when no ticket is available.
    std::vector<uint8_t> GetAppOwnershipTicketFromRegistry(AppId_t appId);

    // Reads the encrypted app ticket cached by Steam under
    //   HKCU\Software\Valve\Steam\Apps\<AppId>\ETicket  (REG_BINARY)
    // Returns an empty vector when no ticket is available.
    std::vector<uint8_t> GetEncryptedTicketFromRegistry(AppId_t appId);

    //Get spoof steamID From the cached AppOwnershipTicket for the given AppId.
    uint64_t GetSpoofSteamID(AppId_t appId);

    // Write AppTicket binary data to registry.
    bool WriteAppOwnershipTicket(AppId_t appId, const std::vector<uint8_t>& data);

    // Write ETicket binary data to registry.
    bool WriteEncryptedTicket(AppId_t appId, const std::vector<uint8_t>& data);
}