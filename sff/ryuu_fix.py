import httpx
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote
import shutil

from colorama import Fore, Style
from sff.prompts import prompt_select
from sff.http_utils import download_to_path
from sff.online_fix import _extract_archive, _detect_archiver

RYUU_URL = "https://generator.ryuu.lol/fixes"

def get_ryuu_games() -> list[tuple[str, str]]:
    """
    Fetches the list of games from Ryuu's website.
    Returns: list of (Game Name, Download URL)
    """
    try:
        print(Fore.CYAN + "Fetching fixes list from generator.ryuu.lol..." + Style.RESET_ALL)
        resp = httpx.get(RYUU_URL, follow_redirects=True, timeout=15)
        resp.raise_for_status()
        html = resp.text
        
        matches = re.findall(r'href="([^"]*?/fixes/([^"]+\.zip))"', html, re.IGNORECASE)
        
        results = []
        for full_url, filename in matches:
            if not full_url.startswith("http"):
                if full_url.startswith("/"):
                    full_url = "https://generator.ryuu.lol" + full_url
                else:
                    full_url = "https://generator.ryuu.lol/" + full_url
            
            name_encoded = filename[:-4] if filename.lower().endswith(".zip") else filename
            name = unquote(name_encoded)
            
            results.append((name, full_url))
            
        return list(set(results))
        
    except Exception as e:
        print(Fore.RED + f"Error fetching Ryuu list: {e}" + Style.RESET_ALL)
        return []


def search_ryuu(query_name: str, all_games: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Searches for a game by name in the list of games.
    """
    query = query_name.lower().strip()
    
    matches = []
    
    # 1. Exact match
    for name, url in all_games:
        if name.lower() == query:
             matches.insert(0, (name, url))
    
    # 2. Contains match
    for name, url in all_games:
        if query in name.lower() and (name, url) not in matches:
            matches.append((name, url))

    return matches


def apply_ryuu_fix(game_name: str, game_folder: Path) -> bool:
    all_games = get_ryuu_games()
    if not all_games:
        return False
        
    matches = search_ryuu(game_name, all_games)
    
    if not matches:
        print(Fore.YELLOW + f"No direct match found for '{game_name}'. You can select manually." + Style.RESET_ALL)
        options = [(name, url) for name, url in sorted(all_games, key=lambda x: x[0])]
    else:
        print(Fore.GREEN + f"Found {len(matches)} matches." + Style.RESET_ALL)
        options = matches

    options.append(("Cancel", "CANCEL"))
    
    # Use prompt_select with fuzzy search
    chosen_url = prompt_select(
        "Select the fix to download:",
        options,
        fuzzy=True,
        max_height=15
    )
    
    if chosen_url == "CANCEL" or chosen_url is None:
        return False

    temp_dir = Path(tempfile.mkdtemp(prefix="sff_ryuu_fix_"))
    try:
        print(Fore.CYAN + f"\nDownloading fix to temporary folder..." + Style.RESET_ALL)
        file_name = chosen_url.split("/")[-1]
        zip_path = temp_dir / unquote(file_name)
        
        success = download_to_path(chosen_url, zip_path)
        if not success:
            print(Fore.RED + "Download failed!" + Style.RESET_ALL)
            return False
            
        print(Fore.GREEN + "Download complete." + Style.RESET_ALL)
        
        if zip_path.suffix.lower() == ".zip":
            import zipfile
            print(Fore.CYAN + "Extracting zip file directly..." + Style.RESET_ALL)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(game_folder)
            print(Fore.GREEN + f"✓ Extraction complete!" + Style.RESET_ALL)
        else:
            # Fallback to archiver for .rar / .7z
            archiver_type, archiver_path = _detect_archiver()
            if not archiver_type:
                print(Fore.RED + "No archiver found. Please install WinRAR or 7-Zip." + Style.RESET_ALL)
                return False
            if not _extract_archive(zip_path, game_folder, archiver_type, archiver_path, password=""):
                return False
                
        print()
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(Fore.GREEN + "  RYUU FIX APPLIED SUCCESSFULLY!" + Style.RESET_ALL)
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(f"Game:   {game_name}")
        print(f"Folder: {game_folder}")
        print()
        return True
        
    except Exception as e:
        print(Fore.RED + f"Error applying Ryuu fix: {e}" + Style.RESET_ALL)
        return False
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
