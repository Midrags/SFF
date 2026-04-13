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

LIGHT_STYLE = """
QMainWindow, QWidget { background-color: #fafafa; color: #111; }
QGroupBox {
    font-weight: bold;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    color: #111;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #111; }
QPushButton {
    background-color: #fff;
    border: 1px solid #ccc;
    border-radius: 3px;
    padding: 6px 12px;
    min-width: 80px;
    color: #111;
}
QPushButton:hover { background-color: #f0f0f0; color: #111; }
QPushButton:pressed { background-color: #e0e0e0; color: #111; }
QPushButton:disabled { background-color: #f5f5f5; color: #666; }
QLineEdit, QComboBox {
    background-color: #fff;
    border: 1px solid #ccc;
    border-radius: 3px;
    padding: 4px;
    min-height: 20px;
    color: #111;
}
QComboBox::drop-down { border: none; width: 24px; min-width: 24px; }
QComboBox QAbstractItemView { background-color: #fff; color: #111; }
QTextEdit, QPlainTextEdit {
    background-color: #fff;
    border: 1px solid #ccc;
    border-radius: 3px;
    font-family: Consolas, monospace;
    font-size: 12px;
    color: #111;
}
QMenuBar { background-color: #f5f5f5; color: #111; }
QMenuBar::item:selected { background-color: #e8e8e8; color: #111; }
QMenu { background-color: #fff; color: #111; }
QMenu::item:selected { background-color: #e8e8e8; color: #111; }
QRadioButton { color: #111; }
QRadioButton::indicator { width: 14px; height: 14px; }
QRadioButton::indicator:unchecked {
    border: 2px solid #888;
    border-radius: 7px;
    background-color: transparent;
}
QRadioButton::indicator:checked {
    border: 2px solid #333;
    border-radius: 7px;
    background-color: #333;
}
QLabel { color: #111; }
QDialog { background-color: #fafafa; color: #111; }
"""

DARK_STYLE = """
QMainWindow, QWidget { background-color: #2d2d2d; color: #e8e8e8; }
QGroupBox {
    font-weight: bold;
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    color: #e8e8e8;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #e8e8e8; }
QPushButton {
    background-color: #404040;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 6px 12px;
    min-width: 80px;
    color: #e8e8e8;
}
QPushButton:hover { background-color: #505050; color: #fff; }
QPushButton:pressed { background-color: #303030; color: #fff; }
QPushButton:disabled { background-color: #353535; color: #888; }
QLineEdit, QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 4px;
    min-height: 20px;
    color: #e8e8e8;
}
QComboBox::drop-down { border: none; width: 24px; min-width: 24px; }
QComboBox QAbstractItemView { background-color: #3c3c3c; color: #e8e8e8; }
QTextEdit, QPlainTextEdit {
    background-color: #1e1e1e;
    border: 1px solid #555;
    border-radius: 3px;
    font-family: Consolas, monospace;
    font-size: 12px;
    color: #e8e8e8;
}
QMenuBar { background-color: #353535; color: #e8e8e8; }
QMenuBar::item:selected { background-color: #505050; color: #fff; }
QMenu { background-color: #2d2d2d; color: #e8e8e8; }
QMenu::item:selected { background-color: #505050; color: #fff; }
QRadioButton { color: #e8e8e8; }
QRadioButton::indicator { width: 14px; height: 14px; }
QRadioButton::indicator:unchecked {
    border: 2px solid #666;
    border-radius: 7px;
    background-color: transparent;
}
QRadioButton::indicator:checked {
    border: 2px solid #ddd;
    border-radius: 7px;
    background-color: #ddd;
}
QLabel { color: #e8e8e8; }
QDialog { background-color: #2d2d2d; color: #e8e8e8; }
"""

