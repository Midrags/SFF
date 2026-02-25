import ctypes
import shutil
import sys
import time
from collections import deque
from pathlib import Path
from typing import Callable

from smd.storage.ini_config import edit_ini_option
from smd.utils import root_folder

if sys.platform == "win32":
    import winsound
else:
    class winsound:
        @staticmethod
        def Beep(*args):
            return None

class Konami:
    def __init__(self, on_success: Callable[[], None]):
        self.on_success = on_success
        self.running = False

        # https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
        self.vk_map = {
            0x26: "UP",
            0x28: "DOWN",
            0x25: "LEFT",
            0x27: "RIGHT",
            0x42: "b",
            0x41: "a",
        }

        self.code = [
            "UP",
            "UP",
            "DOWN",
            "DOWN",
            "LEFT",
            "RIGHT",
            "LEFT",
            "RIGHT",
            "b",
            "a",
        ]

        self.buffer: deque[str] = deque(maxlen=len(self.code))
        "Track last 10 key presses"

        self.key_states = {k: False for k in self.vk_map.keys()}
        "Track previous key state"

    def listen(self):
        self.running = True
        try:
            while self.running:
                for vk, name in self.vk_map.items():
                    # GetAsyncKeyState returns short (16-bit) (up to 2^15).
                    # 0x8000 == 2^15, MSB determines press state
                    is_down = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

                    if is_down and not self.key_states[vk]:
                        # Key went from not pressed to pressed
                        self.buffer.append(name)

                        if list(self.buffer) == self.code:
                            self.buffer.clear()
                            winsound.Beep(200, 250)
                            self.on_success()
                            winsound.Beep(250, 250)

                    self.key_states[vk] = is_down

                time.sleep(0.05)

        except Exception as e:
            print(f"Konami listener failed: {e}")

    def stop(self):
        self.running = False


def replace_boot_image(injector_dir: Path):
    ini_file = injector_dir / "DLLInjector.ini"
    if not ini_file.exists():
        return
    new_val = edit_ini_option(
        ini_file,
        "DllInjector",
        "BootImage",
        lambda x: str(Path(x).with_name("gangster.bmp")),
    )
    if new_val is None:
        return
    src = root_folder() / "static/gangster.bmp"
    dst = injector_dir / new_val
    shutil.copy(src, dst)
