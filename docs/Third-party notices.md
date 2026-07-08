# Third-party notices

This document lists third-party tools, binaries, assets, APIs, services, and projects used by, bundled with, integrated with, downloaded by, or referenced by SteaMidra.

SteaMidra’s GPL license applies to SteaMidra’s own source code only. It does not relicense third-party tools, binaries, unlockers, emulators, assets, APIs, services, or external projects.

Unless stated otherwise, bundled third-party tools are included unmodified and remain owned by their original authors.

If any credit, license, author, source, or ownership note is missing or unclear, open an issue with the exact file/component so it can be reviewed.

---

## Bundled third-party tools

### DDMod / DepotDownloaderMod

Author / maintainer: oureveryday
Path: `third_party/DDMod`
License file: `third_party_licenses/DDMod.LICENSE`
Bundled: Yes
Modified: No
Used for: Downloading Steam depots / manifests where DepotDownloaderMod is needed.
Notes: DDMod remains owned by its original author/maintainer and is not licensed as SteaMidra code.

### SteamAutoCrack CLI

Author / maintainer: oureveryday
Path: `third_party/SteamAutoCrack/cli`
License file: `third_party_licenses/steamautocrack.LICENSE`
Bundled: Yes
Modified: No
Used for: SteamAutoCrack feature / emulator setup automation.
Notes: SteamAutoCrack remains owned by its original author/maintainer and is not licensed as SteaMidra code.

### fzf

Author / maintainer: fzf project maintainers
Path: `third_party/fzf`
License file: `third_party_licenses/fzf.LICENSE`
Bundled: Yes
Modified: No
Used for: Fuzzy search / CLI selection support.
Notes: fzf remains owned by its original authors and is not licensed as SteaMidra code.

### gbe_fork

Author / maintainer: Detanup01 / gbe_fork contributors
Path: `third_party/gbe_fork`
License file: `third_party_licenses/gbe_fork.LICENSE`
Bundled: Yes
Modified: No
Used for: Steam emulator / offline game setup features.
Notes: gbe_fork remains owned by its original authors and is not licensed as SteaMidra code.

### gbe_fork Linux

Author / maintainer: Detanup01 / gbe_fork contributors
Path: `third_party/gbe_fork_linux`
License file: `third_party_licenses/gbe_fork.LICENSE`
Bundled: Yes
Modified: No
Used for: Linux-compatible gbe_fork/emulator support.
Notes: gbe_fork Linux components remain owned by their original authors and are not licensed as SteaMidra code.

### gbe_fork tools / generate_emu_config

Authors / maintainers: Detanup01, NickAntaris, Oureveryday, and related contributors
Path: `third_party/gbe_fork_tools/generate_emu_config`
License file: `third_party_licenses/gbe_fork_tools.LICENSE`
Bundled: Yes
Modified: No
Used for: Generating Goldberg/gbe_fork emulator configuration, achievements, DLC data, stats, and related metadata.
Notes: These tools remain owned by their original authors and are not licensed as SteaMidra code.

### gbe_fork tools Linux

Authors / maintainers: Detanup01, NickAntaris, Oureveryday, and related contributors
Path: `third_party/gbe_fork_tools_linux`
License file: `third_party_licenses/gbe_fork_tools.LICENSE`
Bundled: Yes
Modified: No
Used for: Linux-compatible emulator config generation.
Notes: These tools remain owned by their original authors and are not licensed as SteaMidra code.

### Steamless

Author / maintainer: atom0s
Path: `third_party/steamless`
License file: `third_party_licenses/steamless.LICENSE`
Bundled: Yes
Modified: No
Used for: Removing SteamStub DRM from executables where the user chooses that option.
Notes: Steamless remains owned by its original author and is not licensed as SteaMidra code.

### rclone

Author / maintainer: rclone project maintainers
Path: `third_party/rclone`
License file: `third_party_licenses/rclone.LICENSE`
Bundled: Yes
Modified: No
Used for: Cloud save backup/restore to remote storage providers.
Notes: rclone remains owned by its original authors and is not licensed as SteaMidra code.

### rclone Linux

