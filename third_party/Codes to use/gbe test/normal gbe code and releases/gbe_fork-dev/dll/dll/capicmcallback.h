/* Copyright (C) 2019 Mr Goldberg
   This file is part of the Goldberg Emulator

   The Goldberg Emulator is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 3 of the License, or (at your option) any later version.

   The Goldberg Emulator is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with the Goldberg Emulator; if not, see
   <http://www.gnu.org/licenses/>.  */

#ifndef __INCLUDED_CAPICMCALLBACK_H__
#define __INCLUDED_CAPICMCALLBACK_H__

#include "base.h"

typedef void (*OnLogonSuccessFunc)();
typedef void (*OnLogonFailureFunc)(EResult);
typedef void (*OnLoggedOffFunc)();
typedef void (*OnBeginLogonRetryFunc)();
typedef void (*HandleVACChallengeFunc)(int, void *, int);
typedef void (*GSHandleClientApproveFunc)(CSteamID *);
typedef void (*GSHandleClientDenyFunc)(CSteamID *, EDenyReason);
typedef void (*GSHandleClientKickFunc)(CSteamID *, EDenyReason);

class CCAPICMCallBack : public ICMCallback
{
public:
    CCAPICMCallBack(OnLogonSuccessFunc func1,
        OnLogonFailureFunc func2,
        OnLoggedOffFunc func3,
        OnBeginLogonRetryFunc func4,
        HandleVACChallengeFunc func5,
        GSHandleClientApproveFunc func6,
        GSHandleClientDenyFunc func7,
        GSHandleClientKickFunc func8)
    {
        OnLogonSuccess_ptr = func1;
        OnLogonFailure_ptr = func2;
        OnLoggedOff_ptr = func3;
        OnBeginLogonRetry_ptr = func4;
        HandleVACChallenge_ptr = func5;
        GSHandleClientApprove_ptr = func6;
        GSHandleClientDeny_ptr = func7;
        GSHandleClientKick_ptr = func8;
    }
    ~CCAPICMCallBack() {}

    void OnLogonSuccess() { OnLogonSuccess_ptr(); }
    void OnLogonFailure(EResult result) { OnLogonFailure_ptr(result); }
    void OnLoggedOff() { OnLoggedOff_ptr(); }
    void OnBeginLogonRetry() { OnBeginLogonRetry_ptr(); }
    void HandleVACChallenge(int unk1, void *unk2, int unk3) { HandleVACChallenge_ptr(unk1, unk2, unk3); }
    void GSHandleClientApprove(CSteamID *steamID) { GSHandleClientApprove_ptr(steamID); }
    void GSHandleClientDeny(CSteamID *steamID, EDenyReason reason) { GSHandleClientDeny_ptr(steamID, reason); }
    void GSHandleClientKick(CSteamID *steamID, EDenyReason reason) { GSHandleClientKick_ptr(steamID, reason); }

private:
    OnLogonSuccessFunc OnLogonSuccess_ptr{};
    OnLogonFailureFunc OnLogonFailure_ptr{};
    OnLoggedOffFunc OnLoggedOff_ptr{};
    OnBeginLogonRetryFunc OnBeginLogonRetry_ptr{};
    HandleVACChallengeFunc HandleVACChallenge_ptr{};
    GSHandleClientApproveFunc GSHandleClientApprove_ptr{};
    GSHandleClientDenyFunc GSHandleClientDeny_ptr{};
    GSHandleClientKickFunc GSHandleClientKick_ptr{};
};

#endif // __INCLUDED_CAPICMCALLBACK_H__
