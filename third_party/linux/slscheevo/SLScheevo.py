#!/usr/bin/env python3
import concurrent.futures
import json
import vdf
import os
import re
import shutil
import sys
import time
import traceback
import requests
import platform
import itertools
import base64
import subprocess
import uuid
import getpass
import hashlib
import argparse
import logging
from gevent import Timeout
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from steam.client import SteamClient
from steam.core.msg import MsgProto
from steam.enums.common import EResult
from steam.enums.emsg import EMsg
from steam.webauth import WebAuth
from concurrent.futures import ThreadPoolExecutor, as_completed

# Exit codes
EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_LOGIN_FAILED = 2
EXIT_NO_ACCOUNT_ID = 3
EXIT_NO_APP_IDS = 4
EXIT_INPUT_REQUIRED = 5
EXIT_NO_SCHEMA_FOUND = 6
EXIT_FILE_ERROR = 7
EXIT_STEAM_NOT_FOUND = 8
EXIT_TOKEN_ERROR = 9
EXIT_NO_ACTIONS = 10
EXIT_NOT_SUPPORTED = 11
EXIT_FAILED_TO_GET_HWID = 12
EXIT_NO_ACCOUNT_SPECIFIED = 13
EXIT_FAILED_TO_PARSE_ID = 14

class ConsoleFormatter(logging.Formatter):
    """Formatter for console without timestamps"""
    SYMBOLS = {
        'SUCCESS': "[OK] ",
        'INFO': "[->] ",
        'WARNING': "[!!] ",
        'ERROR': "[XX] "
    }

    def format(self, record):
        symbol = ""

        if hasattr(record, "custom_level"):
            symbol = self.SYMBOLS.get(record.custom_level, "")
        elif record.levelname == "INFO":
            symbol = "[→] "

        return f"{symbol}{record.getMessage()}"

