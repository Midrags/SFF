
#ifndef ISTEAMGAMESERVERITEMS_H
#define ISTEAMGAMESERVERITEMS_H
#ifdef STEAM_WIN32
#pragma once
#endif

// this interface version is not found in public SDK archives, it is based on reversing old Linux binaries

#include "isteamuseritems.h"

enum EItemCriteriaOperator
{
	k_EOperator_String_EQ = 0,
	k_EOperator_Not,
	k_EOperator_String_Not_EQ = k_EOperator_Not,
	k_EOperator_Float_EQ,
	k_EOperator_Float_Not_EQ,
	k_EOperator_Float_LT,
	k_EOperator_Float_Not_LT,
	k_EOperator_Float_LTE,
	k_EOperator_Float_Not_LTE,
	k_EOperator_Float_GT,
	k_EOperator_Float_Not_GT,
	k_EOperator_Float_GTE,
	k_EOperator_Float_Not_GTE,
	k_EOperator_Subkey_Contains,
	k_EOperator_Subkey_Not_Contains,
	k_EItemCriteriaOperator_Count,
};

typedef int32 HNewItemRequest;

class ISteamGameServerItems
{
public:
	virtual SteamAPICall_t LoadItems( CSteamID ownerID ) = 0;
	virtual SteamAPICall_t GetItemCount( CSteamID ownerID ) = 0;
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
	virtual SteamAPICall_t SendNewItemRequest( HNewItemRequest handle ) = 0;
	virtual SteamAPICall_t GrantItemToUser( uint64 ulItemID, CSteamID steamIDRecipient ) = 0;
	virtual SteamAPICall_t DeleteTemporaryItem( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t DeleteAllTemporaryItems() = 0;
	virtual SteamAPICall_t UpdateQuantity( uint64 ulItemID, uint32 unNewQuantity ) = 0;
	virtual SteamAPICall_t GetItemBlob( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob ) = 0;
};

#define STEAMGAMESERVERITEMS_INTERFACE_VERSION "STEAMGAMESERVERITEMS_INTERFACE_VERSION004"

struct GSItemCount_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 0 };
	CSteamID m_OwnerID;
	EItemRequestResult m_eResult;
	uint32 m_unCount;
};

struct GSNewItemRequestResponse_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 1 };
	CSteamID m_SteamID;
	EItemRequestResult m_eResult;
	uint64 m_ulItemID;
	HNewItemRequest m_hRequest;
};

struct GSItemInventoryPosUpdated_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 2 };
	CSteamID m_SteamID;
	uint64 m_ulItemID;
};

struct GSItemDeleted_t // renamed from GSItemDropped_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 3 };
	CSteamID m_SteamID;
	uint64 m_ulItemID;
};

struct GSGrantItemToUser_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 4 };
	EItemRequestResult m_eResult;
	uint64 m_ulItemIDOld;
	uint64 m_ulItemIDPermanent;
	CSteamID m_SteamID;
};

struct GSDeleteTemporaryItem_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 5 };
	EItemRequestResult m_eResult;
	uint64 m_ulItemID;
};

struct GSDeleteAllTemporaryItems_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 6 };
	EItemRequestResult m_eResult;
};

struct GSItemAdded_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 7 };
	CSteamID m_SteamID;
	uint64 m_ulItemID;
};

struct GSGetItemBlobResponse_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 8 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
	uint8 m_pubBlob[1024];
	int32 m_cubBlob;
};

struct GSSetItemBlobResponse_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 9 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

struct GSUpdateQuantity_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 10 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

struct GSItemsRefreshed_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 11 };
};

struct GSItemDropped_t
{
	enum { k_iCallback = k_iSteamGameServerItemsCallbacks + 12 };
	CSteamID m_SteamID;
	uint64 m_ulItemID;
};

#endif // ISTEAMGAMESERVERITEMS_H
