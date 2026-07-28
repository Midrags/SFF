// LumaCore — Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

// LumaCore in-process layout descriptors.
//
// Each struct in this header pins the byte layout LumaCore needs in order
// to read or rewrite live Steam client memory from a hook. The shapes are
// pinned by static_assert further down so a Steam update that shuffles a
// field will fail the LumaCore build instead of corrupting state at run
// time.

#include "Types.h"
#include "Enums.h"

#include <string>
#include <format>

template<typename T>
struct CUtlMemory{
	T* m_pMemory;
	uint32 m_nAllocationCount;
	uint32 m_nGrowSize;
};

template<typename T>
struct CUtlVector {
	CUtlMemory<T> m_Memory;
	uint32 m_Size;

	// Drop-by-swap removal: copy the tail element over the slot at `elem`
	// and shrink. Cheap, but the surviving element order is no longer the
	// insertion order. LumaCore call sites that walk the vector once are
	// fine with that; anything that needs stable order should not use it.
	void FastRemove(uint32 elem) {
		if (elem < m_Size) {
			if (elem != m_Size - 1)
				m_Memory.m_pMemory[elem] = m_Memory.m_pMemory[m_Size - 1];
			--m_Size;
		}
	}

	bool FindAndFastRemove(const T& src) {
		for (uint32 i = 0; i < m_Size; ++i) {
			if (m_Memory.m_pMemory[i] == src) {
				FastRemove(i);
				return true;
			}
		}
		return false;
	}
};

struct CUtlBuffer{
	CUtlMemory<uint8> m_Memory;
	int32 m_Get;
	int32 m_Put;
	int32 m_nOffset;
	int32 m_flags;

	typedef bool (CUtlBuffer::*UtlBufferOverflowFunc_t)( int32 nSize );
	UtlBufferOverflowFunc_t m_GetOverflowFunc;
	UtlBufferOverflowFunc_t m_PutOverflowFunc;

	// Direct base + cursor accessors. LumaCore needs these so a hook
	// can splice into the underlying buffer without duplicating every
	// member access at the call site.
	uint8* Base()             { return m_Memory.m_pMemory; }
	const uint8* Base() const { return m_Memory.m_pMemory; }
	int32 TellPut() const     { return m_Put; }
	int32 TellGet() const     { return m_Get; }
	// Diagnostics dump, used by LumaCore logs to make a sliced buffer
	// readable in a single line.
	std::string DebugString() const{
      return std::format("m_Memory:0x{:X} m_AllocCnt:{} m_Grow:{} m_Get:{} m_Put:{} m_nOffset:{} m_flags:{}",
          reinterpret_cast<uintptr_t>(m_Memory.m_pMemory),
          m_Memory.m_nAllocationCount, m_Memory.m_nGrowSize,
          m_Get, m_Put, m_nOffset, m_flags);
  }
};

struct PackageInfo
{
	AppId_t PackageId;
	int32 ChangeNumber;
	uint64 PICS_token;
	BillingType BillingType;
	ELicenseType LicenseType;
	EPackageStatus Status;
	byte SHA_1_Hash[20];
	void* pPackageInfoNodeBegin;
	void* pExtendNodeBegin;

	CUtlVector<AppId_t> AppIdVec;
	CUtlVector<AppId_t> DepotIdVec;
};

struct AppOwnership
{
        PackageId_t PackageId;
        EAppReleaseState ReleaseState;
        AccountID_t SteamId32;
        AppId_t MasterSubscriptionAppID;
        uint32 TrialSeconds;
        uint32 ExistInPackageNums;
        char PurchaseCountryCode[4];
        uint32 TimeStamp;
        uint32 TimeExpire;
        bool bOwnsLicense;
        bool bLicenseExpired;
        bool bIsPermanent;
        bool bLowViolence;
        bool bFreeLicense;
        bool bRegionRestricted;
        bool bFromFreeWeekend;
        bool bLicenseLocked;
        bool bLicensePending;
        bool bRetailLicense;
        bool bAutoGrant;
        bool bLicensePermanent;
        bool bGuestPass;
        bool bBorrowed;
        bool bAnySiteLicense;
        bool bAllSiteLicenses;
        bool bAllActivationRequired;
        bool bFamilyShared;
};

#pragma pack(push,1)
struct CSteamApp{
	void** vfptr;
	uint8  _pad0[20];
	EAppOwnershipFlags OwnershipFlags;
	EAppState AppStateFlags;
};
#pragma pack(pop)

// One depot record (32 bytes) emitted by the depot dependency builder.
// LumaCore reads these out of the resolved dependency vector and feeds
// the LcsRequired flag plus the manifest GID into its registration path.
struct DepotEntry
{
	uint32  DepotId;        // 0x00
	uint32  AppId;          // 0x04
	uint64  ManifestGid;    // 0x08, sourced from depots/<id>/manifests/<branch>/gid
	uint64  ManifestSize;   // 0x10, sourced from depots/<id>/manifests/<branch>/size
	uint32  DlcAppId;       // 0x18, paired DLC AppID, zero if there is no DLC
	uint8   LcsRequired;    // 0x1C, taken from branches/<branch>/lcsrequired
	uint8   bNotNewTarget;  // 0x1D, carried from the active list, not activated by this call
	uint8   SharedInstall;  // 0x1E, sharedinstall + depotfromapp redirect bit
	uint8   Padding;        // 0x1F
};
static_assert(sizeof(DepotEntry) == 0x20, "LumaCore depot record size drift: DepotEntry no longer matches the 0x20-byte layout LumaCore expects");

