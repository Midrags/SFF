#include "steam_old_lib/steam_old_lib.hpp"
#include "steam_old_lib/SteamCommon.h"

#include "common_helpers/common_helpers.hpp"

#define INCLUDED_STEAM2_USERID_STRUCTS
#include "dll/common_includes.h"

#include <string>
#include <stdexcept>
#include <string_view>
#include <cstdint>

#include <stdlib.h> // getenv
#include <stddef.h> // size_t
#include <cstring> // std::strncpy
#include <string_view>
#include <string>
#include <list>


#define SOLD_ERR_OK 1
#define SOLD_ERR_FAIL 0

#define SOLD_ITF_CODE_OK 0
#define SOLD_ITF_CODE_FAIL 1


using CreateInterface_t = void* (__cdecl *)( const char *pName, int *pReturnCode );

constexpr const static char SOLD_ITF_NAME_CLIENT[]   = "SteamClient017";
constexpr const static char SOLD_ITF_NAME_UTILS[]    = "SteamUtils009";
constexpr const static char SOLD_ITF_NAME_USER[]     = "SteamUser019";
constexpr const static char SOLD_ITF_NAME_APPS[]     = "STEAMAPPS_INTERFACE_VERSION008";
constexpr const static char SOLD_ITF_NAME_FRIENDS[]  = "SteamFriends017";

// we have to use specific headers (ex: ISteamClient017 vs ISteamClient)
// otherwise direct pointer access would result in invalid vftable access
// because we earlier requested a specific version via CreateInterface()
static ISteamClient017 *sold_steam_client = nullptr;
static ISteamUtils009 *sold_steam_utils = nullptr;
static ISteamUser019 *sold_steam_user = nullptr;
static ISteamApps008 *sold_steam_apps = nullptr;

static sold::steamclient_loader_t *steamclient_loader = nullptr;
static CreateInterface_t ptrCreateInterface = nullptr;

static HSteamPipe sold_hsteam_pipe = 0;
static HSteamUser sold_hsteam_user = 0;

static bool startup_ok = false;

static uint32 sold_game_appid = 0;

static char game_installpath[1024]{};
static DepotId_t installed_depots[64]{};

constexpr const static TSteamAppInfo apps_infos[] = {
    { 8600,  "RACE 07" },
    { 8610,  "RACE 07 Dedicated Server" },
    { 8640,  "RACE On" },
    { 8641,  "RACE 07_Exp_Toad" },
    { 8650,  "RACE 07 - Andy Priaulx Crowne Plaza Expansion" },
    { 8660,  "GTR Evolution" },
    { 8690,  "STCC - The Game" },
    { 44620, "STCC 2" },
    { 44621, "RACE 07_Exp_Frog2" },
    { 44630, "RACE 07 - Formula RaceRoom Add-On" },
    { 44631, "RACE 07_Exp_MosquitoPack1" },
    { 44650, "GT Power Expansion" },
    { 44651, "RACE 07_Exp_MosquitoPack3" },
    { 44660, "The Retro Expansion" },
    { 44661, "RACE 07_Exp_MosquitoPack4" },
    { 44670, "WTCC 2010" },
    { 44671, "RACE 07_Exp_MosquitoPack5" },
    { 44680, "Race Injection" },
    { 44681, "RACE 07_Exp_Mosquito" },
    { 44683, "RACE 07_Exp_MosquitoIntro" },
    { 44711, "RACE 07_Exp_MosquitoPack4Beta" },
};
constexpr const static unsigned APPS_INFOS_COUNT = sizeof(apps_infos) / sizeof(apps_infos[0]);

constexpr const static std::string_view servers_list[] = {
    "208.64.200.65:27015",
    "208.64.200.39:27011",
    "208.64.200.52:27011",
};
constexpr const static unsigned SERVERS_LIST_COUNT = sizeof(servers_list) / sizeof(servers_list[0]);


static void set_ok_err(TSteamError *pError) {
    if (pError) {
        pError->eSteamError = ESteamError::eSteamErrorNone;
        pError->eDetailedErrorType = EDetailedPlatformErrorType::eNoDetailedErrorAvailable;
        pError->nDetailedErrorCode = 0;
        pError->szDesc[0] = 0;
    }
}

static void set_steam_err(TSteamError *pError, const char *desc = "", ESteamError eSteamError = ESteamError::eSteamErrorUnknown) {
    if (pError) {
        pError->eSteamError = eSteamError;
        pError->eDetailedErrorType = EDetailedPlatformErrorType::eNoDetailedErrorAvailable;
        pError->nDetailedErrorCode = ESteamError::eSteamErrorBadArg;
        if (desc) {
            std::strncpy(pError->szDesc, desc, sizeof(pError->szDesc) - 1);
        }
    }
}

static int set_wrapper_not_impl_err(TSteamError *pError)
{
    PRINT_DEBUG_ENTRY();
    set_steam_err(pError, "Wrapper not implemented", ESteamError::eSteamErrorUnknown);
    return SOLD_ERR_FAIL;
}

static void* create_interface_internal(const char *pName, int *pReturnCode)
{
    PRINT_DEBUG("'%s'", pName);
    if (!ptrCreateInterface) {
        ptrCreateInterface = reinterpret_cast<CreateInterface_t>(steamclient_loader(true));
        if (!ptrCreateInterface) {
            PRINT_DEBUG("[X] failed to load steamclient.dll or find CreateInterface()");
            if (pReturnCode) *pReturnCode = SOLD_ITF_CODE_FAIL;
            return nullptr;
        } else {
            PRINT_DEBUG("loaded steamclient.dll, CreateInterface() @ %p", ptrCreateInterface);
        }
    }

    return ptrCreateInterface(pName, pReturnCode);
}



