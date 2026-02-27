from io import BytesIO
from typing import Literal, Union, overload
import zipfile
from pathlib import Path

from colorama import Fore, Style


@overload
def read_lua_from_zip(path: Union[Path, BytesIO]) -> Union[str, None]: ...


@overload
def read_lua_from_zip(
    path: Union[Path, BytesIO], decode: Literal[True]
) -> Union[str, None]: ...


@overload
def read_lua_from_zip(
    path: Union[Path, BytesIO], decode: Literal[False]
) -> Union[bytes, None]: ...


def read_lua_from_zip(path: Union[Path, BytesIO], decode: bool = True):
    """Given a zip path, return the string contents,
    None if it can't be found"""
    lua_contents = None
    try:
        with zipfile.ZipFile(path) as f:
            for file in f.filelist:
                if file.filename.endswith(".lua"):
                    print(f".lua found in ZIP: {file.filename}")
                    if lua_contents is None:
                        lua_contents = f.read(file)
                elif file.filename.endswith(".manifest"):
                    filename = Path(file.filename).name
                    print(f"Manifest found in ZIP: {filename}")
                    manifests_dir = Path.cwd() / "manifests"
                    manifests_dir.mkdir(exist_ok=True)
                    with (manifests_dir / filename).open("wb") as mf:
                        mf.write(f.read(file))
            if lua_contents is None:
                print(Fore.RED + "Could not find the lua in the ZIP" + Style.RESET_ALL)
    except zipfile.BadZipFile:
        return
    if decode and lua_contents:
        lua_contents = lua_contents.decode(encoding="utf-8")
    return lua_contents


def read_file_from_zip_bytes(filename: Union[str, zipfile.ZipInfo], bytes: bytes):
    """Returns none if it's an invalid ZIP file"""
    try:
        with zipfile.ZipFile(BytesIO(bytes)) as f:
            return BytesIO(f.read(filename))
    except zipfile.BadZipFile:
        return


def read_nth_file_from_zip_bytes(nth: int, bytes: bytes):
    """Returns none if it's an invalid ZIP file"""
    try:
        with zipfile.ZipFile(BytesIO(bytes)) as f:
            return BytesIO(f.read(f.filelist[nth].filename))
    except zipfile.BadZipFile:
        return


def zip_folder(folder_path: Path, output_path: Path):
    """ZIPs to a BytesIO then to the actual file to prevent infinite recursion"""
    tmp = BytesIO()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in folder_path.rglob('*'):
            if file.is_file():
                zipf.write(file, arcname=file.relative_to(folder_path))
    tmp.seek(0)
    with output_path.open("wb") as f:
        f.write(tmp.read())
