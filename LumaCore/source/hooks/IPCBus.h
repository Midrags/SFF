#pragma once

#include "Steam/Types.h"
#include "Steam/Enums.h"
#include "Steam/Structs.h"

#define REGISTER_IPC_CMD(iface, method) \
    { EIPCInterface::iface, HASH_##iface##_##method, \
      #iface "::" #method, \
      Cmd_##iface##_##method }


// ── IPC InterfaceCall packet layout ─────────────────────────────
//  offset 0:  cmd          (1 byte, EIPCCommand)
//  offset 1:  interfaceID  (1 byte, EIPCInterface)
//  offset 2:  hSteamUser   (4 bytes)
//  offset 6:  funcHash     (4 bytes)
//  offset 10: args[]       (variable)
// ─────────────────────────────────────────────────────────────────
constexpr int OFFSET_CMD          = 0;
constexpr int OFFSET_INTERFACE_ID = 1;
constexpr int OFFSET_FUNC_HASH    = 6;
constexpr int IPC_ARGS_OFFSET     = 10;
constexpr int IPC_HEADER_SIZE     = 10;
constexpr uint8 IPC_REPLY_TAG     = 0x0B;

constexpr uint32 HASH_IClientUser_GetSteamID                        = 0xD6FC3200;
constexpr uint32 HASH_IClientUser_GetAppOwnershipTicketExtendedData = 0xC7E71245;
constexpr uint32 HASH_IClientUser_RequestEncryptedAppTicket         = 0x25D6BB1D;
constexpr uint32 HASH_IClientUser_GetEncryptedAppTicket             = 0xE0468CB4;

constexpr uint32 HASH_IClientUtils_GetAppID                         = 0x09607EC4;
constexpr uint32 HASH_IClientUtils_GetAPICallResult                 = 0x2D3D3947;
constexpr uint32 HASH_IClientUtils_SetAppIDForCurrentPipe           = 0x3378803C;

namespace IPCBus {

    void Install();
    void Uninstall();

    // ── Handler registry ────────────────────────────────────────

    using IpcHandlerFn = void(*)(CSteamPipeClient* pipe,CUtlBuffer* pRead, CUtlBuffer* pWrite);

    struct IpcHandlerEntry {
        EIPCInterface interfaceID;
        uint32        funcHash;
        const char*   name;
        IpcHandlerFn  handler;
    };

    void RegisterHandlers(const IpcHandlerEntry* entries, size_t count);

}
