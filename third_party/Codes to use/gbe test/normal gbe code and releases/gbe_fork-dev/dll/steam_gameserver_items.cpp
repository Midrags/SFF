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

#include "dll/steam_gameserver_items.h"
#include "dll/dll.h"

Steam_Game_Coordinator *Steam_GameServer_Items::gc()
{
    return get_steam_client()->steam_gameserver_game_coordinator;
}

Steam_GameServer_Items::Steam_GameServer_Items(class Settings *settings, class SteamCallBacks *callbacks, class SteamCallResults *callback_results)
{
    this->settings = settings;
    this->callbacks = callbacks;
    this->callback_results = callback_results;
}

Steam_GameServer_Items::~Steam_GameServer_Items()
{
}

void Steam_GameServer_Items::on_items_received(CSteamID steam_id, size_t num_items, SteamAPICall_t api_call, bool success)
{
    GSItemCount_t data{};
    data.m_OwnerID = steam_id;
    if (success) {
        data.m_eResult = k_EItemRequestResultOK;
        data.m_unCount = static_cast<uint32>(num_items);
    } else {
        data.m_eResult = k_EItemRequestResultTimeout;
        data.m_unCount = 0;
    }
    callback_results->addCallResult(api_call, data.k_iCallback, &data, sizeof(data));
    callbacks->addCBResult(data.k_iCallback, &data, sizeof(data));
}

void Steam_GameServer_Items::on_item_pos_updated(CSteamID steam_id, uint64 item_id, uint32 inv_pos)
{
    GSItemInventoryPosUpdated_t data{};
    data.m_SteamID = steam_id;
    data.m_ulItemID = item_id;
    callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.15);
}

void Steam_GameServer_Items::on_item_deleted(CSteamID steam_id, uint64 item_id)
{
    GSItemDeleted_t data{};
    data.m_SteamID = steam_id;
    data.m_ulItemID = item_id;
    callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.15);
}

SteamAPICall_t Steam_GameServer_Items::LoadItems( CSteamID ownerID )
{
    PRINT_DEBUG("%llu", ownerID.ConvertToUint64());
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    // See if we already have their inventory cached.
    if (gc()->has_items_for_user(ownerID)) {
        const auto &items = gc()->get_items_for_user(ownerID);

        GSItemCount_t data{};
        data.m_OwnerID = ownerID;
        data.m_eResult = k_EItemRequestResultOK;
        data.m_unCount = static_cast<uint32>(items.size());
        SteamAPICall_t ret = callback_results->addCallResult(data.k_iCallback, &data, sizeof(data), 0.1);
        callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.1);
        return ret;
    }

    // See if we've already requested their inventory.
    SteamAPICall_t ret = gc()->find_items_request(ownerID);
    if (ret != k_uAPICallInvalid)
        return ret;

    // Request inventory from this player.
    ret = callback_results->reserveCallResult();
    gc()->request_user_items(ownerID, ret, false);
    return ret;
}

void Steam_GameServer_Items::LoadItems_old( CSteamID ownerID )
{
    PRINT_DEBUG_ENTRY();
    LoadItems(ownerID);
}

SteamAPICall_t Steam_GameServer_Items::GetItemCount( CSteamID ownerID )
{
    PRINT_DEBUG_ENTRY();
    return LoadItems(ownerID);
}

void Steam_GameServer_Items::GetItemCount_old( CSteamID ownerID )
{
    PRINT_DEBUG_ENTRY();
    GetItemCount(ownerID);
}

bool Steam_GameServer_Items::GetItemIterative( CSteamID ownerID, uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount )
{
    PRINT_DEBUG("%u", iIndex);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    if (!gc()->has_items_for_user(ownerID))
        return false;

    const auto &items = gc()->get_items_for_user(ownerID);
    if (iIndex >= items.size())
        return false;

    const Econ_Item &item = items[iIndex];
    *pulItemID = item.id;
    *punItemDefIndex = item.def;
    *punItemLevel = item.level;
    *peQuality = item.quality;
    *punInventoryPos = item.inv_pos;
    *punQuantity = item.quantity;
    *punAttributeCount = static_cast<uint32>(item.attributes.size());

    return true;
}

bool Steam_GameServer_Items::GetItemIterative( CSteamID ownerID, uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount )
{
    PRINT_DEBUG_ENTRY();
    uint32 quantity;
    return GetItemIterative(ownerID, iIndex, pulItemID, punItemDefIndex, punItemLevel, peQuality, punInventoryPos, &quantity, punAttributeCount);
}

