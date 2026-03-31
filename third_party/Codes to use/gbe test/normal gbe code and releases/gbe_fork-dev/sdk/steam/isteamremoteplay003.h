
#ifndef ISTEAMREMOTEPLAY003_H
#define ISTEAMREMOTEPLAY003_H
#ifdef STEAM_WIN32
#pragma once
#endif

//-----------------------------------------------------------------------------
// Purpose: Functions to provide information about Steam Remote Play sessions
//-----------------------------------------------------------------------------
class ISteamRemotePlay003
{
public:
	// Get the number of currently connected Steam Remote Play sessions
	virtual uint32 GetSessionCount() = 0;
	
	// Get the currently connected Steam Remote Play session ID at the specified index. Returns zero if index is out of bounds.
	virtual RemotePlaySessionID_t GetSessionID( int iSessionIndex ) = 0;

	// Get the SteamID of the connected user
	virtual CSteamID GetSessionSteamID( RemotePlaySessionID_t unSessionID ) = 0;

	// Get the name of the session client device
	// This returns NULL if the sessionID is not valid
	virtual const char *GetSessionClientName( RemotePlaySessionID_t unSessionID ) = 0;

	// Get the form factor of the session client device
	virtual ESteamDeviceFormFactor GetSessionClientFormFactor( RemotePlaySessionID_t unSessionID ) = 0;

	// Get the resolution, in pixels, of the session client device
	// This is set to 0x0 if the resolution is not available
	virtual bool BGetSessionClientResolution( RemotePlaySessionID_t unSessionID, int *pnResolutionX, int *pnResolutionY ) = 0;

	// Show the Remote Play Together UI in the game overlay
	// This returns false if your game is not configured for Remote Play Together
	virtual bool ShowRemotePlayTogetherUI() = 0;

	// Invite a friend to Remote Play Together, or create a guest invite if steamIDFriend is CSteamID()
	// This returns false if the invite can't be sent or your game is not configured for Remote Play Together
	virtual bool BSendRemotePlayTogetherInvite( CSteamID steamIDFriend ) = 0;

	// Make mouse and keyboard input for Remote Play Together sessions available via GetInput() instead of being merged with local input
	virtual bool BEnableRemotePlayTogetherDirectInput() = 0;

	// Merge Remote Play Together mouse and keyboard input with local input
	virtual void DisableRemotePlayTogetherDirectInput() = 0;

	// Get input events from Remote Play Together sessions
	// This is available after calling BEnableRemotePlayTogetherDirectInput()
	//
	// pInput is an array of input events that will be filled in by this function, up to unMaxEvents.
	// This returns the number of events copied to pInput, or the number of events available if pInput is nullptr.
	virtual uint32 GetInput( RemotePlayInput_t *pInput, uint32 unMaxEvents ) = 0;

	// Set the mouse cursor visibility for a remote player
	// This is available after calling BEnableRemotePlayTogetherDirectInput()
	virtual void SetMouseVisibility( RemotePlaySessionID_t unSessionID, bool bVisible ) = 0;

	// Set the mouse cursor position for a remote player
	// This is available after calling BEnableRemotePlayTogetherDirectInput()
	//
	// This is used to warp the cursor to a specific location and isn't needed during normal event processing.
	//
	// The position is normalized relative to the window, where 0,0 is the upper left, and 1,1 is the lower right.
	virtual void SetMousePosition( RemotePlaySessionID_t unSessionID, float flNormalizedX, float flNormalizedY ) = 0;

	// Create a cursor that can be used with SetMouseCursor()
	// This is available after calling BEnableRemotePlayTogetherDirectInput()
	//
	// Parameters:
	// nWidth - The width of the cursor, in pixels
	// nHeight - The height of the cursor, in pixels
	// nHotX - The X coordinate of the cursor hot spot in pixels, offset from the left of the cursor
	// nHotY - The Y coordinate of the cursor hot spot in pixels, offset from the top of the cursor
	// pBGRA - A pointer to the cursor pixels, with the color channels in red, green, blue, alpha order
	// nPitch - The distance between pixel rows in bytes, defaults to nWidth * 4 
	virtual RemotePlayCursorID_t CreateMouseCursor( int nWidth, int nHeight, int nHotX, int nHotY, const void *pBGRA, int nPitch = 0 ) = 0;

	// Set the mouse cursor for a remote player
	// This is available after calling BEnableRemotePlayTogetherDirectInput()
	//
	// The cursor ID is a value returned by CreateMouseCursor()
	virtual void SetMouseCursor( RemotePlaySessionID_t unSessionID, RemotePlayCursorID_t unCursorID ) = 0;
};

#endif // #define ISTEAMREMOTEPLAY003_H
