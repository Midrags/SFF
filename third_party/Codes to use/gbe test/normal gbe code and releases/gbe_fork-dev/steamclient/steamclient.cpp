
#define WIN32_LEAN_AND_MEAN
#include "Windows.h"

#ifdef _WIN64
    #define DLL_NAME "steam_api64.dll"
#else
    #define DLL_NAME "steam_api.dll"
#endif

extern "C" __declspec( dllexport )  void* __cdecl CreateInterface( const char *pName, int *pReturnCode )
{
    using fn_create_interface_t = void* (__cdecl *)(const char *);

    auto steam_api = LoadLibraryA(DLL_NAME);
    if (!steam_api) {
        if (pReturnCode) *pReturnCode = 1; // IFACE_FAILED
        return nullptr;
    }

    auto create_interface = (fn_create_interface_t)GetProcAddress(steam_api, "SteamInternal_CreateInterface");
    // https://github.com/ValveSoftware/source-sdk-2013/blob/57a8b644af418c691f1fba45791019cf2367dedd/src/public/tier1/interface.h#L156-L160
    if (!create_interface) {
        if (pReturnCode) *pReturnCode = 1; // IFACE_FAILED
        return nullptr;
    }

    auto ptr = create_interface(pName);
    if (pReturnCode) {
        if (ptr) {
            *pReturnCode = 0; // IFACE_OK
        } else {
            *pReturnCode = 1; // IFACE_FAILED
        }
    }

    return ptr;
}
