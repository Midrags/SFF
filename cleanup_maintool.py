import shutil
import os
from pathlib import Path

target = Path(r"C:\Users\Syrer\SFF\Idk\Maintool")
to_delete = [
    ".agents", ".cursor", ".gemini", "venv", "build", "dist",
    "GLDLL", "tmp_stfixer", "DLL_files", "DLL_Analysis", "GLDLL_Analysis", "out"
]

for folder in to_delete:
    p = target / folder
    if p.exists():
        print(f"Deleting {p}")
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        except Exception as e:
            print(f"Failed to delete {p}: {e}")

print("Cleanup finished.")
