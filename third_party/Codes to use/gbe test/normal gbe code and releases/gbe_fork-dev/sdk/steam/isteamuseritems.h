
#ifndef ISTEAMUSERITEMS_H
#define ISTEAMUSERITEMS_H
#ifdef STEAM_WIN32
#pragma once
#endif

// this interface version is not found in public SDK archives, it is based on reversing old Linux binaries

enum EItemQuality
{
	k_EItemQuality_Invalid = -2,
	k_EItemQuality_Any = -1,
	k_EItemQuality_Normal = 0,
	k_EItemQuality_Common,
	k_EItemQuality_Rare,
	k_EItemQuality_Unique,
	k_EItemQuality_Count,
};

enum EItemRequestResult
{
	k_EItemRequestResultOK = 0,
	k_EItemRequestResultDenied,
	k_EItemRequestResultServerError,
	k_EItemRequestResultTimeout,
	k_EItemRequestResultInvalid,
	k_EItemRequestResultNoMatch,
	k_EItemRequestResultUnknownError,
	k_EItemRequestResultNotLoggedOn,
};

class ISteamUserItems
{
public:
	virtual SteamAPICall_t LoadItems() = 0;
	virtual SteamAPICall_t GetItemCount() = 0;
	virtual bool GetItemIterative( uint32 iIndex, uint64 *pulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemByID( uint64 ulItemID, uint32 *punItemDefIndex, uint32 *punItemLevel, EItemQuality *peQuality, uint32 *punInventoryPos, uint32 *punQuantity, uint32 *punAttributeCount ) = 0;
	virtual bool GetItemAttribute( uint64 ulItemID, uint32 unAttributeIndex, uint32 *punAttributeDefIndex, float *pflAttributeValue ) = 0;
	virtual SteamAPICall_t UpdateInventoryPos( uint64 ulItemID, uint32 unNewInventoryPos ) = 0;
	virtual SteamAPICall_t DeleteItem( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t GetItemBlob( uint64 ulItemID ) = 0;
	virtual SteamAPICall_t SetItemBlob( uint64 ulItemID, const void *pubBlob, uint32 cubBlob ) = 0;
	virtual SteamAPICall_t DropItem( uint64 ulItemID ) = 0;
};

#define STEAMUSERITEMS_INTERFACE_VERSION "STEAMUSERITEMS_INTERFACE_VERSION004"

struct UserItemCount_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 0 };
	CGameID m_gameID;
	EItemRequestResult m_eResult;
	uint32 m_unCount;
};

struct UpdateInventoryPosResponse_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 1 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

struct DeleteItemResponse_t // renamed from DropItemResponse_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 2 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

struct ItemGranted_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 3 };
	uint64 m_ulItemID;
	CGameID m_gameID;
};

struct GetItemBlobResponse_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 4 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
	uint8 m_pubBlob[1024];
	int32 m_cubBlob;
};

struct SetItemBlobResponse_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 5 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

struct ItemQuantityUpdated_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 6 };
	uint64 m_ulItemID;
};

struct ItemsRefreshed_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 7 };
};

struct DropItemResponse_t
{
	enum { k_iCallback = k_iClientDepotBuilderCallbacks + 8 };
	uint64 m_ulItemID;
	EItemRequestResult m_eResult;
};

#endif // ISTEAMUSERITEMS_H
