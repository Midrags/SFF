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

#ifndef __INCLUDED_STEAM_GAMESERVER_ITEMS_H__
#define __INCLUDED_STEAM_GAMESERVER_ITEMS_H__

#include "base.h"
#include "econ_item.h"

class Steam_Game_Coordinator;

class Steam_GameServer_Items :
public ISteamGameServerItems001,
public ISteamGameServerItems002,
public ISteamGameServerItems003,
public ISteamGameServerItems
{
    class Settings *settings{};
    class SteamCallBacks *callbacks{};
    class SteamCallResults *callback_results{};

    Steam_Game_Coordinator *gc();

public:
    Steam_GameServer_Items(class Settings *settings, class SteamCallBacks *callbacks, class SteamCallResults *callback_results);
    ~Steam_GameServer_Items();

    void on_items_received(CSteamID steam_id, size_t num_items, SteamAPICall_t api_call, bool success);
    void on_item_pos_updated(CSteamID steam_id, uint64 item_id, uint32 inv_pos);
    void on_item_deleted(CSteamID steam_id, uint64 item_id);

    SteamAPICall_t LoadItems( CSteamID ownerID );
    void LoadItems_old( CSteamID ownerID );
    SteamAPICall_t GetItemCount( CSteamID ownerID );
    void GetItemCount_old( CSteamID ownerID );
    bool GetItemIterative( CSteamID ownerID, uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount );
    bool GetItemIterative( CSteamID ownerID, uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount );
    bool GetItemByID( uint64 ulItemID, CSteamID *pOwnerID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount );
    bool GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount );
    bool GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue );
    HNewItemRequest CreateNewItemRequest( CSteamID steamID );
    HNewItemRequest CreateNewItemRequest( CSteamID steamID, uint32 unItemLevel, EItemQuality eQuality );
    bool AddNewItemLevel( HNewItemRequest handle, uint32 unItemLevel );
    bool AddNewItemQuality( HNewItemRequest handle, EItemQuality eQuality );
    bool SetNewItemInitialInventoryPos( HNewItemRequest handle, uint32 unInventoryPos );
    bool SetNewItemInitialQuantity( HNewItemRequest handle, uint32 unQuantity );
    bool AddNewItemCriteria( HNewItemRequest handle, const char *pchField, EItemCriteriaOperator eOperator, const char *pchValue, bool bRequired );
    bool AddNewItemCriteria( HNewItemRequest handle, const char *pchField, EItemCriteriaOperator eOperator, float flValue, bool bRequired );
    SteamAPICall_t SendNewItemRequest( HNewItemRequest handle );
    void SendNewItemRequest_old( HNewItemRequest handle );
    SteamAPICall_t GrantItemToUser( uint64 ulItemID, CSteamID steamIDRecipient );
    void GrantItemToUser_old( uint64 ulItemID, CSteamID steamIDRecipient );
    SteamAPICall_t DeleteTemporaryItem( uint64 ulItemID );
    void DeleteTemporaryItem_old( uint64 ulItemID );
    SteamAPICall_t DeleteAllTemporaryItems();
    void DeleteAllTemporaryItems_old();
    SteamAPICall_t UpdateQuantity( uint64 ulItemID, uint32 unNewQuantity );
    SteamAPICall_t GetItemBlob( uint64 ulItemID );
    SteamAPICall_t SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob );
};

#endif // __INCLUDED_STEAM_GAMESERVER_ITEMS_H__