def _gen_dark_variant(bg, fg, accent, btn_bg, btn_hover, input_bg, border):
    """generate a theme variant from core colors — saves a ton of repetition"""
    return f"""
QMainWindow, QWidget {{ background-color: {bg}; color: {fg}; }}
QGroupBox {{
    font-weight: bold; border: 1px solid {border}; border-radius: 4px;
    margin-top: 8px; padding-top: 8px; color: {fg};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {fg}; }}
QPushButton {{
    background-color: {btn_bg}; border: 1px solid {border}; border-radius: 3px;
    padding: 6px 12px; min-width: 80px; color: {fg};
}}
QPushButton:hover {{ background-color: {btn_hover}; color: #fff; }}
QPushButton:pressed {{ background-color: {accent}; color: #fff; }}
QPushButton:disabled {{ background-color: {bg}; color: {border}; }}
QLineEdit, QComboBox {{
    background-color: {input_bg}; border: 1px solid {border}; border-radius: 3px;
    padding: 4px; min-height: 20px; color: {fg};
}}
QComboBox::drop-down {{ border: none; width: 24px; min-width: 24px; }}
QComboBox QAbstractItemView {{ background-color: {input_bg}; color: {fg}; }}
QTextEdit, QPlainTextEdit {{
    background-color: {input_bg}; border: 1px solid {border}; border-radius: 3px;
    font-family: Consolas, monospace; font-size: 12px; color: {fg};
}}
QMenuBar {{ background-color: {btn_bg}; color: {fg}; }}
QMenuBar::item:selected {{ background-color: {btn_hover}; color: #fff; }}
QMenu {{ background-color: {bg}; color: {fg}; }}
QMenu::item:selected {{ background-color: {btn_hover}; color: #fff; }}
QRadioButton {{ color: {fg}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; }}
QRadioButton::indicator:unchecked {{ border: 2px solid {border}; border-radius: 7px; background-color: transparent; }}
QRadioButton::indicator:checked {{ border: 2px solid {accent}; border-radius: 7px; background-color: {accent}; }}
QLabel {{ color: {fg}; }}
QDialog {{ background-color: {bg}; color: {fg}; }}
QTabWidget::pane {{ border: 1px solid {border}; background-color: {bg}; }}
QTabBar::tab {{
    background-color: {btn_bg}; color: {fg}; padding: 8px 16px;
    border: 1px solid {border}; border-bottom: none; border-radius: 3px 3px 0 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background-color: {bg}; color: {accent}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover {{ background-color: {btn_hover}; }}
QProgressBar {{
    border: 1px solid {border}; border-radius: 3px;
    background-color: {input_bg}; text-align: center; color: {fg};
}}
QProgressBar::chunk {{ background-color: {accent}; border-radius: 2px; }}
QTableView {{ background-color: {input_bg}; color: {fg}; gridline-color: {border}; }}
QHeaderView::section {{ background-color: {btn_bg}; color: {fg}; padding: 4px; border: 1px solid {border}; }}
"""


CHERRY_STYLE = _gen_dark_variant(
    bg="#1a0a0e", fg="#f0d0d8", accent="#c0392b", btn_bg="#2d1118",
    btn_hover="#4a1a24", input_bg="#1f0c12", border="#5a2030"
)

SUNSET_STYLE = _gen_dark_variant(
    bg="#1a1008", fg="#f0dcc0", accent="#e67e22", btn_bg="#2d1c10",
    btn_hover="#4a2e18", input_bg="#1f120a", border="#5a3820"
)

FOREST_STYLE = _gen_dark_variant(
    bg="#0a1a0e", fg="#d0f0d8", accent="#27ae60", btn_bg="#102d18",
    btn_hover="#184a24", input_bg="#0c1f12", border="#205a30"
)

GRAPE_STYLE = _gen_dark_variant(
    bg="#140a1a", fg="#dcc0f0", accent="#8e44ad", btn_bg="#1c102d",
    btn_hover="#2e184a", input_bg="#120a1f", border="#38205a"
)

CYBERPUNK_STYLE = _gen_dark_variant(
    bg="#0a0a1a", fg="#00ffcc", accent="#ff006a", btn_bg="#10102d",
    btn_hover="#18184a", input_bg="#0a0a1f", border="#20205a"
)

PINK_STYLE = _gen_dark_variant(
    bg="#1a0a18", fg="#f0c0e8", accent="#e84393", btn_bg="#2d101c",
    btn_hover="#4a1830", input_bg="#1f0c1a", border="#5a2050"
)

NORD_STYLE = _gen_dark_variant(
    bg="#2e3440", fg="#d8dee9", accent="#88c0d0", btn_bg="#3b4252",
    btn_hover="#434c5e", input_bg="#2e3440", border="#4c566a"
)

DRACULA_STYLE = _gen_dark_variant(
    bg="#282a36", fg="#f8f8f2", accent="#bd93f9", btn_bg="#44475a",
    btn_hover="#6272a4", input_bg="#282a36", border="#44475a"
)

PASTEL_STYLE = _gen_dark_variant(
    bg="#faf0e6", fg="#333333", accent="#e6a07c", btn_bg="#f0e0d0",
    btn_hover="#e8d0bc", input_bg="#fff8f0", border="#d4b8a0"
)

THEMES = {
    "light": ("Light", LIGHT_STYLE),
    "dark": ("Dark", DARK_STYLE),
    "cherry": ("Cherry", CHERRY_STYLE),
    "sunset": ("Sunset", SUNSET_STYLE),
    "forest": ("Forest", FOREST_STYLE),
    "grape": ("Grape", GRAPE_STYLE),
    "cyberpunk": ("Cyberpunk", CYBERPUNK_STYLE),
    "pink": ("Pink", PINK_STYLE),
    "nord": ("Nord", NORD_STYLE),
    "dracula": ("Dracula", DRACULA_STYLE),
    "pastel": ("Pastel", PASTEL_STYLE),
}