class Logger:
    """Logger class to handle all logging operations"""

    def __init__(self, main=None):
        self.main = main

    def setup_logging(self):
        """Setup logging to both console and file"""
        self.main.DATA_DIR.mkdir(exist_ok=True, parents=True)

        # Create logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Clear any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # File handler with timestamps
        file_handler = logging.FileHandler(self.main.LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler without timestamps and UTF-8 encoding
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ConsoleFormatter()
        console_handler.setFormatter(console_formatter)

        logger.addHandler(console_handler)

    def log_base(self, message):
        """Log message without any symbols"""
        logger = logging.getLogger()
        if logger.isEnabledFor(logging.INFO):
            record = logging.LogRecord(
                name=__name__,
                level=logging.INFO,
                pathname=__file__,
                lineno=0,
                msg=message,
                args=None,
                exc_info=None
            )
            record.custom_level = 'BASE'
            logger.handle(record)

    def log_info(self, message):
        """Log info message with [->] symbol"""
        logger = logging.getLogger()
        if logger.isEnabledFor(logging.INFO):
            record = logging.LogRecord(
                name=__name__,
                level=logging.INFO,
                pathname=__file__,
                lineno=0,
                msg=message,
                args=None,
                exc_info=None
            )
            record.custom_level = 'INFO'
            logger.handle(record)

    def log_success(self, message):
        """Log success message with [OK] symbol"""
        logger = logging.getLogger()
        if logger.isEnabledFor(logging.INFO):
            record = logging.LogRecord(
                name=__name__,
                level=logging.INFO,
                pathname=__file__,
                lineno=0,
                msg=message,
                args=None,
                exc_info=None
            )
            record.custom_level = 'SUCCESS'
            logger.handle(record)

    def log_error(self, message):
        """Log error message with [XX] symbol"""
        logger = logging.getLogger()
        if logger.isEnabledFor(logging.ERROR):
            record = logging.LogRecord(
                name=__name__,
                level=logging.ERROR,
                pathname=__file__,
                lineno=0,
                msg=message,
                args=None,
                exc_info=None
            )
            record.custom_level = 'ERROR'
            logger.handle(record)

    def log_warning(self, message):
        """Log warning message with [!!] symbol"""
        logger = logging.getLogger()
        if logger.isEnabledFor(logging.WARNING):
            record = logging.LogRecord(
                name=__name__,
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg=message,
                args=None,
                exc_info=None
            )
            record.custom_level = 'WARNING'
            logger.handle(record)

    def install_global_exception_logger(self):
        """Catch all unhandled exceptions and log them before exiting."""

        def handle_exception(exc_type, exc_value, exc_traceback):
            logger = logging.getLogger()

            if issubclass(exc_type, KeyboardInterrupt):
                # Don't log Ctrl+C as an error
                logger.info("Interrupted by user (KeyboardInterrupt).")
                return

            # Log full traceback to file
            logger.error("UNHANDLED EXCEPTION OCCURRED!", exc_info=(exc_type, exc_value, exc_traceback))

            # Also log a clean message to the console
            self.log_error(f"Unhandled crash: {exc_value}")

        sys.excepthook = handle_exception

    def prompt(self, msg: str) -> str:
        """Log a prompt with [→] but keep input on same line."""
        prefix = ConsoleFormatter.SYMBOLS.get("INFO", "[->] ")

        # Print prefix and message WITHOUT newline
        print(f"{prefix}{msg} ", end="", flush=True)

        # Now take input
        return input()

    def promptwarn(self, msg: str) -> str:
        """Log a prompt with [→] but keep input on same line."""
        prefix = ConsoleFormatter.SYMBOLS.get("INFO", "[!!] ")

        # Print prefix and message WITHOUT newline
        print(f"{prefix}{msg} ", end="", flush=True)

        # Now take input
        return input()

class SteamLogin:
    """Class to handle Steam login operations"""

    def __init__(self, main):
        self.main = main
        self.logger = main.logger

    def setup_login_credentials(self, login_input=None):
        """Setup all login credentials and target information"""
        self.saved_logins = self.load_saved_logins()
        self.login_input = login_input

        # Parse target account info
        self.target_username, self.target_account_id, self.target_steam_id64 = \
            self.get_target_account_info(login_input)

        # Get environment credentials
        self.env_username = os.environ.get('STEAMUSERNAME', '')
        self.env_password = os.environ.get('STEAMPASSWORD', '')

        # Find saved login
        self.saved_username, self.saved_refresh_token = self.find_saved_login()

        # Determine final username
        self.username = self.determine_username()

        # Find refresh token
        self.refresh_token = self.find_refresh_token()

    def login(self, login_input=None):
        """Login to Steam using saved logins or interactive login"""
        # Step 1: Setup all login credentials
        self.setup_login_credentials(login_input)

        # Step 2: Perform login cycle
        result = self.attempt_login()

        # Step 3: Handle login result
        if result != EResult.OK:
            self.logger.log_error(f"Steam login failed, exiting")
            self.client.logout()
            sys.exit(EXIT_LOGIN_FAILED)

        # Extract account info
        self.steam_id64 = self.client.steam_id.as_64
        self.account_id = self.client.steam_id.account_id

        # Step 4: Save successful login data
        self.save_successful_login()

        self.logger.log_success("Logged into Steam successfully")
        return self.client, self.steam_id64, self.account_id

    def get_username_silent_mode(self):
        """Handle silent mode when no username is available"""
        last_account = self.load_last_account()
        if last_account:
            self.logger.log_info(f"Using last account: {last_account}")
            # Just return the username, not the full login result
            # The login() method will be called again with this username
            return last_account
        else:
            self.logger.log_error("No username provided, please select a user with --login. Read more with --help")
            sys.exit(EXIT_NO_ACCOUNT_SPECIFIED)

    def determine_username(self):
        """Determine the final username through various methods"""
        username = self.saved_username or self.target_username or self.target_steam_id64 or self.env_username

        if not username:
            username = self.get_username_from_user()

        return username

    def get_username_from_user(self):
        """Get username through interactive selection or input"""
        # In silent mode, directly use the last saved account instead of interactive selection
        if self.main.SILENT_MODE:
            return self.get_username_silent_mode()

        # Try interactive selection first (interactive mode only)
        selected_username = self.select_account_interactively()
        if selected_username:
            return selected_username

        # Fallback to manual input
        self.logger.log_base("No Steam accounts found, please log in manually")
        return input("Steam Username: ").strip()

    def select_account_interactively(self):
        """Let user select an account from available options"""
        available_accounts = self.get_available_accounts()
        if not available_accounts:
            return None

        self.logger.log_info("Available accounts:")
        for i, user in enumerate(available_accounts, 1):
            self.logger.log_base(f"[{i}]: {user}")

        try:
            num = int(self.logger.prompt("Choose an account to login (0 for new account):"))
            if 0 < num <= len(available_accounts):
                return available_accounts[num - 1]
        except ValueError:
            pass

        return None

    def get_available_accounts(self):
        """Get list of available account names from various sources"""
        accounts = []

        # Accounts from loginusers.vdf (dict keyed by steamid)
        vdf_accounts = self.parse_loginusers_vdf()
        for user in vdf_accounts.values():
            name = user.get("AccountName")
            if name:
                accounts.append(name)

        # Accounts from saved logins
        saved_logins = self.load_saved_logins()
        for login_data in saved_logins.values():
            name = login_data.get("username")
            if name:
                accounts.append(name)

        # Remove duplicates while preserving order
        seen = set()
        unique_accounts = []
        for name in accounts:
            if name not in seen:
                seen.add(name)
                unique_accounts.append(name)

        return unique_accounts

    def attempt_login(self):
        """Perform the main login"""
        result = None
        prompt_disabled = False
        login_timeout = 60
        retry_count = 1
        max_tries = 10
        self.client = SteamClient()

        while True:
            try:
                print("")
                if retry_count == 1:
                    self.logger.log_info(f"Logging in...")
                else:
                    self.logger.log_info(f"Login attempt {retry_count}...")
                with Timeout(login_timeout):
                    if not self.refresh_token:
                        if not self.perform_web_authentication():
                            self.client.logout()
                            sys.exit(EXIT_LOGIN_FAILED)
                    if self.env_password or self.refresh_token:
                        result = self.client.login(self.username, self.env_password, self.refresh_token)
            except Timeout:
                self.logger.log_warning(f"Login timed out after {login_timeout} seconds")
                result = EResult.Timeout
            except Exception as e:
                self.logger.log_error(f"Login error: {e}")
                result = None

            extra_wait_time = 0
            if result == EResult.OK:
                break
            elif result == EResult.InvalidPassword:
                if self.refresh_token or self.main.SILENT_MODE:
                    self.logger.log_error("Looks like the token wasn't accepted or the password is wrong")
                    self.logger.log_error(f"Try deleting '{self.main.SAVED_LOGINS_FILE}' and then try again.")
                    sys.exit(EXIT_LOGIN_FAILED)
                else:
                    self.logger.log_error("Invalid password. Please try again with the correct one")
                    self.client.logout()
                    self.client.disconnect()
                    continue
            elif result == EResult.TryAnotherCM:
                self.logger.log_error("The Steam Servers aren't letting us login (TryAnotherCM) - Waiting longer before contacting the servers again")
                extra_wait_time = 20
            elif result == EResult.Timeout:
                self.logger.log_error("The login attempt timed out (Timeout)")
            elif result == EResult.ServiceUnavailable:
                self.logger.log_error("The Steam Servers aren't available right now (ServiceUnavailable)")
            else:
                self.logger.log_error(f"An unrecognized error occurred when trying to login: {result}")

            if self.main.SILENT_MODE and not self.main.INFINITE_RETRY and prompt_disabled:
                sys.exit(EXIT_LOGIN_FAILED)

            if not self.main.SILENT_MODE and not prompt_disabled:
                self.handle_service_unavailable()
            prompt_disabled = True

            # Ask if we should continue
            if not self.main.INFINITE_RETRY and not self.main.SILENT_MODE and retry_count >= max_tries:
                self.handle_service_unavailable()
                max_tries += 5

            base_wait = min(5 * (2 ** (retry_count - 1)), 60)
            jitter = base_wait * 0.1  # Add 10% random jitter
            wait_time = base_wait + (time.time() % jitter) + extra_wait_time

            self.logger.log_info(f"Waiting {wait_time:.1f} seconds before retrying ({retry_count}/{'infinity' if self.main.INFINITE_RETRY else max_tries})")
            self.client.logout()
            self.client.disconnect()
            time.sleep(wait_time * 0.3)
            self.client = SteamClient()
            time.sleep(wait_time * 0.7)

            retry_count += 1
            continue

        return result

    def handle_service_unavailable(self):
        """Handle Steam service unavailable scenario with y/n/i options"""
        while True:
            answer = self.logger.promptwarn(f"Keep retrying? (y=yes, n=no, i=infinite): ").lower()
            if answer == 'i':
                self.main.INFINITE_RETRY = True
                self.logger.log_info("Retrying infinitely. Press CTRL+C to cancel")
                return
            elif answer == 'y':
                self.main.INFINITE_RETRY = False
                self.logger.log_info("Retrying.")
                return
            else:
                self.logger.log_info("No retry selected, exiting.")
                sys.exit(EXIT_LOGIN_FAILED)

    def perform_web_authentication(self):
        """Perform web-based authentication when no refresh token exists"""
        if not self.env_password and self.main.SILENT_MODE:
            return False

        try:
            webauth = WebAuth()
            webauth.cli_login(self.username, self.env_password)
            self.username = webauth.username
            self.env_password = webauth.password
            self.refresh_token = webauth.refresh_token
            return True
        except Exception as e:
            self.logger.log_error(f'Web authentication failed: {e}')
            return False

    def save_successful_login(self):
        """Save login data after successful authentication"""
        if self.refresh_token:
            self.saved_logins[self.steam_id64] = {
                "username": self.username,
                "refresh_token": self.refresh_token,
                "account_id": self.account_id,
                "steam_id64": self.steam_id64
            }

            if self.save_saved_logins(self.saved_logins):
                self.logger.log_success(f"Saved encrypted login token for {self.username}")

        # Save last used account
        account_identifier = self.login_input if self.login_input else self.username
        self.save_last_account(account_identifier)

        # Add our account to owner list
        if self.steam_id64 not in self.main.TOP_OWNER_IDS:
            self.main.TOP_OWNER_IDS.insert(0, self.steam_id64)
            self.logger.log_info(f"Added your account ({self.steam_id64}) to owner list")

    def get_target_account_info(self, login_input):
        """Parse login input to determine target account"""
        if not login_input:
            return None, None, None

        target_account_id, target_steam_id64 = self.parse_steam_id(login_input)
        target_username = login_input if not target_account_id else None

        return target_username, target_account_id, target_steam_id64

    def find_saved_login(self):
        """Find matching login in saved logins database"""
        if self.target_steam_id64 and self.target_steam_id64 in self.saved_logins:
            login_data = self.saved_logins[self.target_steam_id64]
            return login_data.get("username", ""), login_data.get("refresh_token")
        elif self.target_username and self.target_username in self.saved_logins:
            login_data = self.saved_logins[self.target_username]
            return login_data.get("username", ""), login_data.get("refresh_token")

        return "", None

    def find_refresh_token(self):
        """Find refresh token for the current username"""
        if self.saved_refresh_token:
            return self.saved_refresh_token

        # Search all saved logins for this username
        for login_data in self.saved_logins.values():
            if login_data.get("username") == self.username:
                return login_data.get("refresh_token")

        return None

    def steamid64_from_account_id(self, account_id: int) -> int:
        """Convert AccountID (32-bit) to public SteamID64"""
        return self.main.STEAMID64_BASE + account_id

    def account_id_from_steamid64(self, steamid64: int) -> int:
        """Extract 32-bit AccountID from public Steam64"""
        return steamid64 - self.main.STEAMID64_BASE

    def parse_steam_id(self, identifier: str):
        identifier = identifier.strip()
        account_id = None
        steam_id64 = None

        # Steam2 ID: STEAM_X:Y:Z
        if identifier.upper().startswith('STEAM_'):
            try:
                steam_prefix, y, z = identifier.split(':')
                universe = int(steam_prefix.split('_')[1])
                y = int(y)
                z = int(z)
                account_id = (z << 1) | y
                steam_id64 = self.steamid64_from_account_id(account_id)
            except Exception as e:
                self.logger.log_error(f"Failed to parse Steam2 ID ({identifier}): {e}")
                sys.exit(EXIT_FAILED_TO_PARSE_ID)

        # Steam3 ID: [U:1:ACCOUNT_ID]
        elif identifier.startswith('[U:') and identifier.endswith(']'):
            try:
                parts = identifier[1:-1].split(':')
                account_id = int(parts[-1])
                steam_id64 = self.steamid64_from_account_id(account_id)
            except Exception as e:
                self.logger.log_error(f"Failed to parse Steam3 ID ({identifier}): {e}")
                sys.exit(EXIT_FAILED_TO_PARSE_ID)

        # Pure numeric input
        elif identifier.isdigit():
            num = int(identifier)
            try:
                if num >= 76561197960265728:  # Steam64 (public)
                    account_id = self.account_id_from_steamid64(num)
                    steam_id64 = num
                elif num <= 4294967295:  # 32-bit AccountID
                    account_id = num
                    steam_id64 = self.steamid64_from_account_id(num)
                else:
                    sys.exit(EXIT_FAILED_TO_PARSE_ID)
                    self.logger.log_error(f"Invalid numeric Steam ID range: {num}")
            except Exception as e:
                sys.exit(EXIT_FAILED_TO_PARSE_ID)
                self.logger.log_error(f"Failed to parse numeric ID ({identifier}): {e}")

        return (
            str(account_id) if account_id is not None else None,
            str(steam_id64) if steam_id64 is not None else None
        )

    def get_hwid(self):
        """Get Hardware ID that works on both Linux and Windows, with robust fallbacks."""
        system = platform.system()

        if system == "Windows":
            wmic_path = Path(r"C:\Windows\System32\wbem\wmic.exe")

            # Try WMIC if it exists
            if wmic_path.exists():
                try:
                    result = subprocess.check_output(
                        'wmic csproduct get UUID',
                        shell=True,
                        stderr=subprocess.DEVNULL,
                        text=True
                    )
                    lines = [line.strip() for line in result.split('\n') if line.strip()]
                    if len(lines) > 1 and lines[1]:
                        return lines[1]
                except Exception:
                    pass  # fallback to PowerShell if WMIC fails

            # Fallback: PowerShell
            try:
                result = subprocess.check_output(
                    'powershell -Command "Get-CimInstance Win32_ComputerSystemProduct | Select-Object -ExpandProperty UUID"',
                    shell=True,
                    stderr=subprocess.DEVNULL,
                    text=True
                ).strip()
                if result:
                    return result
            except Exception:
                pass

            self.logger.log_error("Failed to retrieve HWID on Windows.")
            sys.exit(EXIT_FAILED_TO_GET_HWID)

        elif system == "Linux":
            # Linux: Try machine-id first
            try:
                with open("/etc/machine-id", "r") as f:
                    machine_id = f.read().strip()
                    if machine_id:
                        return machine_id
            except Exception:
                pass
            self.logger.log_error("Failed to retrieve machine ID on Linux.")
            sys.exit(EXIT_FAILED_TO_GET_HWID)

        else:
            self.logger.log_error(f"Unsupported platform: {system}")
            sys.exit(EXIT_NOT_SUPPORTED)

    def derive_key(self):
        """Derive a Fernet key for encryption"""
        system_user = getpass.getuser()
        hwid = self.get_hwid()

        combined_secret = f"{system_user}:{hwid}"

        salt_prefix = b"steam_stats_salt_"
        salt = hashlib.sha256(salt_prefix + hwid.encode("utf-8")).digest()  # 32 bytes

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(combined_secret.encode("utf-8")))
        return key

    def encrypt_saved_logins(self, logins_dict):
        """Encrypt saved logins"""
        try:
            key = self.derive_key()
            fernet = Fernet(key)

            # Convert dict to JSON string and encrypt
            logins_json = json.dumps(logins_dict)
            encrypted_data = fernet.encrypt(logins_json.encode())

            return encrypted_data
        except Exception as e:
            self.logger.log_error(f"Error encrypting logins: {e}")
            return None

    def decrypt_saved_logins(self, encrypted_data):
        """Decrypt saved logins"""
        try:
            key = self.derive_key()
            fernet = Fernet(key)

            # Decrypt and parse JSON
            decrypted_data = fernet.decrypt(encrypted_data)
            logins_dict = json.loads(decrypted_data.decode())

            return logins_dict
        except Exception as e:
            self.logger.log_error(f"Error decrypting logins: {e}")
            return {}

    def migrate_old_tokens_to_new_format(self):
        """Migrate old token files to new saved_logins format"""
        old_files = [
            self.main.DATA_DIR / "refresh_tokens.encrypted",
            self.main.DATA_DIR / "refresh_tokens.json"
        ]

        migrated = False
        new_logins = {}

        for old_file in old_files:
            if old_file.exists():
                try:
                    if old_file.suffix == ".encrypted":
                        # Try to decrypt old format
                        with open(old_file, 'rb') as f:
                            encrypted_data = f.read()

                        # Use old derive_key function (same as before)
                        key = self.derive_key()
                        fernet = Fernet(key)
                        decrypted_data = fernet.decrypt(encrypted_data)
                        old_tokens = json.loads(decrypted_data.decode())

                        # Convert to new format
                        for username, refresh_token in old_tokens.items():
                            account_id, steam_id64 = self.parse_steam_id(username)
                            if account_id and steam_id64:
                                new_logins[steam_id64] = {
                                    "username": username,
                                    "refresh_token": refresh_token,
                                    "account_id": account_id,
                                    "steam_id64": steam_id64
                                }
                            else:
                                # If we can't parse as ID, keep as username
                                new_logins[username] = {
                                    "username": username,
                                    "refresh_token": refresh_token,
                                    "account_id": None,
                                    "steam_id64": None
                                }

                    elif old_file.suffix == ".json":
                        # Plaintext JSON
                        with open(old_file, 'r') as f:
                            old_tokens = json.load(f)

                        # Convert to new format
                        for username, refresh_token in old_tokens.items():
                            account_id, steam_id64 = self.parse_steam_id(username)
                            if account_id and steam_id64:
                                new_logins[steam_id64] = {
                                    "username": username,
                                    "refresh_token": refresh_token,
                                    "account_id": account_id,
                                    "steam_id64": steam_id64
                                }
                            else:
                                # If we can't parse as ID, keep as username
                                new_logins[username] = {
                                    "username": username,
                                    "refresh_token": refresh_token,
                                    "account_id": None,
                                    "steam_id64": None
                                }

                    # Delete old file after migration
                    old_file.unlink()
                    migrated = True
                    self.logger.log_info(f"Migrated {old_file} to new format")

                except Exception as e:
                    self.logger.log_error(f"Error migrating {old_file}: {e}")

        # Save migrated data
        if migrated and new_logins:
            if self.save_saved_logins(new_logins):
                self.logger.log_success("Successfully migrated old tokens to saved_logins.encrypted")
            else:
                self.logger.log_error("Failed to save migrated tokens")

        return migrated

    def load_saved_logins(self):
        """Load saved logins, handling migration from old format if needed"""
        # Check if migration is needed
        old_files_exist = any([
            (self.main.DATA_DIR / "refresh_tokens.encrypted").exists(),
            (self.main.DATA_DIR / "refresh_tokens.json").exists()
        ])

        if old_files_exist:
            self.migrate_old_tokens_to_new_format()

        # Load from new encrypted file
        if self.main.SAVED_LOGINS_FILE.exists():
            try:
                with open(self.main.SAVED_LOGINS_FILE, 'rb') as f:
                    encrypted_data = f.read()

                # Try to decrypt
                logins = self.decrypt_saved_logins(encrypted_data)
                if logins:
                    return logins
                else:
                    self.logger.log_error("Failed to decrypt logins with current system")
                    self.logger.log_error("This might happen if you changed hardware or system user")

            except Exception as e:
                self.logger.log_error(f"Error loading encrypted logins: {e}")

        return {}

    def save_saved_logins(self, logins_dict):
        """Save logins in encrypted format"""
        encrypted_data = self.encrypt_saved_logins(logins_dict)
        if encrypted_data:
            try:
                with open(self.main.SAVED_LOGINS_FILE, 'wb') as f:
                    f.write(encrypted_data)
                return True
            except Exception as e:
                self.logger.log_error(f"Error saving encrypted logins: {e}")
                sys.exit(EXIT_TOKEN_ERROR)
        return False

    def save_last_account(self, account_identifier):
        """Save the last used account identifier to a file"""
        try:
            with open(self.main.LAST_ACCOUNT_FILE, 'w') as f:
                f.write(account_identifier)
            return True
        except Exception as e:
            self.logger.log_error(f"Error saving last account: {e}")
            return False

    def load_last_account(self):
        """Load the last used account identifier from file"""
        try:
            if self.main.LAST_ACCOUNT_FILE.exists():
                with open(self.main.LAST_ACCOUNT_FILE, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            self.logger.log_error(f"Error loading last account: {e}")
        return None

    def get_account_id(self, client):
        """Get Steam Account ID directly from logged-in client"""
        if client and hasattr(client, 'steam_id') and client.steam_id:
            account_id = client.steam_id.account_id
            self.logger.log_success(f"Using Account ID from logged-in client: {account_id}")
            return str(account_id)

        self.logger.log_error("No logged-in client available for Account ID")
        return None

    def get_steam_id64(self, client):
        """Get Steam Steam ID64 directly from logged-in client"""
        if client and hasattr(client, 'steam_id') and client.steam_id:
            steam_id64 = client.steam_id.as_64
            self.logger.log_success(f"Using Steam ID64 from logged-in client: {steam_id64}")
            return str(steam_id64)

        self.logger.log_error("No logged-in client available for Steam ID64")
        return None

    def parse_loginusers_vdf(self):
        if not self.main.LOGIN_FILE or not self.main.LOGIN_FILE.exists():
            return {}

        with self.main.LOGIN_FILE.open("r", encoding="utf-8", errors="ignore") as f:
            data = vdf.load(f)

        # data["users"] is keyed by SteamID
        users = {
            steamid: {
                "AccountName": info.get("AccountName"),
                "PersonaName": info.get("PersonaName"),
                "MostRecent": info.get("MostRecent") == "1",
                "Timestamp": int(info.get("Timestamp", 0)),
            }
            for steamid, info in data.get("users", {}).items()
        }

        return users

class SteamUtils:
    """Class to handle Steam utility operations"""

    def __init__(self, main):
        self.main = main
        self.logger = main.logger
        self.steam_login = main.steam_login

    def determine_steam_directory(self):
        if platform.system() == "Windows":
            try:
                import winreg

                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
                winreg.CloseKey(key)
                self.logger.log_info(f"Found Steam installation at: {steam_path}")
                self.main.STEAM_DIR = Path(os.path.normpath(steam_path))
            except Exception:
                self.logger.log_error("Failed to read Steam path from registry.")
                sys.exit(EXIT_STEAM_NOT_FOUND)
        else:
            native_path = Path.home() / ".local/share/Steam"
            symlink_path = Path.home() / ".steam/steam"
            flatpak_path = Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam"

            if native_path.exists():
                self.main.STEAM_DIR = native_path
                self.logger.log_base(f"Using native Steam installation: {native_path}")

            elif symlink_path.exists():
                self.main.STEAM_DIR = symlink_path
                self.logger.log_base(f"Using symlink Steam installation: {symlink_path}")

            elif flatpak_path.exists():
                self.main.STEAM_DIR = flatpak_path
                self.logger.log_base(f"Using Flatpak Steam installation: {flatpak_path}")

            else:
                self.logger.log_error("No Steam installation found in ~/.local/share/Steam, ~/.steam/steam, ~/.var/app/com.valvesoftware.Steam/data/Steam")
                sys.exit(EXIT_STEAM_NOT_FOUND)

        if not self.main.STEAM_DIR.exists():
            self.logger.log_error(f"Steam directory does not exist at '{self.main.STEAM_DIR}'. Please report this issue")
            sys.exit(EXIT_STEAM_NOT_FOUND)

        # Set the dependent paths
        self.main.LIBRARY_FILE = self.main.STEAM_DIR / "config/libraryfolders.vdf"
        self.main.LOGIN_FILE = self.main.STEAM_DIR / "config/loginusers.vdf"
        self.main.DEST_DIR = self.main.STEAM_DIR / "appcache/stats"

    def parse_libraryfolders_vdf(self):
        """Parse libraryfolders.vdf to extract app IDs"""
        if not self.main.LIBRARY_FILE or not self.main.LIBRARY_FILE.exists():
            self.logger.log_error(f"Steam library file not found at {self.main.LIBRARY_FILE}")
            sys.exit(EXIT_STEAM_NOT_FOUND)

        self.logger.log_info(f"Reading Steam library from: {self.main.LIBRARY_FILE}")

        content = self.main.LIBRARY_FILE.read_text()
        # Extract all app IDs using regex
        app_ids = set(re.findall(r'"apps"\s*{([^}]+)}', content, re.DOTALL))
        app_ids = set(re.findall(r'"(\d+)"\s*"', ''.join(app_ids)))

        return sorted([int(app_id) for app_id in app_ids if app_id.isdigit()])

    def read_tracking_file(self, file_path):
        """Read tracking file and return set of app IDs"""
        if not file_path.exists():
            return set()
        return set(int(line.strip()) for line in file_path.read_text().splitlines() if line.strip().isdigit())

    def get_stats_schema(self, client, game_id, owner_id):
        """Request the stats schema for a game from a specific owner"""
        msg = MsgProto(EMsg.ClientGetUserStats)
        msg.body.game_id = game_id
        msg.body.schema_local_version = -1
        msg.body.crc_stats = 0
        msg.body.steam_id_for_user = owner_id

        client.send(msg)
        return client.wait_msg(EMsg.ClientGetUserStatsResponse, timeout=5)

    def check_single_owner(self, game_id, owner_id, client):
        """Return schema bytes or None"""
        try:
            out = self.get_stats_schema(client, game_id, owner_id)
            if out and hasattr(out.body, "schema") and out.body.schema:
                if len(out.body.schema) > 0:
                    return out.body.schema
            # Check for the specific "no schema" response pattern
            elif (out and hasattr(out.body, 'eresult') and out.body.eresult == 2 and
                  hasattr(out.body, 'crc_stats') and out.body.crc_stats == 0):
                return "NO_SCHEMA"  # Special indicator for no schema
        except Exception as e:
            self.logger.log_error(f"Exception for owner {owner_id}: {e}")
            traceback.print_exc(limit=1)
        return None

    def generate_stats_schema_bin(self, game_id, account_id, max_no_schema_in_row, client=None):
        """Generate stats and schema files with no-schema detection"""
        self.logger.log_info(f"Generating stats schema for game ID {game_id}")

        should_logout = False
        if not client:
            client, steam_id64, account_id = self.steam_login.login()
            if not client:
                self.logger.log_error("Aborting schema generation - not logged in")
                return False
            should_logout = True

        total_owners = len(self.main.TOP_OWNER_IDS)
        self.logger.log_info(f"Checking {total_owners} potential owners")

        stats_schema_found = None
        found_owner = None
        no_schema_count = 0

        spinner = itertools.cycle("|/-\\")
        for i, owner_id in enumerate(self.main.TOP_OWNER_IDS, start=1):
            sys.stdout.write(f"\r[{next(spinner)}] Checked {i-1}/{total_owners} owners... (no-schema streak: {no_schema_count}/{max_no_schema_in_row})")
            sys.stdout.flush()

            schema_data = self.check_single_owner(game_id, owner_id, client)

            if schema_data == "NO_SCHEMA":
                no_schema_count += 1
                # If we get too many "no schema" responses in a row, abort early
                if no_schema_count >= max_no_schema_in_row:
                    break
            elif schema_data and schema_data != "NO_SCHEMA":
                stats_schema_found = schema_data
                found_owner = owner_id
                sys.stdout.write(f"\r[OK] Found valid schema using owner {owner_id} ({i}/{total_owners})\n")
                sys.stdout.flush()
                break
            else:
                # Reset counter if we get a different type of response (error, timeout, etc.)
                no_schema_count = 0

            time.sleep(0.1)  # small delay to avoid hammering Steam's API

        if not stats_schema_found:
            if no_schema_count >= max_no_schema_in_row:
                sys.stdout.write(f"\r[XX] No schema available for game {game_id} ({max_no_schema_in_row} consecutive 'no schema' responses)\n")
                sys.stdout.flush()
                if self.main.SILENT_MODE and self.main.VERBOSE:
                    sys.exit(EXIT_NO_SCHEMA_FOUND)
            else:
                sys.stdout.write(f"\r[XX] No schema found for game {game_id} after checking {total_owners} owners\n")
                sys.stdout.flush()

            if should_logout:
                client.logout()
            return False

        try:
            schema_path = self.main.OUTPUT_DIR / f"UserGameStatsSchema_{game_id}.bin"
            with open(schema_path, "wb") as f:
                f.write(stats_schema_found)
            self.logger.log_success(f"Saved {schema_path} ({len(stats_schema_found)} bytes)")

            vdf_accounts = self.steam_login.parse_loginusers_vdf()
            for steamid in vdf_accounts:
                user_path = self.main.OUTPUT_DIR / f"UserGameStats_{self.steam_login.account_id_from_steamid64(int(steamid))}_{game_id}.bin"
                shutil.copyfile(self.main.TEMPLATE_FILE, user_path)
        except Exception as e:
            self.logger.log_error(f"Error writing schema files: {e}")
            if should_logout:
                client.logout()
            if self.main.SILENT_MODE:
                sys.exit(EXIT_FILE_ERROR)
            return False

        if should_logout:
            client.logout()

        self.logger.log_success(f"Finished schema generation for game {game_id} (owner {found_owner})")
        return True

    def ensure_directories(self):
        """Create necessary directories"""
        # Ensure Steam destination exists if set
        if self.main.DEST_DIR:
            self.main.DEST_DIR.mkdir(exist_ok=True, parents=True)

        self.main.DATA_DIR.mkdir(exist_ok=True, parents=True)
        self.main.OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

        # Ensure tracking files exist
        for file in [self.main.SKIP_FILE, self.main.NO_ACH_FILE, self.main.LAST_ACCOUNT_FILE]:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.touch(exist_ok=True)

    def get_maximum_tries(self):
        """Read maximum tries from file or create default file"""
        max_tries = self.main.DEFAULT_MAX_TRIES
        try:
            if self.main.MAX_TRIES_FILE.exists():
                with open(self.main.MAX_TRIES_FILE, 'r') as f:
                    content = f.read()

                    # Remove everything except digits
                    digits = ''.join(ch for ch in content if ch.isdigit())

                    if digits:
                        max_tries = int(digits)
                        self.logger.log_info(f"Using maximum tries from file: {max_tries}")
                    else:
                        self.logger.log_error(f"Invalid content in {self.main.MAX_TRIES_FILE}")
                        self.create_default_maximum_tries_files()
            else:
                self.create_default_maximum_tries_files()

        except Exception as e:
            self.logger.log_error(f"Error reading maximum_tries file: {e}, using default value: {max_tries}")

        return max_tries


    def create_default_maximum_tries_files(self):
        """Create the file with default value 5"""
        self.main.MAX_TRIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.main.MAX_TRIES_FILE, 'w') as f:
            f.write(f"{self.main.DEFAULT_MAX_TRIES}")
        self.logger.log_info(f"Created {self.main.MAX_TRIES_FILE} with default value: {self.main.DEFAULT_MAX_TRIES}")

    def copy_bins_to_steam_stats(self):
        """
        Copies all files from bins/* to the Steam appcache/stats directory
        for the given Steam ID64.
        """
        # Destination stats folder per user
        if self.main.DEST_DIR:
            self.main.DEST_DIR.mkdir(parents=True, exist_ok=True)

        if not self.main.OUTPUT_DIR.exists():
            self.logger.log_error(f"Source directory {self.main.OUTPUT_DIR} does not exist. Skipped copying")
            return

        files_copied = 0
        for file_path in self.main.OUTPUT_DIR.glob("*"):
            if not file_path.is_file():
                continue

            if files_copied == 0:
                self.logger.log_base("")

            dest_path = self.main.DEST_DIR / file_path.name if self.main.DEST_DIR else None

            # Schema files: always overwrite
            if file_path.name.startswith("UserGameStatsSchema_"):
                try:
                    if dest_path:
                        shutil.copy2(file_path, dest_path)
                        files_copied += 1
                        self.logger.log_success(f"Overwrote Schema File: {file_path} -> {dest_path}")
                    else:
                        self.logger.log_info(f"DEST_DIR not set, skipping copy of {file_path}")
                except Exception as e:
                    self.logger.log_error(f"Failed to copy schema {file_path} -> {dest_path}: {e}")
                    if self.main.SILENT_MODE:
                        sys.exit(EXIT_FILE_ERROR)

            # User stats files: only copy if not already present
            elif file_path.name.startswith("UserGameStats_"):
                if dest_path and dest_path.exists():
                    self.logger.log_warning(f"Stats file already exists: {dest_path}")
                    continue
                try:
                    if dest_path:
                        shutil.copy2(file_path, dest_path)
                        files_copied += 1
                        self.logger.log_success(f"Copied Stats File: {file_path} -> {dest_path}")
                    else:
                        self.logger.log_info(f"DEST_DIR not set, skipping copy of {file_path}")
                except Exception as e:
                    self.logger.log_error(f"Failed to copy stats {file_path} -> {dest_path}: {e}")
                    if self.main.SILENT_MODE:
                        sys.exit(EXIT_FILE_ERROR)

        if files_copied > 0:
            self.logger.log_success(f"Copied {files_copied} files to {self.main.DEST_DIR}")

    def prompt_security_warning(self):
        """Prompt user about security and ask if they want to delete the encrypted tokens"""
        if self.main.SILENT_MODE:
            return

        self.logger.log_base(f"\n{'='*80}")
        self.logger.log_base(f"SLScheevo Security Notice")
        self.logger.log_base(f"{'='*80}")
        self.logger.log_base(f"Your Steam login tokens have been saved in an encrypted file:")
        self.logger.log_base(f"{os.path.abspath(self.main.SAVED_LOGINS_FILE)}")
        self.logger.log_base(f"While encrypted, this file still contains sensitive information.")
        self.logger.log_base(f"If you don't plan to use SLScheevo for a while then please delete this file")
        self.logger.log_base(f"{'='*80}")

        try:
            self.logger.log_base("")
            response = self.logger.prompt("Do you want to delete the encrypted tokens file now? (y/n): ").strip().lower()
            self.logger.log_base("")
            if response in ['y', 'yes']:
                if self.main.SAVED_LOGINS_FILE.exists():
                    self.main.SAVED_LOGINS_FILE.unlink()
                    self.logger.log_success("Encrypted tokens file deleted.")
                else:
                    self.logger.log_warning("File already deleted or doesn't exist.")
            else:
                self.logger.log_warning("File kept. Remember to delete it manually if needed.")
        except (KeyboardInterrupt, EOFError):
            self.logger.log_base("\nFile kept. Remember to delete it manually if needed.")

    def parse_app_ids(self, appid_input):
        """Parse comma-separated app IDs string into list of integers"""
        if not appid_input:
            return []

        app_ids = []
        for part in appid_input.split(','):
            part = part.strip()
            if part.isdigit():
                app_ids.append(int(part))

        return app_ids

