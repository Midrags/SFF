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

#ifndef __INCLUDED_CALLBACK_WRAPPER_H__
#define __INCLUDED_CALLBACK_WRAPPER_H__

#include "base.h"

class CCallbackBase001
{
public:
    CCallbackBase001() { m_nCallbackFlags = 0; m_iCallback = 0; }
    // don't add a virtual destructor because we export this binary interface across dll's
    virtual void Run( void *pvParam ) = 0;
    int GetICallback() { return m_iCallback; }

protected:
    enum { k_ECallbackFlagsRegistered = 0x01, k_ECallbackFlagsGameServer = 0x02 };
    uint8 m_nCallbackFlags;
    int m_iCallback;
    friend class CCallbackMgr;
    friend class CCallBackWrapper;

private:
    CCallbackBase001( const CCallbackBase001& );
    CCallbackBase001& operator=( const CCallbackBase001& );
};

class CCallBackWrapper : public CCallbackBase
{
public:
    CCallBackWrapper( CCallbackBase *callback )
    {
        old_callback = reinterpret_cast<CCallbackBase001 *>( callback );
        m_nCallbackFlags = old_callback->m_nCallbackFlags;
        m_iCallback = old_callback->m_iCallback;
    }

    void Run( void *pvParam )
    {
        old_callback->Run( pvParam );
    }
    void Run( void *pvParam, bool bIOFailure, SteamAPICall_t hSteamAPICall )
    {
        old_callback->Run( pvParam );
    }
    int GetCallbackSizeBytes()
    {
        return 0;
    }

private:
    CCallbackBase001 *old_callback{};
};

#endif // __INCLUDED_CALLBACK_WRAPPER_H__
