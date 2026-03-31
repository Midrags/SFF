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

#ifndef __INCLUDED_STEAM_USER_ITEMS_H__
#define __INCLUDED_STEAM_USER_ITEMS_H__

#include "base.h"
#include "econ_item.h"

class Steam_Game_Coordinator;

class Steam_User_Items :
public ISteamUserItems001,
public ISteamUserItems002,
public ISteamUserItems003,
public ISteamUserItems
{
    class Settings *settings{};
    class SteamCallBacks *callbacks{};
    class SteamCallResults *callback_results{};

    Steam_Game_Coordinator *gc();

public:
    Steam_User_Items(class Settings *settings, class SteamCallBacks *callbacks, class SteamCallResults *callback_results);
    ~Steam_User_Items();

    SteamAPICall_t LoadItems();
    void LoadItems_old();
    SteamAPICall_t GetItemCount();
    void GetItemCount_old();
    bool GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount );
    bool GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount );
    bool GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount );
    bool GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount );
    bool GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue );
    SteamAPICall_t UpdateInventoryPos( uint64 ulItemID, uint32 unNewInventoryPos );
    void UpdateInventoryPos_old( uint64 ulItemID, uint32 unNewInventoryPos );
    SteamAPICall_t DeleteItem( uint64 ulItemID );
    void DropItem_old( uint64 ulItemID );
    SteamAPICall_t DropItem_old2( uint64 ulItemID );
    SteamAPICall_t GetItemBlob( uint64 ulItemID );
    SteamAPICall_t SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob );
    virtual SteamAPICall_t DropItem( uint64 ulItemID );
};

#endif // __INCLUDED_STEAM_USER_ITEMS_H__
