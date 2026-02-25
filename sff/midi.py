import ctypes
from pathlib import Path

from sff.structs import MidiFiles
import logging

logger = logging.getLogger(__name__)


class MidiPlayer:
    def __init__(self, dll: Path):
        lib_path = str(dll.resolve())
        try:
            self.player_lib = ctypes.CDLL(lib_path)
        except OSError as e:
            raise ValueError(f"Error loading library: {e}")

        self.CIntArray16 = ctypes.c_int * 16
        self.soundfont = str(MidiFiles.SOUNDFONT.value.resolve()).encode()
        self.midi = str(MidiFiles.MIDI.value.resolve()).encode()
        logger.debug("MidiPlayer initialized")

    def start(self):
        # All channels on by default
        initial_states_py = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

        # Convert the Python list to a C-compatible array
        initial_states_c = self.CIntArray16(*initial_states_py)

        result = self.player_lib.StartPlayback(
            self.midi, self.soundfont, initial_states_c
        )

        if result != 0 and result != -1:
            print(f"C library returned an error on start: {result}")
            return

        used_channels_data = self.CIntArray16()
        self.player_lib.GetUsedChannels(used_channels_data)
        self.used_channels = [i for i, used in enumerate(used_channels_data) if used]

        self.channel_is_active = {
            ch: (initial_states_py[ch] == 1) for ch in self.used_channels
        }

        logger.debug(f"MIDI file uses channels: {self.used_channels}")
        logger.debug("MidiPlayer started")

    def toggle_channel(self, channel_to_toggle: int):
        try:
            if not (0 <= channel_to_toggle < 16):
                raise ValueError("Channel out of range")
            if channel_to_toggle not in self.used_channels:
                logger.debug(
                    f"Warning: Channel {channel_to_toggle} is "
                    "not used in this MIDI file."
                )

            # Update Python state
            new_state = not self.channel_is_active.get(channel_to_toggle, False)
            self.channel_is_active[channel_to_toggle] = new_state
            action = 'Unmuting' if new_state else 'Muting'
            logger.debug(
                f"--> {action} channel {channel_to_toggle}..."
            )
            # Send command to C library
            self.player_lib.ToggleChannel(channel_to_toggle, 1 if new_state else 0)

        except ValueError:
            print("Invalid input. Please enter a number between 0 and 15, or 'q'.")

    def set_channel(self, channel_num: int, state: int):
        self.player_lib.ToggleChannel(channel_num, state)

    def set_range(self, start: int, end: int, state: int):
        for x in range(start, end + 1):
            self.set_channel(x, state)

    def stop(self):
        self.player_lib.StopPlayback()
        logger.debug("MidiPlayer stopped")
