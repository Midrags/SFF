
#ifndef ISTEAMUSERITEMS001_H
#define ISTEAMUSERITEMS001_H
#ifdef STEAM_WIN32
#pragma once
#endif

// this interface version is not found in public SDK archives, it is based on reversing old Linux binaries

class ISteamUserItems001
{
public:
	virtual void LoadItems_old() = 0;
	virtual void GetItemCount_old() = 0;
	virtual bool GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue ) = 0;
	virtual void UpdateInventoryPos_old( uint64 ulItemID, uint32 unNewInventoryPos ) = 0;
	virtual void DropItem_old( uint64 ulItemID ) = 0;
};

struct DropItemResponse001_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 2 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

#endif // ISTEAMUSERITEMS001_H
