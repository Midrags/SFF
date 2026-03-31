
#ifndef ISTEAMUSERITEMS003_H
#define ISTEAMUSERITEMS003_H
#ifdef STEAM_WIN32
#pragma once
#endif

// this interface version is not found in public SDK archives, it is based on reversing old Linux binaries

class ISteamUserItems003
{
public:
	virtual SteamAPICall_t LoadItems() = 0;
	virtual SteamAPICall_t GetItemCount() = 0;
	virtual bool GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue ) = 0;
	virtual SteamAPICall_t UpdateInventoryPos( uint64 ulItemID, uint32 unNewInventoryPos ) = 0;
	virtual SteamAPICall_t DropItem_old2( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t GetItemBlob( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob ) = 0;
};

#endif // ISTEAMUSERITEMS003_H
