# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.


import base64 as _b64

VERSION = "6.2.1"
# NOTE: Public key shared by oureveryday (https://github.com/SteamAutoCracks/Steam-auto-crack/issues/33)
_swak = b"MUREMDQ1MEE5OUY1NzM2OTNDRDAzMUVCQjE2MDkwN0Q="
STEAM_WEB_API_KEY = _b64.b64decode(_swak).decode()
GITHUB_USERNAME = "Midrags"
REPO_NAME = "sff"
# Update check source: https://github.com/Midrags/SFF/releases/
GITHUB_UPDATE_USERNAME = "Midrags"
REPO_UPDATE_NAME = "SteaMidra"
RELEASE_PAGE_URL = "https://github.com/Midrags/SFF/releases/"
WINDOWS_RELEASE_PREFIX = "0_windows_x86-64"
LINUX_RELEASE_PREFIX = "1_linux_x86-64"
