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
QComboBox::drop-down { border: none; }
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
QComboBox::drop-down { border: none; }
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
QLabel { color: #e8e8e8; }
QDialog { background-color: #2d2d2d; color: #e8e8e8; }
"""

THEMES = {
    "light": ("Light", LIGHT_STYLE),
    "dark": ("Dark", DARK_STYLE),
}
