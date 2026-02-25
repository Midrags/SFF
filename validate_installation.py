"""
Comprehensive validation script for SteamForge Fetcher (SFF) installation
Checks all components, dependencies, and functionality
"""

import sys
from pathlib import Path
from colorama import Fore, Style, init as color_init

color_init()

def print_header(text):
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{text}")
    print(f"{'='*80}{Style.RESET_ALL}")

def print_check(name, passed, details=""):
    status = f"{Fore.GREEN}✓{Style.RESET_ALL}" if passed else f"{Fore.RED}✗{Style.RESET_ALL}"
    print(f"{status} {name}")
    if details:
        print(f"  {Fore.YELLOW}{details}{Style.RESET_ALL}")

def check_python_version():
    """Check Python version is 3.11+"""
    print_header("Checking Python Version")
    version = sys.version_info
    required = (3, 11)
    passed = version >= required
    print_check(
        f"Python {version.major}.{version.minor}.{version.micro}",
        passed,
        f"Required: Python {required[0]}.{required[1]}+" if not passed else ""
    )
    return passed

def check_core_dependencies():
    """Check core dependencies are installed"""
    print_header("Checking Core Dependencies")
    
    dependencies = [
        ("colorama", "colorama"),
        ("steam", "steam"),
        ("msgpack", "msgpack"),
        ("cryptography", "cryptography"),
        ("keyring", "keyring"),
        ("tqdm", "tqdm"),
        ("requests", "requests"),
        ("vdf", "vdf"),
        ("gevent", "gevent"),
        ("httpx", "httpx"),
    ]
    
    all_passed = True
    for name, import_name in dependencies:
        try:
            __import__(import_name)
            print_check(name, True)
        except ImportError as e:
            print_check(name, False, str(e))
            all_passed = False
    
    return all_passed

def check_enhancement_dependencies():
    """Check enhancement feature dependencies"""
    print_header("Checking Enhancement Dependencies")
    
    dependencies = [
        ("win10toast", "win10toast", "Desktop notifications"),
        ("selenium", "selenium", "Online-fix multiplayer"),
        ("webdriver-manager", "webdriver_manager", "Automatic ChromeDriver"),
    ]
    
    all_passed = True
    for name, import_name, feature in dependencies:
        try:
            __import__(import_name)
            print_check(f"{name} ({feature})", True)
        except ImportError as e:
            print_check(f"{name} ({feature})", False, f"Optional: {str(e)}")
            # Don't fail for optional dependencies
    
    return all_passed

def check_sff_modules():
    """Check all SFF modules can be imported"""
    print_header("Checking SFF Modules")
    
    modules = [
        # Core modules
        ("sff.utils", "Core utilities"),
        ("sff.structs", "Data structures"),
        ("sff.strings", "String constants"),
        ("sff.ui", "User interface"),
        ("sff.steam_client", "Steam client"),
        ("sff.steam_path", "Steam path detection"),
        
        # Storage modules
        ("sff.storage.settings", "Settings management"),
        ("sff.storage.vdf", "VDF parsing"),
        ("sff.storage.acf", "ACF parsing"),
        
        # Lua modules
        ("sff.lua.manager", "Lua manager"),
        ("sff.lua.writer", "Lua writer"),
        
        # Manifest modules
        ("sff.manifest.downloader", "Manifest downloader"),
        ("sff.manifest.crypto", "Manifest crypto"),
        
        # Enhancement modules
        ("sff.cache", "API caching"),
        ("sff.backup", "Backup system"),
        ("sff.notifications", "Desktop notifications"),
        ("sff.recent_files", "Recent files"),
        ("sff.library_scanner", "Library scanner"),
        ("sff.progress", "Progress bars"),
        ("sff.integrity", "Integrity verification"),
        ("sff.analytics", "Analytics tracking"),
        ("sff.keyboard_shortcuts", "Keyboard shortcuts"),
        ("sff.online_fix", "Online-fix integration"),
    ]
    
    all_passed = True
    for module, description in modules:
        try:
            __import__(module)
            print_check(f"{module} ({description})", True)
        except Exception as e:
            print_check(f"{module} ({description})", False, str(e))
            all_passed = False
    
    return all_passed

def check_file_structure():
    """Check required files and folders exist"""
    print_header("Checking File Structure")
    
    required_files = [
        ("Main.py", "Entry point"),
        ("requirements.txt", "Dependencies list"),
        ("sff/ui.py", "UI module"),
        ("sff/structs.py", "Data structures"),
        ("tests/test_all_features.py", "Test suite"),
    ]
    
    required_folders = [
        ("sff", "Core modules"),
        ("sff/storage", "Storage modules"),
        ("sff/lua", "Lua modules"),
        ("sff/manifest", "Manifest modules"),
        ("docs", "Documentation"),
        ("tests", "Test suites"),
    ]
    
    all_passed = True
    
    for file, description in required_files:
        path = Path(file)
        passed = path.exists() and path.is_file()
        print_check(f"{file} ({description})", passed)
        if not passed:
            all_passed = False
    
    for folder, description in required_folders:
        path = Path(folder)
        passed = path.exists() and path.is_dir()
        print_check(f"{folder}/ ({description})", passed)
        if not passed:
            all_passed = False
    
    return all_passed