struct KeyValues
{
	union                                   // +0x00 (8B), value slot, or the head of the child list
	{
		KeyValues*      m_pSub;             // TYPE_NONE, points at the first child
		char*           m_sValue;           // TYPE_STRING
		wchar_t*        m_wsValue;          // TYPE_WSTRING
		int             m_iValue;           // TYPE_INT
		float           m_flValue;          // TYPE_FLOAT
		void*           m_pValue;           // TYPE_PTR
		uint64			m_ullValue;         // TYPE_UINT64
		int64           m_llValue;          // TYPE_INT64
		byte   			m_Color[8];         // TYPE_COLOR
	};

	KeyValues*          m_pChain;           // +0x08 (8B), chained KeyValues used as a fallback during lookup

	// +0x10 (4B), packed bitfield. Layout LumaCore depends on:
	//   bit[0:24]  m_iKeyName              (25 bits) symbol assigned by the KeyValues string pool
	//   bit[25:28] m_iDataType             (4 bits)  value-type discriminant, see EKeyValuesType
	//   bit[29]    m_bHasEscapeSequences             escape sequences were enabled at parse time
	//   bit[30]    m_bEvaluateConditionals           conditional blocks were evaluated at parse time
	//   bit[31]    m_bAllocatedValue                 the value sits on the heap, dereference offset 0
	union
	{
		struct
		{
			unsigned int m_iKeyName              : 25;
			unsigned int m_iDataType             : 4;
			unsigned int m_bHasEscapeSequences   : 1;
			unsigned int m_bEvaluateConditionals : 1;
			unsigned int m_bAllocatedValue       : 1;
		};
		unsigned int m_iPackedKeyAndType;    // raw DWORD view of the bitfield above
	};

	unsigned int        m_unFlags;          // +0x14 (4B), spare flag word

	KeyValues*          m_pPeer;            // +0x18 (8B), next sibling node in the linked list

};
static_assert(sizeof(KeyValues) == 0x20, "LumaCore KeyValues node size drift: KeyValues no longer matches the 0x20-byte layout LumaCore expects");

// IKeyValuesSystem
//   LumaCore resolves this interface through the export
//   "KeyValuesSystemSteam" (ord 103) from vstdlib_s64.dll. LumaCore
//   consumes the first three vtable slots only, so the rest are
//   sketched in comments rather than declared.
struct IKeyValuesSystem {
	// vtable[0] (+0x00), records the maximum KeyValues node size used by
	// the KeyValues memory pool.
	virtual void        RegisterSizeofKeyValues(int size) = 0;

	// vtable[1] (+0x08), hash a string and return its symbol; create a
	// fresh entry when bCreate is true.
	//   Symbol = (pool_index << 15) | byte_offset_within_pool
	//   Returns 0 for a null/empty name when bCreate is false.
	virtual int         GetSymbolForString(const char* name, bool bCreate) = 0;

	// vtable[2] (+0x10), O(1) reverse lookup from a symbol back to its
	// string pointer. Invalid or zero symbols read back as "".
	virtual const char* GetStringForSymbol(int symbol) = 0;

	// vtable[3..11] cover allocation, leak tracking, and file caching.
	// LumaCore does not call these, so the slots stay undeclared.

	// Convenience helpers used by LumaCore call sites.
	int  GetSymbol(const char* name)        { return GetSymbolForString(name, false); }
	int  GetOrCreateSymbol(const char* name) { return GetSymbolForString(name, true); }
	const char* GetKeyName(int symbol)       { return GetStringForSymbol(symbol); }
};
using KeyValuesSystemSteam_t = IKeyValuesSystem* (*)();

struct CNetPacket
{
	HCONNECTION m_hConnection;
	uint8* m_pubData;
	uint32 m_cubData;
	int32 m_cRef;
	uint8* m_pubNetworkBuffer;
	CNetPacket* m_pNext;
};

struct MsgHdr
{
	EMsg eMsg;               // raw value: actual_eMsg OR 0x80000000
	uint32 headerLength;
};

// LumaCore branches on the high bit of eMsg to pick between the protobuf
// header path and the extended-header path.
constexpr uint32 kMsgHdrProtoFlag = 0x80000000;

#pragma pack(push,1)
struct ExtendedMsgHdr
{
	EMsg eMsg;
	uint8 m_nCubHdr;
	uint16 m_nHdrVersion;
	JobID_t m_JobIDTarget;
	JobID_t m_JobIDSource;
	uint8 m_nHdrCanary;
	uint64 m_ulSteamID;
	int32 m_nSessionID;
};
#pragma pack(pop)

// CSteamPipeClient: layout LumaCore reads back from the live pipe object.
struct CSteamPipeClient {
    void*    m_pServer;         // +0
    void*    m_pClient;         // +8
    uint32   m_hSteamPipe;      // +16
    uint8    _pad0[12];         // +20
    uint32   m_clientPID;       // +32
    uint8    _pad1[4];          // +36
    char*    m_szProcessName;   // +40
    uint8    _pad2[80];         // +48
    int32    m_nActiveRefs;     // +128
    uint8    _pad3[188];        // +132
    void*    m_pLocalIPCServer; // +320
    bool     m_bInProcess;      // +328
    uint8    _pad4[31];         // +329

	std::string DebugString() const {
		return std::format("pipe=0x{:08X} pid={} proc={} ",
			m_hSteamPipe, m_clientPID, m_szProcessName ? m_szProcessName : "?");
	}
};