Author / maintainer: rclone project maintainers
Path: `third_party/rclone_linux`
License file: `third_party_licenses/rclone.LICENSE`
Bundled: Yes
Modified: No
Used for: Linux cloud save backup/restore support.
Notes: rclone remains owned by its original authors and is not licensed as SteaMidra code.

### aria2

Author / maintainer: aria2 project maintainers
Path: Used by bundled/download features where applicable
License file: `third_party_licenses/aria2.LICENSE`
Bundled: Yes, where included in SteaMidra builds
Modified: No
Used for: Downloading files where aria2 support is used.
Notes: aria2 remains owned by its original authors and is not licensed as SteaMidra code.

### coldloader

Author / maintainer: Original ColdLoader / related emulator project authors
Path: `third_party/coldloader`
Bundled: Yes
Modified: No
Used for: ColdLoader / emulator-related game setup features.
Notes: coldloader remains owned by its original authors and is not licensed as SteaMidra code. If a more specific upstream author/source should be credited here, open an issue with the exact source and it will be corrected.

### HyperVisor / hv tools

Author / maintainer: Original HyperVisor bypass/tool authors
Path: `third_party/hv`
Bundled: Yes
Modified: No
Used for: HyperVisor bypass setup where the user chooses that feature.
Notes: HyperVisor-related third-party files remain owned by their original authors and are not licensed as SteaMidra code. If a more specific upstream author/source should be credited here, open an issue with the exact source and it will be corrected.

### Linux tools bundle

Author / maintainer: Original Linux tool authors / maintainers
Path: `third_party/linux`
Bundled: Yes
Modified: No
Used for: Linux support, including SLSsteam/SLScheevo-related setup where applicable.
Notes: Linux third-party tools remain owned by their original authors and are not licensed as SteaMidra code. If a more specific upstream author/source should be credited here, open an issue with the exact source and it will be corrected.

---

## DLC unlocker components

### CreamAPI

Author: deadmau5
Path: DLC Unlockers feature / bundled unlocker resources where applicable
Bundled: Yes
Modified: No
Used for: DLC unlocker support for Steam games.
Notes: CreamAPI remains owned by deadmau5 and is not licensed as SteaMidra code. SteaMidra does not claim authorship or ownership of CreamAPI.

### SmokeAPI

Author: Acidicoala
Path: DLC Unlockers feature / bundled unlocker resources where applicable
Bundled: Yes
Modified: No
Used for: DLC ownership emulation/unlocker support for Steam games.
Notes: SmokeAPI remains owned by Acidicoala and is not licensed as SteaMidra code. SteaMidra does not claim authorship or ownership of SmokeAPI.

### ScreamAPI

Author: Acidicoala
Path: DLC Unlockers feature / bundled unlocker resources where applicable
Bundled: Yes
Modified: No
Used for: DLC unlocker/emulation support where applicable.
Notes: ScreamAPI remains owned by Acidicoala and is not licensed as SteaMidra code. SteaMidra does not claim authorship or ownership of ScreamAPI.

### Uplay R1 Unlocker

Author: Acidicoala
Path: DLC Unlockers feature / bundled unlocker resources where applicable
Bundled: Yes
Modified: No
Used for: Ubisoft/Uplay DLC unlocker support for older Ubisoft Connect/Uplay titles where applicable.
Notes: Uplay R1 Unlocker remains owned by Acidicoala and is not licensed as SteaMidra code.

### Uplay R2 Unlocker

Author: Acidicoala
Path: DLC Unlockers feature / bundled unlocker resources where applicable
Bundled: Yes
Modified: No
Used for: Ubisoft/Uplay DLC unlocker support for newer Ubisoft Connect/Uplay titles where applicable.
Notes: Uplay R2 Unlocker remains owned by Acidicoala and is not licensed as SteaMidra code.

### CreamInstaller

Author / maintainer: FroggMaster / CreamInstaller contributors
Bundled: No
Modified: No
Used for: Workflow/style inspiration and compatibility reference for DLC unlocker handling.
Notes: SteaMidra does not ship CreamInstaller. SteaMidra has its own implementation for managing compatible unlocker setups. CreamInstaller remains owned by its original authors/contributors.

