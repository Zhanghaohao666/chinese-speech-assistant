"""Kinetic: dark surfaces, warm accents and stable reading contrast."""
from pathlib import Path
COLORS = {
    'primary': '#FF6863', 'focus': '#FFAE58', 'link_dark': '#FF8C00',
    'red': '#FF4D4D', 'orange': '#FF8C00', 'on_accent': '#0F0F14',
    'ink': '#F2F0ED', 'secondary': '#E0E0E0', 'muted': '#AAA6AE',
    'disabled': '#77737E', 'white': '#19191F', 'canvas': '#0F0F14',
    'pearl': '#202026', 'divider': '#292830', 'hairline': '#3A3741',
    'dark': '#151419', 'dark_control': '#28252D', 'dark_muted': '#C6C0C9',
    'chip': '#504952', 'selection': '#352225', 'error': '#FF9992',
}

_QSS = '''
QWidget { color: @ink; font-family: "Microsoft YaHei UI", "Segoe UI", "Microsoft YaHei"; font-size: 15px; }
QMainWindow, QWidget#root, QStackedWidget { background: @canvas; }
QFrame#sidebar { background: #121116; border-right: 1px solid @hairline; }
QFrame#card, QFrame#transcript { background: @white; border: 1px solid @hairline; border-radius: 10px; }
QFrame#transcript[dropActive="true"] { background: @selection; border: 2px dashed @primary; }
QLabel { background: transparent; }
QLabel#brand { font-size: 27px; font-weight: 800; }
QLabel#title { font-size: 36px; font-weight: 800; }
QLabel#heading { font-size: 19px; font-weight: 700; }
QLabel#muted { color: @muted; font-size: 13px; }
QLabel#eyebrow { color: @primary; font-size: 12px; font-weight: 700; }
QLabel#badge { background: @divider; color: @secondary; padding: 5px 12px; border-radius: 4px; font-size: 12px; }
QLabel#badge[state="done"], QLabel#badge[state="busy"] { background: @selection; color: @focus; border-left: 3px solid @red; }
QLabel#badge[state="failed"] { color: @error; }
QPushButton { background: @white; color: @secondary; border: 1px solid @hairline; border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @pearl; border-color: @primary; }
QPushButton:pressed { background: @selection; }
QPushButton:focus { border: 1px solid @focus; }
QPushButton:disabled { color: @disabled; background: @divider; border-color: @divider; }
QPushButton#primary, QPushButton#exportPrimary { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @red,stop:1 @orange); color: @on_accent; border-color: @red; font-weight: 700; }
QPushButton#primary:hover, QPushButton#exportPrimary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @primary,stop:1 @focus); }
QPushButton#primary:pressed, QPushButton#exportPrimary:pressed { background: @red; }
QPushButton#primary:disabled, QPushButton#exportPrimary:disabled { background: @chip; border-color: @chip; color: @disabled; }
QPushButton::menu-indicator { image: none; width: 0; }
QPushButton#nav { text-align: left; color: @muted; background: transparent; border: 1px solid transparent; border-left: 3px solid transparent; border-radius: 6px; padding: 13px 16px; }
QPushButton#nav:hover { background: @divider; }
QPushButton#nav:checked { color: @ink; background: @selection; border-left-color: @red; }
QPushButton#subtle { background: transparent; color: @primary; border: none; padding: 6px 8px; }
QPushButton#subtle:hover { background: @divider; }
QPushButton#subtle:disabled { color: @disabled; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: @canvas; border: 1px solid @hairline; border-radius: 8px; padding: 9px 12px; selection-background-color: @selection; selection-color: @ink; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: @focus; }
QLineEdit#search { border-radius: 8px; background: @canvas; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(@down_icon); width: 14px; height: 14px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border: none; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border: none; }
QSpinBox::up-arrow { image: url(@up_icon); width: 12px; height: 12px; }
QSpinBox::down-arrow { image: url(@down_icon); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @white; color: @ink; selection-background-color: @selection; }
QTableWidget { background: @white; border: none; outline: none; selection-background-color: @selection; selection-color: @ink; }
QTableWidget::item { border: none; padding: 0; }
QHeaderView::section { background: @white; color: @muted; border: none; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { background: @white; border: 1px solid @hairline; border-radius: 8px; margin-bottom: 12px; padding: 20px; }
QListWidget::item:selected { background: @selection; border-color: @primary; }
QListWidget::item:hover { border-color: @primary; }
QProgressBar { background: @hairline; border: none; border-radius: 2px; max-height: 3px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @red,stop:1 @orange); border-radius: 2px; }
QSlider::groove:horizontal { background: @hairline; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @primary; border-radius: 2px; }
QSlider::handle:horizontal { background: @primary; width: 12px; margin: -4px 0; border-radius: 6px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid @chip; border-radius: 5px; background: @white; }
QCheckBox::indicator:checked { background: @orange; border: 3px solid @orange; image: url(@check_icon); }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: @chip; min-height: 32px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu, QDialog, QMessageBox, QFileDialog { background: @white; }
QMenu { border: 1px solid @hairline; padding: 6px; }
QMenu::item { padding: 10px 24px; border-radius: 8px; }
QMenu::item:selected { background: @selection; }
QToolTip { color: @ink; background: @white; border: 1px solid @hairline; padding: 6px; }
QFrame#player { background: @dark; border: 1px solid @hairline; border-top: 2px solid @red; border-radius: 10px; }
QFrame#player QLabel { color: @dark_muted; }
QFrame#player QPushButton { color: @ink; background: @dark_control; border-color: @dark_control; }
QFrame#player QPushButton#primary { color: @on_accent; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @red,stop:1 @orange); border-color: @red; }
QFrame#player QPushButton:disabled, QFrame#player QPushButton#primary:disabled { color: @disabled; background: @dark_control; border-color: @dark_control; }
QFrame#player QComboBox { color: @ink; background: @dark_control; border-color: @dark_control; }
QFrame#player QSlider::groove:horizontal { background: @disabled; }
QFrame#player QSlider::sub-page:horizontal, QFrame#player QSlider::handle:horizontal { background: @link_dark; }
'''
STYLE = _QSS
for name in ('check', 'down', 'up'):
    STYLE = STYLE.replace('@'+name+'_icon', (Path(__file__).parent/'assets'/f'{name}.svg').as_posix())
for key in sorted(COLORS, key=len, reverse=True):
    STYLE = STYLE.replace('@'+key, COLORS[key])
