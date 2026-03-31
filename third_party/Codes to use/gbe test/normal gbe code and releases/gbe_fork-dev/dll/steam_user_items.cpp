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

#include "dll/steam_user_items.h"
#include "dll/dll.h"

Steam_Game_Coordinator *Steam_User_Items::gc()
{
    return get_steam_client()->steam_game_coordinator;
}

Steam_User_Items::Steam_User_Items(class Settings *settings, class SteamCallBacks *callbacks, class SteamCallResults *callback_results)
{
    this->settings = settings;
    this->callbacks = callbacks;
    this->callback_results = callback_results;
}

Steam_User_Items::~Steam_User_Items()
{
}

SteamAPICall_t Steam_User_Items::LoadItems()
{
    PRINT_DEBUG_ENTRY();
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    const auto &items = gc()->load_items_from_file();

    UserItemCount_t data{};
    data.m_gameID = settings->get_local_game_id();
    data.m_eResult = k_EItemRequestResultOK;
    data.m_unCount = static_cast<uint32>(items.size());
    SteamAPICall_t ret = callback_results->addCallResult(data.k_iCallback, &data, sizeof(data), 0.1);
    callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.1);
    return ret;
}

void Steam_User_Items::LoadItems_old()
{
    PRINT_DEBUG_ENTRY();
    LoadItems();
}

SteamAPICall_t Steam_User_Items::GetItemCount()
{
    PRINT_DEBUG_ENTRY();
    return LoadItems();
}

void Steam_User_Items::GetItemCount_old()
{
    PRINT_DEBUG_ENTRY();
    GetItemCount();
}

bool Steam_User_Items::GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount )
{
    PRINT_DEBUG("%u", iIndex);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    const auto &items = gc()->get_items();

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

bool Steam_User_Items::GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount )
{
    PRINT_DEBUG_ENTRY();
    uint32 quantity;
    return GetItemIterative(iIndex, pulItemID, punItemDefIndex, punItemLevel, peQuality, punInventoryPos, &quantity, punAttributeCount);
}

bool Steam_User_Items::GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount )
{
    PRINT_DEBUG("%llu", ulItemID);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    const auto &items = gc()->get_items();

    for (const Econ_Item &item : items) {
        if (item.id != ulItemID)
            continue;

        *punItemDefIndex = item.def;
        *punItemLevel = item.level;
        *peQuality = item.quality;
        *punInventoryPos = item.inv_pos;
        *punQuantity = item.quantity;
        *punAttributeCount = static_cast<uint32>(item.attributes.size());

        return true;
    }

    return false;
}

bool Steam_User_Items::GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount )
{
    PRINT_DEBUG_ENTRY();
    uint32 quantity;
    return GetItemByID(ulItemID, punItemDefIndex, punItemLevel, peQuality, punInventoryPos, &quantity, punAttributeCount);
}

bool Steam_User_Items::GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue )
{
    PRINT_DEBUG("%llu %u", ulItemID, unAttributeIndex);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    const auto &items = gc()->get_items();

    for (const Econ_Item &item : items) {
        if (item.id != ulItemID)
            continue;

        if (unAttributeIndex >= item.attributes.size())
            return false;

        *punAttributeDefIndex = item.attributes[unAttributeIndex].def;
        *pflAttributeValue = item.attributes[unAttributeIndex].value;

        return true;
    }

    return false;
}

SteamAPICall_t Steam_User_Items::UpdateInventoryPos( uint64 ulItemID, uint32 unNewInventoryPos )
{
    PRINT_DEBUG("%llu 0x%08X", ulItemID, unNewInventoryPos);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    if (gc()->set_item_pos(ulItemID, unNewInventoryPos, false)) {
        UpdateInventoryPosResponse_t data{};
        data.m_ulItemID = ulItemID;
        data.m_eResult = k_EItemRequestResultOK;
        SteamAPICall_t ret = callback_results->addCallResult(data.k_iCallback, &data, sizeof(data), 0.1);
        callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.1);
        return ret;
    }

    UpdateInventoryPosResponse_t data{};
    data.m_ulItemID = ulItemID;
    data.m_eResult = k_EItemRequestResultNoMatch;
    SteamAPICall_t ret = callback_results->addCallResult(data.k_iCallback, &data, sizeof(data), 0.1);
    callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.1);
    return ret;
}

void Steam_User_Items::UpdateInventoryPos_old( uint64 ulItemID, uint32 unNewInventoryPos )
{
    PRINT_DEBUG_ENTRY();
    UpdateInventoryPos(ulItemID, unNewInventoryPos);
}

SteamAPICall_t Steam_User_Items::DeleteItem( uint64 ulItemID )
{
    PRINT_DEBUG("%llu", ulItemID);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    if (gc()->delete_item(ulItemID, false)) {
        DeleteItemResponse_t data{};
        data.m_ulItemID = ulItemID;
        data.m_eResult = k_EItemRequestResultOK;
        SteamAPICall_t ret = callback_results->addCallResult(data.k_iCallback, &data, sizeof(data), 0.1);
        callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.1);
        return ret;
    }

    DeleteItemResponse_t data{};
    data.m_ulItemID = ulItemID;
    data.m_eResult = k_EItemRequestResultNoMatch;
    SteamAPICall_t ret = callback_results->addCallResult(data.k_iCallback, &data, sizeof(data), 0.1);
    callbacks->addCBResult(data.k_iCallback, &data, sizeof(data), 0.1);
    return ret;
}

void Steam_User_Items::DropItem_old( uint64 ulItemID )
{
    PRINT_DEBUG_ENTRY();
    DeleteItem(ulItemID);
}

SteamAPICall_t Steam_User_Items::DropItem_old2( uint64 ulItemID )
{
    PRINT_DEBUG_ENTRY();
    return DeleteItem(ulItemID);
}

SteamAPICall_t Steam_User_Items::GetItemBlob( uint64 ulItemID )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

SteamAPICall_t Steam_User_Items::SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}

SteamAPICall_t Steam_User_Items::DropItem( uint64 ulItemID )
{
    PRINT_DEBUG_TODO();
    return k_uAPICallInvalid;
}