STEAM_API void* CreateInterface(const char *pName, int *pReturnCode)
{
    PRINT_DEBUG("'%s'", pName);
    return create_interface_internal(pName, pReturnCode);
}

STEAM_API int STEAM_CALL SteamAbortCall( SteamCallHandle_t handle, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    return SOLD_ERR_OK;
}

STEAM_API void STEAM_CALL SteamAbortOngoingUserIDTicketValidation( SteamUserIDTicketValidationHandle_t Handle )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamAckSubscriptionReceipt( unsigned int uSubscriptionId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamBlockingCall( SteamCallHandle_t handle, unsigned int uiProcessTickMS, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    return SOLD_ERR_OK;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamChangeAccountName( const char *cszCurrentPassphrase, const char *cszNewAccountName, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamChangeEmailAddress( const char *cszNewEmailAddress, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamChangeForgottenPassword( const char *cszUser, const char *cszAnswerToQuestion, const char *cszEmailVerificationKey, const char *cszNewPassphrase, int *pbChanged, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamChangeOfflineStatus( TSteamOfflineStatus *pStatus, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamChangePassword( const char *cszCurrentPassphrase, const char *cszNewPassphrase, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamChangePersonalQA( const char *cszCurrentPassphrase, const char *cszNewPersonalQuestion, const char *cszNewAnswerToQuestion, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamCheckAppOwnership( unsigned int uAppId, int* pbOwned, TSteamGlobalUserID* pSteamID, TSteamError* pError )
{
    PRINT_DEBUG("%u", uAppId);
    set_ok_err(pError);

    // real dll doesn't check for null
    if (pbOwned) *pbOwned = 0;

    if (!sold_steam_user) {
        PRINT_DEBUG("[X] SteamUser is null!");
        return SOLD_ERR_FAIL;
    }
 
    CSteamID account_steamid = sold_steam_user->GetSteamID();
    // real dll doesn't check for null
    if (pSteamID && account_steamid == SteamIDFromSteam2UserID(pSteamID, account_steamid.GetEUniverse())) {
        // real dll doesn't check for null
        bool subed = sold_steam_apps && sold_steam_apps->BIsSubscribedApp(uAppId);
        // real dll doesn't check for null
        if (pbOwned) *pbOwned = subed;

        PRINT_DEBUG("is subbed = %i", (int)subed);
        return SOLD_ERR_OK;
    }

    PRINT_DEBUG("[X] pSteamID is null or not same account");
    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamCleanup( TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    if (sold_steam_client) {
        sold_steam_client->ReleaseUser(sold_hsteam_pipe, sold_hsteam_user);
        sold_steam_client->BReleaseSteamPipe(sold_hsteam_pipe);
        sold_steam_client = nullptr;
    }

    sold_steam_utils = nullptr;
    sold_steam_user = nullptr;
    sold_steam_apps = nullptr;

    startup_ok = false;

    // free steamclient lib, don't do that here some games still need the steamclient dll
    // if (steamclient_loader) {
    //     steamclient_loader(false);
    //     PRINT_DEBUG("[?] unloaded steamclient.dll");
    // }

    // free Steam2.dll lib
    return SOLD_ERR_OK;
}

STEAM_API void STEAM_CALL SteamClearError( TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);
}

STEAM_API int STEAM_CALL SteamCloseFile( SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamCreateAccount( const char *cszUser, const char *cszEmailAddress, const char *cszPassphrase, const char *cszCreationKey, const char *cszPersonalQuestion, const char *cszAnswerToQuestion, int *pbCreated, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamCreateCachePreloaders( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamHandle_t STEAM_CALL SteamCreateLogContext( const char *cszName )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return STEAM_INVALID_HANDLE;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamDefragCaches( unsigned int uAppId, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamDeleteAccount( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamEnumerateApp( unsigned int uId, TSteamApp *pApp, TSteamError *pError )
{
    static std::list<std::string> custom_names{};

    // this implementation is incomplete, real dll does some other stuff
    PRINT_DEBUG_TODO();
    PRINT_DEBUG("%u", uId);
    set_ok_err(pError);

    if (pApp) {
        pApp->uId = uId;
        pApp->uLatestVersionId = 1;
        pApp->uCurrentVersionId = 1;
        pApp->uMinCacheFileSizeMB = 1;
        pApp->uMaxCacheFileSizeMB = 1;
        pApp->uNumLaunchOptions = 1;
        pApp->uNumIcons = 0;
        pApp->uNumVersions = 1;
    }

    const TSteamAppInfo *ptr_info = nullptr;
    for (auto &app_info : apps_infos) {
        if (app_info.uAppId == uId) {
            ptr_info = &app_info;
            break;
        }
    }

    if (ptr_info) {
        std::strncpy(pApp->szName, ptr_info->szAppName, pApp->uMaxNameChars);
    } else {
        // readl dll returns formatted "Steam App %u"
        auto &name = custom_names.emplace_back("Steam App " + std::to_string(uId));
        std::strncpy(pApp->szName, name.c_str(), pApp->uMaxNameChars);
    }
    std::strncpy(pApp->szLatestVersionLabel, "1", pApp->uMaxLatestVersionLabelChars);
    std::strncpy(pApp->szCurrentVersionLabel, "1", pApp->uMaxCurrentVersionLabelChars);

    sold_steam_apps->GetAppInstallDir(uId, pApp->szInstallDirName, pApp->uMaxInstallDirNameChars);

    DepotId_t vecDepots[32]{};
    uint32 depots_count = sold_steam_apps->GetInstalledDepots(uId, vecDepots, sizeof(vecDepots) / sizeof(vecDepots[0]));
    pApp->uNumDependencies = depots_count;

    PRINT_DEBUG("appid %u, dependencies %u", uId, depots_count);
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamEnumerateAppDependency( unsigned int uAppId, unsigned int uIndex, TSteamAppDependencyInfo *pDependencyInfo, TSteamError *pError )
{
    PRINT_DEBUG("%u [%u]", uAppId, uIndex);
    set_ok_err(pError);

    DepotId_t vecDepots[32];
    memset(vecDepots, 0, sizeof(vecDepots));
    
    // real dll doesn't check for null
    uint32 depots_count = sold_steam_apps
        ? sold_steam_apps->GetInstalledDepots(uAppId, vecDepots, sizeof(vecDepots) / sizeof(vecDepots[0]))
        : 0;
    
    PRINT_DEBUG("depots count=%u", depots_count);
    if (uIndex < depots_count) {
        char mount_path[sizeof(TSteamAppDependencyInfo::szMountPath)]{};
        // real dll doesn't check for null
        if (sold_steam_apps) {
            sold_steam_apps->GetAppInstallDir(uAppId, mount_path, sizeof(mount_path));
        }
        // real dll doesn't check for null
        if (pDependencyInfo) {
            pDependencyInfo->uAppId = vecDepots[uIndex];
            memcpy(pDependencyInfo->szMountPath, mount_path, sizeof(pDependencyInfo->szMountPath));
            pDependencyInfo->bIsSystemDefined = 1;
        }
        PRINT_DEBUG("app install/mount dir '%s'", mount_path);
    } else {
        // real dll doesn't check for null
        if (pDependencyInfo) {
            pDependencyInfo->uAppId = 0;
            pDependencyInfo->szMountPath[0] = 0;
            pDependencyInfo->bIsSystemDefined = 0;
        }
        PRINT_DEBUG("[X] index out of range");
    }
    
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamEnumerateAppIcon( unsigned int uAppId, unsigned int uIconIndex, unsigned char *pIconData, unsigned int uIconDataBufSize, unsigned int *puSizeOfIconData, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamEnumerateAppLaunchOption( unsigned int uAppId, unsigned int uLaunchOptionIndex, TSteamAppLaunchOption *pLaunchOption, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamEnumerateAppVersion( unsigned int uAppId, unsigned int uVersionIndex, TSteamAppVersion *pAppVersion, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamEnumerateSubscription( unsigned int uId, TSteamSubscription *pSubscription, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamEnumerateSubscriptionDiscount( unsigned int uSubscriptionId, unsigned int uDiscountIndex, TSteamSubscriptionDiscount *pDiscount, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamEnumerateSubscriptionDiscountQualifier( unsigned int uSubscriptionId, unsigned int uDiscountIndex, unsigned int uQualifierIndex, TSteamDiscountQualifier *pDiscountQualifier, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamFindApp( const char *cszAppName, unsigned int *puAppId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamFindClose( SteamHandle_t hDirectory, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API SteamHandle_t STEAM_CALL SteamFindFirst( const char *cszPattern, ESteamFindFilter eFilter, TSteamElemInfo *pFindInfo, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API SteamHandle_t STEAM_CALL SteamFindFirst64( const char *cszPattern, ESteamFindFilter eFilter, TSteamElemInfo64 *pFindInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamFindNext( SteamHandle_t hDirectory, TSteamElemInfo *pFindInfo, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamFindNext64( SteamHandle_t hDirectory, TSteamElemInfo64 *pFindInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API const char* STEAM_CALL SteamFindServersGetErrorString()
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return "Wrapper not implemented: SteamFindServersXXX";
}

STEAM_API int STEAM_CALL SteamFindServersIterateServer(ESteamServerType eSteamServerType, unsigned int uIndex, char *szServerAddress, int iServerAddressChars)
{
    PRINT_DEBUG("<%u> %u", eSteamServerType, uIndex);
    if ((eSteamServerType == ESteamServerType::eSteamHalfLife2MasterServer) && (uIndex < SERVERS_LIST_COUNT)) {
        // real dll doesn't check for null
        if (szServerAddress && iServerAddressChars > 0) {
            auto copied = servers_list[uIndex].copy(szServerAddress, iServerAddressChars - 1);
            szServerAddress[copied] = 0;
        }
        return 0;
    }

    // real dll doesn't check for null
    if (szServerAddress && iServerAddressChars > 0) *szServerAddress = 0;
    return -1;
}

STEAM_API int STEAM_CALL SteamFindServersNumServers( ESteamServerType eSteamServerType )
{
    PRINT_DEBUG("<%u>", eSteamServerType);
    int count = 0;
    if (eSteamServerType == ESteamServerType::eSteamHalfLife2MasterServer) {
        count = (int)SERVERS_LIST_COUNT;
    }
    return count;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamFlushCache( unsigned int uCacheId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamFlushFile( SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamForceCellId( unsigned int uCellId, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamForgetAllHints( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamGenerateSuggestedAccountNames( const char *cszAccountNameToSelectMasterAS, const char *cszGenerateNamesLikeAccountName, char *pSuggestedNamesBuf, unsigned int uBufSize, unsigned int *puNumSuggestedChars, TSteamError *pError)
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAccountStatus( unsigned int *puAccountStatusFlags, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamGetAppCacheSize( unsigned int uCacheId, unsigned int *pCacheSizeInMb, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAppDLCStatus( unsigned int uAppId, unsigned int uDLCCacheId, int *pbDownloaded, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAppDependencies( unsigned int uAppId, unsigned int *puCacheIds, unsigned int uMaxIds, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAppDir( unsigned int uAppId, char *szPath, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAppIds( unsigned int *puIds, unsigned int uMaxIds, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    if (uMaxIds < APPS_INFOS_COUNT) { // this is a predetermined limit in the original dll
        set_steam_err(pError, "AppID buffer too small");
        return SOLD_ERR_FAIL;
    }

    // real dll doesn't check for null/size
    if (puIds && uMaxIds > 0) {
        const auto min_size = uMaxIds < APPS_INFOS_COUNT ? uMaxIds : APPS_INFOS_COUNT;
        for (unsigned idx = 0; idx < min_size; ++idx) {
            puIds[idx] = apps_infos[idx].uAppId;
        }
        PRINT_DEBUG("copied %u items", min_size);
    } else {
        PRINT_DEBUG("[?] nothing was copied, null buffer or size=0");
    }

    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamGetAppPurchaseCountry( unsigned int uAppId, char* szCountryBuf, unsigned int uBufSize, unsigned int* pPurchaseTime, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAppStats( TSteamAppStats *pAppStats, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    // real dll doesn't check for null
    if (pAppStats) {
        // these are actual hardcoded values from the real dll
        pAppStats->uNumApps = APPS_INFOS_COUNT;
        pAppStats->uMaxNameChars = STEAM_MAX_PATH;
        pAppStats->uMaxInstallDirNameChars = STEAM_MAX_PATH;
        pAppStats->uMaxVersionLabelChars = STEAM_MAX_PATH;
        pAppStats->uMaxLaunchOptions = 1;
        pAppStats->uMaxLaunchOptionDescChars = STEAM_MAX_PATH;
        pAppStats->uMaxLaunchOptionCmdLineChars = STEAM_MAX_PATH;
        pAppStats->uMaxNumIcons = 0;
        pAppStats->uMaxIconSize = 0;
        pAppStats->uMaxDependencies = 0;
    }

    return SOLD_ERR_OK;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamGetAppUpdateStats( unsigned int uAppOrCacheId, ESteamAppUpdateStatsQueryType eQueryType, TSteamUpdateStats *pUpdateStats, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return STEAM_INVALID_CALL_HANDLE;
}

STEAM_API int STEAM_CALL SteamGetAppUserDefinedInfo( unsigned int uAppId, const char *cszKey, char *szValueBuf, unsigned int uValueBufLen, unsigned int *puValueLen, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetAppUserDefinedRecord(unsigned int uAppId, KeyValueIteratorCallback_t AddEntryToKeyValueFunc, void* pvCKeyValue, TSteamError *pError)
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetCacheDecryptionKey( unsigned int uCacheId, char* pchKeyBuffer, unsigned int cubBuff, unsigned int* pcubKey, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetCacheDefaultDirectory( char *szPath, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetCacheFilePath( unsigned int uCacheId, char *szPathBuf, unsigned int uBufSize, unsigned int *puPathChars, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamGetCachePercentFragmentation( unsigned int uAppId, unsigned int* puPctFragmentation, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetContentServerInfo( unsigned int uAppId, unsigned int *puServerId, unsigned int *puServerIpAddress, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetCurrentAppId(unsigned int *puAppId, TSteamError *pError)
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    // real dll doesn't check for null
    if (puAppId) *puAppId = 0;
    
    if (!sold_steam_utils) {
        return SOLD_ERR_FAIL;
    }

    uint32 appid = sold_steam_utils->GetAppID();
    // real dll doesn't check for null
    if (puAppId) *puAppId = appid;
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamGetCurrentCellID(int *param_1, int *param_2, TSteamError *pError)
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    // real dll doesn't check for null
    if (param_1) *param_1 = 1;
    if (param_2) *param_2 = 100;
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamGetCurrentEmailAddress( char *szEmailAddress, unsigned int uBufSize, unsigned int *puEmailChars, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetDepotParent( unsigned int uDepotId, unsigned int* puParentId, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}


STEAM_API ESteamError STEAM_CALL SteamGetEncryptedUserIDTicket( const void *pEncryptionKeyReceivedFromAppServer, unsigned int uEncryptionKeyLength, void *pOutputBuffer, unsigned int uSizeOfOutputBuffer, unsigned int *pReceiveSizeOfEncryptedTicket, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return ESteamError::eSteamErrorBadArg;
}

STEAM_API const char* STEAM_CALL SteamGetEncryptionKeyToSendToNewClient( unsigned int * pReceiveSizeOfEncryptionKey )
{
    // that's the whole function in the real dll!
    PRINT_DEBUG_ENTRY();
    // real dll doesn't check for null
    if (pReceiveSizeOfEncryptionKey) *pReceiveSizeOfEncryptionKey = 27;
    return "Steam2WrapperEncryptionKey";
}

STEAM_API int STEAM_CALL SteamGetFileAttributeFlags( const char* cszName, int* puFlags, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetLocalClientVersion( unsigned int* puBootstrapperVersion, unsigned int* puClientVersion, TSteamError *pError )
{
    // that's the whole function in the real dll!
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    // real dll doesn't check for null
    if (puBootstrapperVersion) *puBootstrapperVersion = 1;
    if (puClientVersion) *puClientVersion = 1;
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamGetLocalFileCopy( const char *cszName, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamGetNumAccountsWithEmailAddress( const char *cszEmailAddress, unsigned int *puNumAccounts, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetOfflineStatus( TSteamOfflineStatus *pStatus, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    // real dll doesn't check for null
    if (pStatus) {
        pStatus->eOfflineNow = 0;
        pStatus->eOfflineNextSession = 0;
    }
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL  SteamGetSponsorUrl( unsigned int uAppId, char *szUrl, unsigned int uBufSize, unsigned int *pUrlChars, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetSubscriptionExtendedInfo( unsigned int uSubscriptionId, const char* cszKeyName, char* szKeyValue, unsigned int uBufferLength, unsigned int* puRecievedLength, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetSubscriptionIds( unsigned int *puIds, unsigned int uMaxIds, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetSubscriptionPurchaseCountry( unsigned int uSubscriptionId, char* szCountryBuf, unsigned int uBufSize , int* pPurchaseTime, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetSubscriptionReceipt( unsigned int uSubscriptionId, TSteamSubscriptionReceipt *pSubscriptionReceipt, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetSubscriptionStats( TSteamSubscriptionStats *pSubscriptionStats, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetTotalUpdateStats( TSteamUpdateStats *pUpdateStats, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetUser( char *szUser, unsigned int uBufSize, unsigned int *puUserChars, TSteamGlobalUserID *pOptionalReceiveUserID, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    if (puUserChars) *puUserChars = 0;
    if (!sold_steam_user) {
        PRINT_DEBUG("[X] SteamUser is null!");
        return SOLD_ERR_FAIL;
    }
    if (!szUser) {
        uBufSize = 0;
    }
    const char *user_val = getenv("SteamUser");

    // === emu specific START
    if (!user_val || !user_val[0]) {
        user_val = getenv("SteamAppUser");
    }

    if (!user_val || !user_val[0]) {
        auto friends_itf = sold_steam_client
            ? reinterpret_cast<ISteamFriends017 *>(sold_steam_client->GetISteamGenericInterface(sold_hsteam_user, sold_hsteam_pipe, SOLD_ITF_NAME_FRIENDS))
            : static_cast<ISteamFriends017 *>(nullptr);
        if (friends_itf) {
            user_val = friends_itf->GetPersonaName();
        }
    }

    if (!user_val || !user_val[0]) {
        user_val = DEFAULT_NAME;
    }
    // === emu specific END

    {
        unsigned copy_count = 0;
        if (uBufSize > 0) {
            auto user_val_view = std::string_view(user_val);
            copy_count = (unsigned)user_val_view.copy(szUser, uBufSize - 1);
            szUser[copy_count] = 0;
        }
        if (puUserChars) *puUserChars = copy_count;
    }
    
    if (pOptionalReceiveUserID) {
        sold_steam_user->GetSteamID().ConvertToSteam2(pOptionalReceiveUserID);
    }
    
    PRINT_DEBUG("copied buffer '%s'", szUser);
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamGetUserType( unsigned int *puUserTypeFlags, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamGetVersion( char *szVersion, unsigned int uVersionBufSize )
{
    PRINT_DEBUG_ENTRY();
    if (szVersion && uVersionBufSize > 0) {
        std::strncpy(szVersion, "1.0.0.0", uVersionBufSize - 1);
        return SOLD_ERR_OK;
    }

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamGetc( SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamHintResourceNeed( const char *cszMasterList, int bForgetEverything, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API ESteamError STEAM_CALL SteamInitializeUserIDTicketValidator( const char * pszOptionalPublicEncryptionKeyFilename, const char * pszOptionalPrivateDecryptionKeyFilename, unsigned int ClientClockSkewToleranceInSeconds, unsigned int ServerClockSkewToleranceInSeconds, unsigned int MaxNumLoginsWithinClientClockSkewTolerancePerClient, unsigned int HintPeakSimultaneousValidations, unsigned int AbortValidationAfterStallingForNProcessSteps )
{
    // that's the whole function in the real dll!
    PRINT_DEBUG_ENTRY();
    return ESteamError::eSteamErrorNone;
}

STEAM_API int STEAM_CALL SteamInsertAppDependency( unsigned int uAppId, unsigned int uIndex, TSteamAppDependencyInfo *pDependencyInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamIsAccountNameInUse( const char *cszAccountName, int *pbIsUsed, TSteamError *pError)
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamIsAppSubscribed( unsigned int uAppId, int *pbIsAppSubscribed, int *pbIsSubscriptionPending, TSteamError *pError )
{
    PRINT_DEBUG("%u", uAppId);
    set_ok_err(pError); // never changed afterwards

    // original dll doesn't check for null
    if (pbIsAppSubscribed) *pbIsAppSubscribed = 0;
    if (!sold_steam_apps) {
        PRINT_DEBUG("[X] SteamApps is null!");
        return SOLD_ERR_FAIL;
    }
    if (pbIsSubscriptionPending) *pbIsSubscriptionPending = 0; // never changed afterwards
    bool subed = sold_steam_apps->BIsSubscribedApp(uAppId);
    // real dll doesn't check for null
    if (pbIsAppSubscribed) *pbIsAppSubscribed = subed;

    PRINT_DEBUG("is subbed = %i", (int)subed);
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamIsCacheLoadingEnabled( unsigned int uAppId, int *pbIsLoading, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamStat( const char *cszName, TSteamElemInfo *pInfo, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);
    if (pError) pError->eSteamError = ESteamError::eSteamErrorNotFound;

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamIsFileImmediatelyAvailable( const char *cszName, TSteamError *pError )
{
    PRINT_DEBUG("'%s'", cszName);
    set_ok_err(pError);

    TSteamElemInfo elem_info{};
    int err_code = SteamStat(cszName, &elem_info, pError);
    PRINT_DEBUG("ret=%i", err_code);
    return err_code != -1 ? SOLD_ERR_OK : SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamIsFileNeededByApp( unsigned int uAppId, const char* pchFileName, SteamUnsigned64_t u64FileSize, unsigned int* puCacheId, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamIsFileNeededByCache( unsigned int uCacheId, const char* pchFileName, SteamUnsigned64_t u64FileSize, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamIsLoggedIn( int *pbIsLoggedIn, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    // real dll doesn't check for null
    if (pbIsLoggedIn) *pbIsLoggedIn = 1;
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamIsSecureComputer(  int *pbIsSecure, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamIsSubscribed( unsigned int uSubscriptionId, int *pbIsSubscribed, int *pbIsSubscriptionPending, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamIsUsingSdkContentServer( int *pbUsingSdkCS, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamLaunchApp( unsigned int uAppId, unsigned int uLaunchOption, const char *cszArgs, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    // real function:
    // ----------------
    // HINSTANCE ret = ShellExecuteW(NULL, NULL, <PATH_TO_STEAM_EXE>, "-applaunch <APPID> <cszArgs>", NULL, 1);
    // return ret > 32;
    // ----------------

    // https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-
    return 2; // ERROR_FILE_NOT_FOUND
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamLoadCacheFromDir( unsigned int uAppId, const char *szPath, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamLoadFileToApp( unsigned int uAppId, const char* pchFileName, const void* pubDataChunk, unsigned int cubDataChunk, SteamUnsigned64_t cubDataOffset, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamLoadFileToCache( unsigned int uCacheId, const char* pchFileName, const void* pubDataChunk, unsigned int cubDataChunk, SteamUnsigned64_t cubDataOffset, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamLog( SteamHandle_t hContext, const char *cszMsg )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return SOLD_ERR_FAIL;
}

STEAM_API void STEAM_CALL SteamLogResourceLoadFinished( const char *cszMsg )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
}

STEAM_API void STEAM_CALL SteamLogResourceLoadStarted( const char *cszMsg )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamLogin( const char *cszUser, const char *cszPassphrase, int bIsSecureComputer, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamLogout( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}


STEAM_API void STEAM_CALL SteamMiniDumpInit()
{
    PRINT_DEBUG_TODO();
}

// TODO
STEAM_API int STEAM_CALL SteamMountAppFilesystem( TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API SteamHandle_t STEAM_CALL SteamMountFilesystem( unsigned int uAppId, const char *szMountPath, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_OK;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamMoveApp( unsigned int uAppId, const char *szPath, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API unsigned int STEAM_CALL SteamNumAppsRunning( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamHandle_t STEAM_CALL SteamOpenFileEx( const char *cszName, const char *cszMode, unsigned int *puFileSize, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return STEAM_INVALID_CALL_HANDLE;
}

STEAM_API SteamHandle_t STEAM_CALL SteamOpenFile( const char *cszName, const char *cszMode, TSteamError *pError )
{
    PRINT_DEBUG("'%s' '%s'", cszName, cszMode);

    unsigned int uFileSize = 0;
    return SteamOpenFileEx(cszName, cszMode, &uFileSize, pError);
}

STEAM_API SteamHandle_t STEAM_CALL SteamOpenFile64( const char *cszPath, const char *cszMode, SteamUnsigned64_t *pu64FileSize, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamHandle_t STEAM_CALL SteamOpenTmpFile( TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return STEAM_INVALID_CALL_HANDLE;
}

STEAM_API ESteamError STEAM_CALL SteamOptionalCleanUpAfterClientHasDisconnected( unsigned int ObservedClientIPAddr, unsigned int ClientLocalIPAddr )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return ESteamError::eSteamErrorNone;
}

STEAM_API int STEAM_CALL SteamPauseCachePreloading( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamPrintFile( SteamHandle_t hFile, TSteamError *pError, const char *cszFormat, ... )
{
    PRINT_DEBUG_TODO();

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamProcessCall( SteamCallHandle_t handle, TSteamProgress *pProgress, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    if (pProgress) {
        pProgress->bValid = 1;
        pProgress->uPercentDone = 100;
        pProgress->szProgress[0] = 0;
    }
    return SOLD_ERR_OK;
}

STEAM_API ESteamError STEAM_CALL SteamProcessOngoingUserIDTicketValidation( SteamUserIDTicketValidationHandle_t Handle, TSteamGlobalUserID *pReceiveValidSteamGlobalUserID, unsigned int *pReceiveClientLocalIPAddr, unsigned char *pOptionalReceiveProofOfAuthenticationToken, size_t SizeOfOptionalAreaToReceiveProofOfAuthenticationToken, size_t *pOptionalReceiveSizeOfProofOfAuthenticationToken )
{
    PRINT_DEBUG_TODO();

    return ESteamError::eSteamErrorNothingToDo;
}

STEAM_API int STEAM_CALL SteamPutc( int cChar, SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API unsigned int STEAM_CALL SteamReadFile( void *pBuf, unsigned int uSize, unsigned int uCount, SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return 0;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRefreshAccountInfo( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRefreshAccountInfo2( int bRefreshAccount, int bRefreshCDDB, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRefreshAccountInfoEx( int bContentDescriptionOnly, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRefreshLogin( const char *cszPassphrase, int bIsSecureComputer, TSteamError * pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamReleaseCacheFiles( unsigned int uAppId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamRemoveAppDependency( unsigned int uAppId, unsigned int uIndex, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRepairOrDecryptCaches( unsigned int uAppId, int bForceValidation, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRequestAccountsByCdKeyEmail( const char *cszCdKey, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRequestAccountsByEmailAddressEmail( const char *cszEmailAddress, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRequestEmailAddressVerificationEmail( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamRequestForgottenPasswordEmail( const char *cszUser, SteamPersonalQuestion_t ReceivePersonalQuestion, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamResumeCachePreloading( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamSeekFile( SteamHandle_t hFile, long lOffset, ESteamSeekMethod, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);
    if (pError) pError->eSteamError = ESteamError::eSteamErrorEOF;

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamSeekFile64( SteamHandle_t hFile, SteamSigned64_t s64Offset, ESteamSeekMethod eMethod, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamSetAppCacheSize( unsigned int uCacheId, unsigned int nCacheSizeInMb, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamSetAppVersion( unsigned int uAppId, unsigned int uAppVersionId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamSetCacheDefaultDirectory( const char *szPath, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamSetMaxStallCount( unsigned int uNumStalls, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamSetNotificationCallback( SteamNotificationCallback_t pCallbackFunction, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamSetUser( const char *cszUser, int *pbUserSet, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamSetUser2( const char *cszUser, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamSetvBuf( SteamHandle_t hFile, void* pBuf, ESteamBufferMethod eMethod, unsigned int uBytes, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamShutdownEngine(TSteamError *pError)
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamShutdownSteamBridgeInterface( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API ESteamError STEAM_CALL SteamShutdownUserIDTicketValidator()
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return ESteamError::eSteamErrorNone;
}

STEAM_API long STEAM_CALL SteamSizeFile( SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return 0;
}

STEAM_API SteamSigned64_t STEAM_CALL SteamSizeFile64( SteamHandle_t hFile, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamStartEngine(TSteamError *pError)
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamStartEngineEx( TSteamError *pError, bool bStartOffline, bool bDetectOnlineOfflineState )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamStartLoadingCache( unsigned int uAppId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API ESteamError STEAM_CALL SteamStartValidatingNewValveCDKey( void *pEncryptedNewValveCDKeyFromClient, unsigned int uSizeOfEncryptedNewValveCDKeyFromClient, unsigned int ObservedClientIPAddr, struct sockaddr *pPrimaryValidateNewCDKeyServerSockAddr, struct sockaddr *pSecondaryValidateNewCDKeyServerSockAddr, SteamUserIDTicketValidationHandle_t *pReceiveHandle )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return ESteamError::eSteamErrorNone;
}

STEAM_API ESteamError STEAM_CALL SteamStartValidatingUserIDTicket( void *pEncryptedUserIDTicketFromClient, unsigned int uSizeOfEncryptedUserIDTicketFromClient, unsigned int ObservedClientIPAddr, SteamUserIDTicketValidationHandle_t *pReceiveHandle )
{
    PRINT_DEBUG_TODO();

    return ESteamError::eSteamErrorBadArg;
}

STEAM_API int STEAM_CALL SteamStartup( unsigned int uUsingMask, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    if (startup_ok) {
        PRINT_DEBUG("startup was already called");
        return SOLD_ERR_OK;
    }

    if (!steamclient_loader) {
        PRINT_DEBUG("[X] steamclient.dll loader is null!");
        set_steam_err(pError, "SteamAPI_Init_Internal failed", ESteamError::eSteamErrorUnknown);
        return SOLD_ERR_FAIL;
    }

    sold_steam_client = reinterpret_cast<decltype(sold_steam_client)>(create_interface_internal(SOLD_ITF_NAME_CLIENT, nullptr));
    if (!sold_steam_client) {
        PRINT_DEBUG("[X] failed to get SteamClient interface");
        set_steam_err(pError, "SteamAPI_Init_Internal failed", ESteamError::eSteamErrorUnknown);
        return SOLD_ERR_FAIL;
    }

    sold_hsteam_pipe = sold_steam_client->CreateSteamPipe();
    sold_hsteam_user = sold_steam_client->ConnectToGlobalUser(sold_hsteam_pipe);
    sold_steam_utils = reinterpret_cast<decltype(sold_steam_utils)>(sold_steam_client->GetISteamGenericInterface(sold_hsteam_user, sold_hsteam_pipe, SOLD_ITF_NAME_UTILS));
    sold_steam_user = reinterpret_cast<decltype(sold_steam_user)>(sold_steam_client->GetISteamGenericInterface(sold_hsteam_user, sold_hsteam_pipe, SOLD_ITF_NAME_USER));
    sold_steam_apps = reinterpret_cast<decltype(sold_steam_apps)>(sold_steam_client->GetISteamGenericInterface(sold_hsteam_user, sold_hsteam_pipe, SOLD_ITF_NAME_APPS));
    if (!sold_steam_utils || !sold_steam_user || !sold_steam_apps || 0 == sold_hsteam_user) {
        PRINT_DEBUG("[X] one of the required interfaces is missing or bad HSteamUser");
        set_steam_err(pError, "Missing interface", ESteamError::eSteamErrorUnknown);
        return SOLD_ERR_FAIL;
    }

    sold_game_appid = sold_steam_utils->GetAppID();
    if (0 == sold_game_appid) {
        PRINT_DEBUG("[X] invalid appid");
        set_steam_err(pError, "Invalid appid", ESteamError::eSteamErrorUnknown);
        return SOLD_ERR_FAIL;
    }

    sold_steam_apps->GetAppInstallDir(sold_game_appid, game_installpath, (uint32)sizeof(game_installpath));
    sold_steam_apps->GetInstalledDepots(sold_game_appid, installed_depots, (uint32)(sizeof(installed_depots) / sizeof(installed_depots[0])));

    PRINT_DEBUG("done");
    startup_ok = true;
    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamStat64( const char *cszName, TSteamElemInfo64 *pInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamStopLoadingCache( unsigned int uAppId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamSubscribe( unsigned int uSubscriptionId, const TSteamSubscriptionBillingInfo *pSubscriptionBillingInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API long STEAM_CALL SteamTellFile( SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return 0;
}

STEAM_API SteamSigned64_t STEAM_CALL SteamTellFile64( SteamHandle_t hFile, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamUninstall( TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamUnmountAppFilesystem( TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API int STEAM_CALL SteamUnmountFilesystem( SteamHandle_t hFs, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    return SOLD_ERR_OK;
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamUnsubscribe( unsigned int uSubscriptionId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamUpdateAccountBillingInfo( const TSteamPaymentCardInfo *pPaymentCardInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamUpdateSubscriptionBillingInfo( unsigned int uSubscriptionId, const TSteamSubscriptionBillingInfo *pSubscriptionBillingInfo, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamVerifyEmailAddress( const char *cszEmailVerificationKey, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API int STEAM_CALL SteamVerifyPassword( const char *cszPassphrase, int *pbCorrect, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamWaitForAppReadyToLaunch( unsigned int uAppId, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamWaitForAppResources( unsigned int uAppId, const char* cszMasterList, TSteamError* pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API SteamCallHandle_t STEAM_CALL SteamWaitForResources( const char *cszMasterList, TSteamError *pError )
{
    PRINT_DEBUG_ENTRY();
    set_ok_err(pError);

    return SOLD_ERR_OK;
}

STEAM_API int STEAM_CALL SteamWasBlobRegistryDeleted( int *puWasDeleted, TSteamError *pError )
{
    // that's the whole function in the original dll!
    PRINT_DEBUG_ENTRY();
    return set_wrapper_not_impl_err(pError);
}

STEAM_API unsigned int STEAM_CALL SteamWriteFile( const void *pBuf, unsigned int uSize, unsigned int uCount, SteamHandle_t hFile, TSteamError *pError )
{
    PRINT_DEBUG_TODO();
    set_ok_err(pError);

    return SOLD_ERR_FAIL;
}

STEAM_API void STEAM_CALL SteamWriteMiniDumpFromAssert(unsigned int unknown1, unsigned int unknown2, unsigned int unknown3, const char *szMessage, const char *szFileName)
{
    // that's the whole function in the original dll!
    PRINT_DEBUG("Wrapper not implemented:SteamWriteMiniDumpFromAssert");
}

STEAM_API void STEAM_CALL SteamWriteMiniDumpSetComment( const char* cszComment )
{
    PRINT_DEBUG_TODO();
    PRINT_DEBUG(  "%s", cszComment);
}

STEAM_API void STEAM_CALL SteamWriteMiniDumpUsingExceptionInfo(	unsigned int uStructuredExceptionCode, /*struct _EXCEPTION_POINTERS*/ void* pExceptionInfo)
{
    PRINT_DEBUG_TODO();
    PRINT_DEBUG("  app is writing a crash dump! [XXXXXXXXXXXXXXXXXXXXXXXXXXX]");
}

STEAM_API void STEAM_CALL SteamWriteMiniDumpUsingExceptionInfoWithBuildId(unsigned int uStructuredExceptionCode, /*struct _EXCEPTION_POINTERS*/ void* pExceptionInfo, unsigned int uBuildID)
{
    PRINT_DEBUG_TODO();
    PRINT_DEBUG("  app is writing a crash dump! [XXXXXXXXXXXXXXXXXXXXXXXXXXX]");
}

STEAM_API void STEAM_CALL SteamWriteMiniDumpWithAppID()
{
    // that's the whole function in the original dll!
    PRINT_DEBUG("Wrapper not implemented:SteamWriteMiniDumpWithAppID");
}

STEAM_API void* STEAM_CALL _f(const char *szInterfaceVersionRequested)
{
    PRINT_DEBUG_TODO();
    return create_interface_internal(szInterfaceVersionRequested, nullptr);
}

// declare "g_dwDllEntryThreadId" as an export, then actually define it
STEAM_API unsigned long g_dwDllEntryThreadId;
unsigned long g_dwDllEntryThreadId = 0;



void sold::set_steamclient_loader(steamclient_loader_t *loader)
{
    steamclient_loader = loader;
}

void sold::set_tid(unsigned long tid)
{
    g_dwDllEntryThreadId = tid;
}
