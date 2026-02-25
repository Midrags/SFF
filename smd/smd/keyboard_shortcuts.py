"""Keyboard Shortcuts Handler for SMD"""

import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Check if we're on Windows for keyboard handling
if sys.platform == "win32":
    try:
        import msvcrt
        KEYBOARD_AVAILABLE = True
    except ImportError:
        KEYBOARD_AVAILABLE = False
        logger.warning("msvcrt not available. Keyboard shortcuts disabled.")
else:
    KEYBOARD_AVAILABLE = False


class KeyboardHandler:
    """Handles keyboard shortcuts for menu navigation"""
    
    @staticmethod
    def check_for_keypress() -> Optional[str]:
        """
        Check if a key has been pressed (non-blocking)
        
        Returns:
            Key character if pressed, None otherwise
        """
        if not KEYBOARD_AVAILABLE:
            return None
        
        try:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                # Handle special keys
                if key == b'\x1b':  # ESC
                    return 'ESC'
                elif key == b'\x03':  # Ctrl+C
                    return 'CTRL_C'
                elif key in [b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']:
                    return key.decode('utf-8')
                return key.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Error checking keypress: {e}")
        
        return None
    
    @staticmethod
    def wait_for_key() -> str:
        """
        Wait for a key press (blocking)
        
        Returns:
            Key character
        """
        if not KEYBOARD_AVAILABLE:
            return input()
        
        try:
            key = msvcrt.getch()
            if key == b'\x1b':  # ESC
                return 'ESC'
            elif key == b'\x03':  # Ctrl+C
                return 'CTRL_C'
            elif key == b'\r':  # Enter
                return 'ENTER'
            return key.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Error waiting for key: {e}")
            return ''
    
    @staticmethod
    def is_number_key(key: str) -> bool:
        """
        Check if key is a number (1-9)
        
        Args:
            key: Key character
            
        Returns:
            True if number key
        """
        return key in ['1', '2', '3', '4', '5', '6', '7', '8', '9']
    
    @staticmethod
    def get_number_from_key(key: str) -> Optional[int]:
        """
        Convert key to number
        
        Args:
            key: Key character
            
        Returns:
            Number (1-9) or None
        """
        if KeyboardHandler.is_number_key(key):
            return int(key)
        return None


def format_menu_with_shortcuts(items: list, start_index: int = 1) -> str:
    """
    Format menu items with keyboard shortcuts
    
    Args:
        items: List of menu items
        start_index: Starting index for numbering
        
    Returns:
        Formatted menu string
    """
    lines = []
    for i, item in enumerate(items, start=start_index):
        if i <= 9:
            lines.append(f"[{i}] {item}")
        else:
            lines.append(f"    {item}")
    return "\n".join(lines)
