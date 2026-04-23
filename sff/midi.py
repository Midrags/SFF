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

import ctypes
import threading
import time
from pathlib import Path

from sff.structs import MidiFiles
import logging

logger = logging.getLogger(__name__)


def _find_c_files(ext: str) -> list:
    c_dir = MidiFiles.MIDI_PLAYER_DLL.value.parent
    return sorted(c_dir.glob(f"*.{ext}"))


class MidiPlayer:
    def __init__(self, dll: Path, playlist: list, soundfont: Path):
        lib_path = str(dll.resolve())
        try:
            self.player_lib = ctypes.CDLL(lib_path)
        except OSError as e:
            raise ValueError(f"Error loading library: {e}")
        self.CIntArray16 = ctypes.c_int * 16
        self.soundfont = str(soundfont.resolve()).encode()
        self.playlist = list(playlist)
        self._current_idx = 0
        self._running = False
        self._monitor_thread = None
        self.used_channels: list = []
        self.channel_is_active: dict = {}
        self._muted: bool = False
        self.player_lib.StartPlayback.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        self.player_lib.StartPlayback.restype = ctypes.c_int
        self.player_lib.StopPlayback.argtypes = []
        self.player_lib.StopPlayback.restype = None
        self.player_lib.ToggleChannel.argtypes = [ctypes.c_int, ctypes.c_int]
        self.player_lib.ToggleChannel.restype = None
        self.player_lib.GetUsedChannels.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.player_lib.GetUsedChannels.restype = None
        self.player_lib.IsFinished.argtypes = []
        self.player_lib.IsFinished.restype = ctypes.c_int
        logger.debug("MidiPlayer initialized")

    def _start_track(self, midi_path: Path):
        initial_states_py = [1] * 16
        initial_states_c = self.CIntArray16(*initial_states_py)
        midi_b = str(midi_path.resolve()).encode()
        result_holder = [None]
        exc_holder = [None]
        used_channels_holder = [self.CIntArray16()]
        def _run():
            try:
                result_holder[0] = self.player_lib.StartPlayback(
                    midi_b, self.soundfont, initial_states_c
                )
                if result_holder[0] == 0:
                    self.player_lib.GetUsedChannels(used_channels_holder[0])
            except Exception as e:
                exc_holder[0] = e
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=10)
        if exc_holder[0] is not None:
            raise exc_holder[0]
        result = result_holder[0]
        if result != 0:
            logger.warning(
                f"StartPlayback returned {result} for {midi_path.name} "
                f"({'already playing' if result == -1 else 'error'})"
            )
            return False
        self.used_channels = [i for i, used in enumerate(used_channels_holder[0]) if used]
        self.channel_is_active = {ch: True for ch in self.used_channels}
        logger.debug(f"Now playing: {midi_path.name} | channels: {self.used_channels}")
        return True

    def _monitor_playlist(self):
        while self._running:
            time.sleep(0.3)
            if not self._running:
                break
            try:
                if self.player_lib.IsFinished():
                    self.player_lib.StopPlayback()
                    if not self._running:
                        break
                    self._current_idx = (self._current_idx + 1) % len(self.playlist)
                    next_track = self.playlist[self._current_idx]
                    logger.debug(f"Advancing to track {self._current_idx}: {next_track.name}")
                    self._start_track(next_track)
                    if self._muted:
                        self.set_range(0, 15, 0)
            except Exception as e:
                logger.warning(f"Playlist monitor error: {e}")

    def start(self):
        if not self.playlist:
            raise ValueError("Playlist is empty — no MIDI files found in c/ folder")
        self._current_idx = 0
        if not self._start_track(self.playlist[0]):
            raise RuntimeError("Failed to start first track")
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_playlist, daemon=True)
        self._monitor_thread.start()
        logger.debug("MidiPlayer started")

    def toggle_channel(self, channel_to_toggle):
        try:
            if not (0 <= channel_to_toggle < 16):
                raise ValueError("Channel out of range")
            if channel_to_toggle not in self.used_channels:
                logger.debug(f"Channel {channel_to_toggle} not used in current MIDI.")
            new_state = not self.channel_is_active.get(channel_to_toggle, False)
            self.channel_is_active[channel_to_toggle] = new_state
            action = "Unmuting" if new_state else "Muting"
            logger.debug(f"--> {action} channel {channel_to_toggle}...")
            self.player_lib.ToggleChannel(channel_to_toggle, 1 if new_state else 0)
        except ValueError:
            logger.warning("Invalid channel number.")

    def set_channel(self, channel_num, state):
        self.player_lib.ToggleChannel(channel_num, state)

    def set_range(self, start, end, state):
        for x in range(start, end + 1):
            self.set_channel(x, state)

    def set_muted(self, muted: bool):
        self._muted = muted
        self.set_range(0, 15, 0 if muted else 1)

    def stop(self):
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)
        self.player_lib.StopPlayback()
        logger.debug("MidiPlayer stopped")
