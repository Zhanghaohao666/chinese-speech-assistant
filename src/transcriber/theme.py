"""Maximalism: saturated paper layers with a quiet, high-contrast reading surface."""
from pathlib import Path
COLORS = {
    'primary': '#006B65', 'focus': '#6B3BC4', 'link_dark': '#006B65',
    'red': '#FF6B6B', 'orange': '#FFE66D', 'on_accent': '#20202A',
    'ink': '#20202A', 'secondary': '#30303C', 'muted': '#5A5468',
    'disabled': '#716A78', 'white': '#FFFFFF', 'canvas': '#FFF9EC',
    'pearl': '#FFF4D6', 'divider': '#DED6C7', 'hairline': '#20202A',
    'dark': '#E7DDFC', 'dark_control': '#FFFFFF', 'dark_muted': '#494052',
    'chip': '#D4C8E5', 'selection': '#D9F8EF', 'error': '#A42B35',
    'cyan': '#4ECDC4', 'purple': '#A78BFA', 'yellow': '#FFE66D',
    'blue': '#378FFF', 'sidebar': '#EFE5FF',
}

_QSS = '''
QWidget { color: @ink; font-family: "Microsoft YaHei UI", "Segoe UI", "Microsoft YaHei"; font-size: 15px; }
QMainWindow { background: @canvas; }
QWidget#root, QStackedWidget { background: transparent; }
QFrame#sidebar { background: @sidebar; border-right: 3px solid @hairline; border-top: 8px solid @cyan; }
QFrame#card, QFrame#transcript { background: transparent; border: none; }
QFrame#transcript[dropActive="true"] { background: @selection; border: 2px dashed @primary; }
QLabel { background: transparent; }
QLabel#brand { font-size: 27px; font-weight: 800; }
QLabel#title { font-size: 34px; font-weight: 900; }
QLabel#heading { font-size: 19px; font-weight: 700; }
QLabel#muted { color: @muted; font-size: 13px; }
QLabel#eyebrow { color: @ink; background: @yellow; border: 2px solid @hairline; border-radius: 5px; padding: 4px 9px; font-size: 12px; font-weight: 700; }
QLabel#badge { background: @yellow; color: @ink; border: 1px solid @hairline; padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
QLabel#badge[state="done"] { background: @cyan; color: @ink; }
QLabel#badge[state="busy"] { background: @yellow; color: @ink; }
QLabel#badge[state="failed"] { background: #FFE0E0; color: @error; }
QPushButton { background: @white; color: @secondary; border: 2px solid @hairline; border-bottom-width: 4px; border-radius: 9px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background: @pearl; border-color: @hairline; }
QPushButton:pressed { background: @selection; }
QPushButton:focus { border: 1px solid @focus; }
QPushButton:disabled { color: @disabled; background: @divider; border-color: @divider; }
QPushButton#primary { background: @cyan; color: @on_accent; border-color: @hairline; font-weight: 700; }
QPushButton#exportPrimary { background: @yellow; color: @on_accent; border-color: @hairline; font-weight: 700; }
QPushButton#primary:hover, QPushButton#exportPrimary:hover { background: @purple; }
QPushButton#primary:pressed, QPushButton#exportPrimary:pressed { background: @red; }
QPushButton#primary:disabled, QPushButton#exportPrimary:disabled { background: @chip; border-color: @chip; color: @disabled; }
QPushButton::menu-indicator { image: none; width: 0; }
QPushButton#nav { text-align: left; color: @ink; background: @white; border: 2px solid @hairline; border-bottom-width: 4px; border-radius: 9px; padding: 12px 14px; }
QPushButton#nav[accent="pink"] { background: #FFD6D9; }
QPushButton#nav[accent="cyan"] { background: #C8F4ED; }
QPushButton#nav[accent="purple"] { background: #DBC9FF; }
QPushButton#nav[accent="yellow"] { background: #FFF2B1; }
QPushButton#nav:hover { background: @white; }
QPushButton#nav:checked { color: @ink; background: @yellow; border-left: 6px solid @hairline; }
QPushButton#subtle { background: transparent; color: @primary; border: none; padding: 6px 8px; }
QPushButton#subtle:hover { background: @divider; }
QPushButton#subtle:disabled { color: @disabled; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: @white; border: 2px solid @hairline; border-radius: 8px; padding: 8px 10px; selection-background-color: @selection; selection-color: @ink; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: @focus; }
QLineEdit#search { border-radius: 8px; background: @canvas; min-width: 110px; }
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
QListWidget::item { background: @white; border: 2px solid @hairline; border-bottom-width: 5px; border-radius: 12px; margin-bottom: 12px; padding: 20px; }
QListWidget::item:selected { background: @selection; border-color: @primary; }
QListWidget::item:hover { border-color: @primary; }
QProgressBar { background: @divider; border: none; border-radius: 3px; max-height: 5px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @red,stop:0.33 @yellow,stop:0.66 @cyan,stop:1 @purple); border-radius: 3px; }
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
QFrame#player { background: @dark; border: 2px solid @hairline; border-bottom-width: 5px; border-radius: 14px; }
QFrame#player QLabel { color: @dark_muted; }
QFrame#player QPushButton { color: @ink; background: @dark_control; border-color: @hairline; }
QFrame#player QPushButton#primary { color: @on_accent; background: @cyan; border-color: @hairline; }
QFrame#player QPushButton:disabled, QFrame#player QPushButton#primary:disabled { color: @disabled; background: @dark_control; border-color: @dark_control; }
QFrame#player QComboBox { color: @ink; background: @dark_control; border-color: @hairline; }
QFrame#player QSlider::groove:horizontal { background: @disabled; }
QFrame#player QSlider::sub-page:horizontal, QFrame#player QSlider::handle:horizontal { background: @link_dark; }
'''
STYLE = _QSS
for name in ('check', 'down', 'up'):
    STYLE = STYLE.replace('@'+name+'_icon', (Path(__file__).parent/'assets'/f'{name}.svg').as_posix())
for key in sorted(COLORS, key=len, reverse=True):
    STYLE = STYLE.replace('@'+key, COLORS[key])
