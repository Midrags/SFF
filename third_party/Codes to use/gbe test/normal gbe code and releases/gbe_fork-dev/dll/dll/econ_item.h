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

#ifndef __INCLUDED_ECON_ITEM_H__
#define __INCLUDED_ECON_ITEM_H__

#include "base.h"

//===============================================================================================================
// POSITION HANDLING
//===============================================================================================================
// TF Inventory Position cracking

// REALLY OLD FORMAT (??):
//      Bits 17-32 are the bag index (class index + 999, 1 is unequipped).
//      Bits 1-16 are the position of the item within the bag.
//      0 means item hasn't been acknowledged by the player yet.
//
// LESS OLD FORMAT (up through July, 2011):
//		If Bit 31 is 0: 
//			Bits 1-16 are the backpack position.
//			Bits 17-26 are a bool for whether the item is equipped in the matching class.
//		Otherwise, if Bit 31 is 1:
//			Item hasn't been acknowledged by the player yet.
//			Bits 1-16 are the method by the player found the item (see unacknowledged_item_inventory_positions_t)
//		Bit 32 is 1, to note the new format.
//
// CURRENT FORMAT:
//		If Bit 31 is 0: 
//			Bits 1-16 are the backpack position.
//		Otherwise, if Bit 31 is 1:
//			Item hasn't been acknowledged by the player yet.
//			Bits 1-16 are the method by the player found the item (see unacknowledged_item_inventory_positions_t)
//		Equipped state is stored elsewhere.
//		This is the only format that should exist on clients.
// Note (1/15/2013) For backwards compatibility, if the value is 0 item is considered unacknowledged too

struct Econ_Item_Attribute
{
    uint32 def;
    float value;
};

struct Econ_Item
{
    uint64 id;
    uint32 def;
    uint32 level;
    EItemQuality quality;
    uint32 inv_pos;
    uint32 quantity;
    uint8 flags;
    uint8 origin;
    std::string custom_name;
    std::string custom_desc;
    bool in_use;
    uint64 original_id;
    std::vector<Econ_Item_Attribute> attributes;
};

inline bool check_econ_item_name(const std::string &name)
{
    if (name.size() > 40)
        return false;

    return true;
}

inline bool check_econ_item_desc(const std::string &desc)
{
    if (desc.size() > 80)
        return false;

    return true;
}

#endif