def check_settings_enum():
    """Check Settings enum has all required values"""
    print_header("Checking Settings Configuration")
    
    try:
        from sff.structs import Settings
        
        required_settings = [
            "ADVANCED_MODE",
            "STEAM_PATH",
            "PARALLEL_DOWNLOADS",
            "USE_PARALLEL_DOWNLOADS",
            "ENABLE_NOTIFICATIONS",
            "BACKUP_RETENTION",
            "ONLINE_FIX_USER",
            "ONLINE_FIX_PASS",
        ]
        
        all_passed = True
        for setting in required_settings:
            passed = hasattr(Settings, setting)
            print_check(f"Settings.{setting}", passed)
            if not passed:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print_check("Settings enum", False, str(e))
        return False

def check_main_menu():
    """Check MainMenu enum has all required options"""
    print_header("Checking Main Menu Configuration")
    
    try:
        from sff.structs import MainMenu
        
        required_options = [
            "MANAGE_LUA",
            "RECENT_FILES",
            "SCAN_LIBRARY",
            "ANALYTICS",
            "SETTINGS",
            "EXIT",
        ]
        
        all_passed = True
        for option in required_options:
            passed = hasattr(MainMenu, option)
            print_check(f"MainMenu.{option}", passed)
            if not passed:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print_check("MainMenu enum", False, str(e))
        return False

def check_ui_methods():
    """Check UI class has all required methods"""
    print_header("Checking UI Methods")
    
    try:
        from sff.ui import UI
        
        required_methods = [
            "edit_settings_menu",
            "recent_files_menu",
            "scan_library_menu",
            "analytics_dashboard_menu",
            "process_lua_full",
            "process_lua_minimal",
        ]
        
        all_passed = True
        for method in required_methods:
            passed = hasattr(UI, method)
            print_check(f"UI.{method}", passed)
            if not passed:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print_check("UI class", False, str(e))
        return False

def run_quick_tests():
    """Run quick functionality tests"""
    print_header("Running Quick Functionality Tests")
    
    all_passed = True
    
    # Test cache
    try:
        from sff.cache import get_cache
        cache = get_cache()
        cache.set("test", "value", ttl=60)
        result = cache.get("test")
        passed = result == "value"
        print_check("Cache functionality", passed)
        if not passed:
            all_passed = False
    except Exception as e:
        print_check("Cache functionality", False, str(e))
        all_passed = False
    
    # Test analytics
    try:
        from sff.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        tracker.record_operation("test", success=True)
        passed = len(tracker.data.operations) > 0
        print_check("Analytics functionality", passed)
        if not passed:
            all_passed = False
    except Exception as e:
        print_check("Analytics functionality", False, str(e))
        all_passed = False
    
    # Test recent files
    try:
        from sff.recent_files import get_recent_files_manager
        manager = get_recent_files_manager()
        recent = manager.get_all()
        passed = isinstance(recent, list)
        print_check("Recent files functionality", passed)
        if not passed:
            all_passed = False
    except Exception as e:
        print_check("Recent files functionality", False, str(e))
        all_passed = False
    
    # Test notifications
    try:
        from sff.notifications import get_notification_service
        service = get_notification_service()
        passed = service is not None
        print_check("Notification service", passed)
        if not passed:
            all_passed = False
    except Exception as e:
        print_check("Notification service", False, str(e))
        all_passed = False
    
    return all_passed

def main():
    """Run all validation checks"""
    print(f"{Fore.CYAN}{'='*80}")
    print("SteamForge Fetcher (SFF) Installation Validation")
    print(f"{'='*80}{Style.RESET_ALL}\n")
    
    results = []
    
    results.append(("Python Version", check_python_version()))
    results.append(("Core Dependencies", check_core_dependencies()))
    results.append(("Enhancement Dependencies", check_enhancement_dependencies()))
    results.append(("SFF Modules", check_sff_modules()))
    results.append(("File Structure", check_file_structure()))
    results.append(("Settings Configuration", check_settings_enum()))
    results.append(("Main Menu Configuration", check_main_menu()))
    results.append(("UI Methods", check_ui_methods()))
    results.append(("Quick Functionality Tests", run_quick_tests()))
    
    # Summary
    print_header("Validation Summary")
    
    total = len(results)
    passed = sum(1 for _, result in results if result)
    failed = total - passed
    
    for name, result in results:
        status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if result else f"{Fore.RED}FAIL{Style.RESET_ALL}"
        print(f"[{status}] {name}")
    
    print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"Total Checks: {total}")
    print(f"Passed: {Fore.GREEN}{passed}{Style.RESET_ALL}")
    print(f"Failed: {Fore.RED}{failed}{Style.RESET_ALL}")
    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"Success Rate: {Fore.CYAN}{success_rate:.1f}%{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
    
    if failed == 0:
        print(f"{Fore.GREEN}✓ All validation checks passed!{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✓ SFF is properly installed and configured.{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✓ Ready to build and use!{Style.RESET_ALL}\n")
        return 0
    else:
        print(f"{Fore.YELLOW}⚠ Some validation checks failed.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}⚠ Review the errors above and fix them.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}⚠ Run 'pip install -r requirements.txt' to install missing dependencies.{Style.RESET_ALL}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