---

## External APIs, services, and data sources

### online-fix.me

Type: External website/service
Bundled: No
Modified: No
Used for: Searching online-fix.me and opening result pages in the user's browser.
Notes: SteaMidra is not affiliated with online-fix.me. SteaMidra does not store online-fix.me credentials or download files from that site.

### Hubcap Manifest

Type: External manifest library/API
Bundled: No
Modified: No
Used for: Store browser and manifest search/download features.
Notes: Hubcap Manifest remains owned/controlled by its maintainers. SteaMidra is not affiliated with Hubcap Manifest.

### ManifestHub

Maintainer: oureveryday
Type: External manifest archive/API
Bundled: No
Modified: No
Used for: Manifest source / fallback manifest data where applicable.
Notes: ManifestHub remains owned/maintained by its original maintainer.

### CrakFiles

Type: External/community-maintained fix list repository
Bundled: No, unless specific files are included in a release
Modified: No
Used for: Fixes & Bypasses search/listing and applying selected fixes.
Notes: CrakFiles and any referenced fixes remain owned/controlled by their original maintainers/authors. SteaMidra only provides tooling around the list and selected user actions.

### SteamDB

Type: External informational website/data source
Bundled: No
Modified: No
Used for: Depot/app/build/version metadata reference where applicable.
Notes: SteamDB remains owned/controlled by its maintainers. SteaMidra is not affiliated with SteamDB.

### Google Drive API

Type: External API/service
Bundled: No
Modified: No
Used for: Cloud save backup/restore when the user signs in and chooses Google Drive.
Notes: Google Drive remains owned/controlled by Google. SteaMidra is not affiliated with Google.

### rclone-supported providers

Type: External cloud storage providers
Bundled: No
Modified: No
Used for: Cloud save backup/restore through rclone, including providers such as Dropbox, OneDrive, MEGA, S3-compatible storage, Backblaze B2, SFTP, and others.
Notes: Each provider remains owned/controlled by its own operator. SteaMidra is not affiliated with these providers.

---

## Assets and media

### RedPaper / Broken Moon MIDI cover

Author / credit: RedPaper
Original arrangement: U2 Akiyama
Original work: Touhou 7.5: Immaterial and Missing Power
Owners: Team Shanghai Alice and Twilight Frontier
Bundled: Yes, where included in SteaMidra assets
Modified: No
Used for: MIDI/music asset in SteaMidra.
Notes: SteaMidra is not affiliated with or endorsed by Team Shanghai Alice, Twilight Frontier, U2 Akiyama, or RedPaper. All trademarks and original works belong to their respective owners.

### MIDI files and soundfont assets

Path: `c/`
Files include: `.mid` files and `FF5.sf2`
Bundled: Yes
Modified: No
Used for: MIDI/music playback in SteaMidra.
Notes: These assets should be individually credited where their original author/source is known. If any specific asset credit/source is missing, open an issue with the exact file and source so it can be corrected.

### TinySoundFont / TinyMidiLoader headers

Files: `c/tsf.h`, `c/tml.h`
Bundled: Yes
Modified: No
Used for: MIDI playback support.
Notes: These are third-party header libraries and remain owned by their original authors. Their original license/source should be kept with the files or referenced here.

### miniaudio

File: `c/miniaudio_io.h`
Bundled: Yes
Modified: No
Used for: Audio output / MIDI playback support.
Notes: miniaudio remains owned by its original author and is not licensed as SteaMidra code.

### MIDI player library

Files: `c/midi_player_lib.c`, `c/midi_player_lib.dll`
Bundled: Yes
Modified: No, unless otherwise stated
Used for: MIDI playback support.
Notes: If this library includes or links third-party code, the relevant upstream licenses should be included or referenced here.

---

## License scope

SteaMidra is licensed under the GNU General Public License v3.0 for SteaMidra’s own source code.

This GPL license does not apply to third-party tools, binaries, unlockers, emulators, APIs, services, media assets, or external projects except where those components are separately licensed under GPL-compatible terms by their own authors.

Third-party components remain under their original authorship, licenses, and terms.

Nothing in this repository should be read as claiming ownership of third-party work.