class Main:
    """Main class to hold the application state and coordinate operations"""

    def __init__(self):
        self.DEFAULT_MAX_TRIES = 3

        # Steam ids with public profiles that own a lot of games
        self.TOP_OWNER_IDS = [
            76561198028121353, 76561197979911851, 76561198017975643, 76561197993544755,
            76561198355953202, 76561198001237877, 76561198237402290, 76561198152618007,
            76561198355625888, 76561198213148949, 76561197969050296, 76561198217186687,
            76561198037867621, 76561198094227663, 76561198019712127, 76561197963550511,
            76561198134044398, 76561198001678750, 76561197973009892, 76561198044596404,
            76561197976597747, 76561197969810632, 76561198095049646, 76561198085065107,
            76561198864213876, 76561197962473290, 76561198388522904, 76561198033715344,
            76561197995070100, 76561198313790296, 76561198063574735, 76561197996432822,
            76561197976968076, 76561198281128349, 76561198154462478, 76561198027233260,
            76561198842864763, 76561198010615256, 76561198035900006, 76561198122859224,
            76561198235911884, 76561198027214426, 76561197970825215, 76561197968410781,
            76561198104323854, 76561198001221571, 76561198256917957, 76561198008181611,
            76561198407953371, 76561198062901118,
        ]

        self.STEAMID64_BASE = 76561197960265728  # Valve's base offset for public Steam64 IDs

        self.BASE_DIR = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
        self.DATA_DIR = self.BASE_DIR / "data"
        self.OUTPUT_DIR = self.DATA_DIR / "bins"
        self.SKIP_FILE = self.DATA_DIR / "skip_generation.txt"
        self.NO_ACH_FILE = self.DATA_DIR / "no_achievement_games.txt"
        self.MAX_TRIES_FILE = self.DATA_DIR / "maximum_tries.txt"
        self.SAVED_LOGINS_FILE = self.DATA_DIR / "saved_logins.encrypted"
        self.LAST_ACCOUNT_FILE = self.DATA_DIR / "last_account.txt"
        self.TEMPLATE_FILE = self.DATA_DIR / "UserGameStats_TEMPLATE.bin"
        self.LOG_FILE = self.DATA_DIR / "slscheevo.log"
        self.SILENT_MODE = False
        self.VERBOSE = False

        # Steam Path Vars
        self.STEAM_DIR = None
        self.LIBRARY_FILE = None
        self.LOGIN_FILE = None
        self.DEST_DIR = None

        # Initialize helper classes
        self.logger = Logger(self)
        self.steam_login = SteamLogin(self)
        self.steam_utils = SteamUtils(self)

    def run(self):
        """Main execution method"""
        parser = argparse.ArgumentParser(description='SLScheevo - Steam Stats Schema Generator')
        parser.add_argument('--login', type=str, help='Login using AccountID, SteamID, Steam2 ID, Steam3 ID, or username')
        parser.add_argument('--silent', action='store_true', help='Silent mode - no input prompts, exit with status codes')
        parser.add_argument('--verbose', action='store_true', help='Exits on non-critical statuses like no schemas for appid and such')
        parser.add_argument('--noclear', action='store_true', help='Don\'t clear console when starting, for developers')
        parser.add_argument('--appid', type=str, help='Comma-separated list of app IDs to generate schemas for')
        parser.add_argument('--save-dir', type=str, help='Base directory to save data and outputs (overrides default script-based base dir)')
        parser.add_argument('--max-tries', type=int, help='Maximum number of consecutive "no schema" responses before giving up')
        parser.add_argument('--infinite-retry', action='store_true', help='Retry login attempts infinitely when encountering network errors')

        args = parser.parse_args()

        self.SILENT_MODE = args.silent
        self.VERBOSE = args.verbose
        self.INFINITE_RETRY = args.infinite_retry

        # If user specified a save directory, update BASE_DIR and all dependent paths
        if args.save_dir:
            requested = Path(args.save_dir).expanduser().resolve()
            if not requested.exists():
                try:
                    requested.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self.logger.log_error(f"Could not create save-dir '{requested}': {e}")
                    sys.exit(EXIT_FILE_ERROR)
            self.BASE_DIR = requested
            self.DATA_DIR = self.BASE_DIR / "data"
            self.OUTPUT_DIR = self.DATA_DIR / "bins"
            self.SKIP_FILE = self.DATA_DIR / "skip_generation.txt"
            self.NO_ACH_FILE = self.DATA_DIR / "no_achievement_games.txt"
            self.MAX_TRIES_FILE = self.DATA_DIR / "maximum_tries.txt"
            self.SAVED_LOGINS_FILE = self.DATA_DIR / "saved_logins.encrypted"
            self.LAST_ACCOUNT_FILE = self.DATA_DIR / "last_account.txt"
            self.TEMPLATE_FILE = self.DATA_DIR / "UserGameStats_TEMPLATE.bin"
            self.LOG_FILE = self.DATA_DIR / "slscheevo.log"

        # Setup logging after paths are configured
        self.logger.setup_logging()
        self.logger.install_global_exception_logger()

        # Clear screen based on platform
        if not args.noclear and platform.system() == "Windows":
            os.system('cls')
        elif not args.noclear:
            os.system('clear')

        self.steam_utils.determine_steam_directory()
        self.steam_utils.ensure_directories()
        if args.max_tries is not None:
            max_no_schema_in_row = args.max_tries
            self.logger.log_info(f"Using command line max tries: {max_no_schema_in_row}")
        else:
            max_no_schema_in_row = self.steam_utils.get_maximum_tries()

        # Login first to get client
        if args.login:
            client, steam_id64, account_id = self.steam_login.login(args.login)
        else:
            client, steam_id64, account_id = self.steam_login.login()

        if not client:
            self.logger.log_error("Failed to login to Steam")
            sys.exit(EXIT_LOGIN_FAILED)

        if not account_id:
            self.logger.log_error("Could not retrieve account ID")
            client.logout()
            sys.exit(EXIT_NO_ACCOUNT_ID)

        if not steam_id64:
            self.logger.log_error("Could not retrieve Steam ID64")
            client.logout()
            sys.exit(EXIT_NO_ACCOUNT_ID)

        self.logger.log_info(f"Parsed Account ID: {account_id}")
        self.logger.log_info(f"Parsed Steam ID64: {steam_id64}")

        # Parse app IDs from command line or library
        if args.appid:
            app_ids = self.steam_utils.parse_app_ids(args.appid)
            if not app_ids:
                self.logger.log_error("No valid app IDs provided with --appid")
                client.logout()
                sys.exit(EXIT_NO_APP_IDS)
            self.logger.log_info(f"Using {len(app_ids)} app IDs from command line: {app_ids}")
        else:
            # Parse Steam library
            app_ids = self.steam_utils.parse_libraryfolders_vdf()
            if not app_ids:
                self.logger.log_error("No app IDs found in library file.")
                client.logout()
                sys.exit(EXIT_NO_APP_IDS)
            self.logger.log_success(f"Found {len(app_ids)} games in library")

        # Read tracking files
        skip_generation = self.steam_utils.read_tracking_file(self.SKIP_FILE)
        no_achievements = self.steam_utils.read_tracking_file(self.NO_ACH_FILE)

        # Find missing app IDs
        missing_app_ids = []
        for app_id in app_ids:
            if app_id in no_achievements:
                continue  # doesn't have achievements
            if app_id in skip_generation:
                continue  # explicitly skipped

            # Check if schema file already exists in backup or destination
            vdf_accounts = self.steam_login.parse_loginusers_vdf()
            for steamid in vdf_accounts:
                schema_file = f"UserGameStats_{self.steam_login.account_id_from_steamid64(int(steamid))}_{app_id}.bin"
                if (self.OUTPUT_DIR / schema_file).exists() or (self.DEST_DIR and (self.DEST_DIR / schema_file).exists()):
                    continue

                missing_app_ids.append(app_id)

        if not missing_app_ids:
            self.logger.log_info("No missing stats files to generate")
            client.logout()
            self.steam_utils.copy_bins_to_steam_stats()
            self.steam_utils.prompt_security_warning()
            sys.exit(EXIT_NO_ACTIONS)

        self.logger.log_info(f"Generating stats for {len(missing_app_ids)} missing games")

        # Generate missing stats
        success_count = 0
        failed_count = 0

        for i, app_id in enumerate(missing_app_ids, 1):
            self.logger.log_base("")
            self.logger.log_info(f"Progress: {i}/{len(missing_app_ids)}")

            if self.steam_utils.generate_stats_schema_bin(app_id, account_id, max_no_schema_in_row, client):
                success_count += 1
            else:
                failed_count += 1

        self.logger.log_base("")
        self.logger.log_success(f"Generation complete: {success_count} succeeded, {failed_count} failed")

        client.logout()

        # Copy generated files to Steam directory
        self.steam_utils.copy_bins_to_steam_stats()

        self.steam_utils.prompt_security_warning()

        sys.exit(EXIT_SUCCESS)

def main():
    """Main function to create and run the application"""
    app = Main()
    app.run()

if __name__ == "__main__":
    main()