bool Steam_GameServer_Items::GetItemByID( uint64 ulItemID, CSteamID *pOwnerID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount )
{
    PRINT_DEBUG("%llu", ulItemID);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    for (const auto &[steam_id, items] : gc()->get_all_user_items()) {
        for (const Econ_Item &item : items) {
            if (item.id != ulItemID)
                continue;

            *pOwnerID = steam_id;
            *punItemDefIndex = item.def;
            *punItemLevel = item.level;
            *peQuality = item.quality;
            *punInventoryPos = item.inv_pos;
            *punQuantity = item.quantity;
            *punAttributeCount = static_cast<uint32>(item.attributes.size());

            return true;
        }
    }

    return false;
}

bool Steam_GameServer_Items::GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount )
{
    PRINT_DEBUG_ENTRY();
    CSteamID steam_id;
    uint32 quantity;
    return GetItemByID(ulItemID, &steam_id, punItemDefIndex, punItemLevel, peQuality, punInventoryPos, &quantity, punAttributeCount);
}

bool Steam_GameServer_Items::GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue )
{
    PRINT_DEBUG("%llu %u", ulItemID, unAttributeIndex);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    for (const auto &[steamID, items] : gc()->get_all_user_items()) {
        for (const Econ_Item &item : items) {
            if (item.id != ulItemID)
                continue;

            if (unAttributeIndex >= item.attributes.size())
                return false;

            *punAttributeDefIndex = item.attributes[unAttributeIndex].def;
            *pflAttributeValue = item.attributes[unAttributeIndex].value;

            return true;
        }
    }

    return false;
}

HNewItemRequest Steam_GameServer_Items::CreateNewItemRequest( CSteamID steamID )
{
    PRINT_DEBUG_TODO();
    return 0;
}

HNewItemRequest Steam_GameServer_Items::CreateNewItemRequest( CSteamID steamID, uint32 unItemLevel, EItemQuality eQuality )
{
    PRINT_DEBUG_TODO();
    return 0;
}

bool Steam_GameServer_Items::AddNewItemLevel( HNewItemRequest handle, uint32 unItemLevel )
{
    PRINT_DEBUG_TODO();
    return false;
}

bool Steam_GameServer_Items::AddNewItemQuality( HNewItemRequest handle, EItemQuality eQuality )
{
    PRINT_DEBUG_TODO();
    return false;
}

bool Steam_GameServer_Items::SetNewItemInitialInventoryPos( HNewItemRequest handle, uint32 unInventoryPos )
{
    PRINT_DEBUG_TODO();
    return false;
}

bool Steam_GameServer_Items::SetNewItemInitialQuantity( HNewItemRequest handle, uint32 unQuantity )
{
    PRINT_DEBUG_TODO();
    return false;
}

bool Steam_GameServer_Items::AddNewItemCriteria( HNewItemRequest handle, const char *pchField, EItemCriteriaOperator eOperator, const char *pchValue, bool bRequired )
{
    PRINT_DEBUG_TODO();
    return false;
}

bool Steam_GameServer_Items::AddNewItemCriteria( HNewItemRequest handle, const char *pchField, EItemCriteriaOperator eOperator, float flValue, bool bRequired )
{
    PRINT_DEBUG_TODO();
    return false;
}

SteamAPICall_t Steam_GameServer_Items::SendNewItemRequest( HNewItemRequest handle )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

void Steam_GameServer_Items::SendNewItemRequest_old( HNewItemRequest handle )
{
    PRINT_DEBUG_ENTRY();
    SendNewItemRequest(handle);
}

SteamAPICall_t Steam_GameServer_Items::GrantItemToUser( uint64 ulItemID, CSteamID steamIDRecipient )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

void Steam_GameServer_Items::GrantItemToUser_old( uint64 ulItemID, CSteamID steamIDRecipient )
{
    PRINT_DEBUG_ENTRY();
    GrantItemToUser(ulItemID, steamIDRecipient);
}

SteamAPICall_t Steam_GameServer_Items::DeleteTemporaryItem( uint64 ulItemID )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

void Steam_GameServer_Items::DeleteTemporaryItem_old( uint64 ulItemID )
{
    PRINT_DEBUG_ENTRY();
    DeleteTemporaryItem(ulItemID);
}

SteamAPICall_t Steam_GameServer_Items::DeleteAllTemporaryItems()
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

void Steam_GameServer_Items::DeleteAllTemporaryItems_old()
{
    PRINT_DEBUG_ENTRY();
    DeleteAllTemporaryItems();
}

SteamAPICall_t Steam_GameServer_Items::UpdateQuantity( uint64 ulItemID, uint32 unNewQuantity )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

SteamAPICall_t Steam_GameServer_Items::GetItemBlob( uint64 ulItemID )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

SteamAPICall_t Steam_GameServer_Items::SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}
