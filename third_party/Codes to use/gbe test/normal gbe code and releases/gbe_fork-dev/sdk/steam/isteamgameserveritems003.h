
#ifndef ISTEAMGAMESERVERITEMS003_H
#define ISTEAMGAMESERVERITEMS003_H
#ifdef STEAM_WIN32
#pragma once
#endif

// this interface version is not found in public SDK archives, it is based on reversing old Linux binaries

class ISteamGameServerItems003
{
public:
	virtual void LoadItems_old( CSteamID ownerID ) = 0;
	virtual void GetItemCount_old( CSteamID ownerID ) = 0;
	virtual bool GetItemIterative( CSteamID ownerID, uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemByID( uint64 ulItemID, CSteamID *pOwnerID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue ) = 0;
	virtual HNewItemRequest CreateNewItemRequest( CSteamID steamID ) = 0;
	virtual bool AddNewItemLevel( HNewItemRequest handle, uint32 unItemLevel ) = 0;
	virtual bool AddNewItemQuality( HNewItemRequest handle, EItemQuality eQuality ) = 0;
	virtual bool SetNewItemInitialInventoryPos( HNewItemRequest handle, uint32 unInventoryPos ) = 0;
	virtual bool SetNewItemInitialQuantity( HNewItemRequest handle, uint32 unQuantity ) = 0;
	virtual bool AddNewItemCriteria( HNewItemRequest handle, const char *pchField, EItemCriteriaOperator eOperator, const char *pchValue, bool bRequired ) = 0;
	virtual bool AddNewItemCriteria( HNewItemRequest handle, const char *pchField, EItemCriteriaOperator eOperator, float flValue, bool bRequired ) = 0;
	virtual void SendNewItemRequest_old( HNewItemRequest handle ) = 0;
	virtual void GrantItemToUser_old( uint64 ulItemID, CSteamID steamIDRecipient ) = 0;
	virtual void DeleteTemporaryItem_old( uint64 ulItemID ) = 0;
	virtual void DeleteAllTemporaryItems_old() = 0;
	virtual SteamAPICall_t UpdateQuantity( uint64 ulItemID, uint32 unNewQuantity ) = 0;
	virtual SteamAPICall_t GetItemBlob( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob ) = 0;
};

#endif // ISTEAMGAMESERVERITEMS003_H
