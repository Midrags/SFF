#pragma once

#include "Steam/Types.h"

// Patches incoming CMsgClientPersonaState (eMsg 766) so that a game launched
// with -onlinefix (which reports as appid 480 to Steam) shows the correct
// game_played_app_id and game_name in the local Steam client.
//
// Call HandleRecv from PacketRouter's RecvJob for k_EMsgClientPersonaState.
namespace RichPresence {

    // Parse pBody as CMsgClientPersonaState. For each Friend entry where
    // game_played_app_id == 480 and SteamCapture::ResolveAppId() holds a
    // real appid, replace game_played_app_id, gameid, and game_name with
    // the real values and serialize into pOutBuf (max outBufSize bytes).
    // Sets *pOutSize to the serialized length and returns true on success.
    // Returns false without modifying pOutBuf if no patch is needed or the
    // serialized result exceeds outBufSize.
    bool HandleRecv(const uint8* pBody, uint32 cbBody,
                    uint8* pOutBuf, uint32 outBufSize, uint32* pOutSize);

}
