"""统一的浅色科研界面主题；只改变外观，不改变任何分析行为。"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

ACCENT = "#1E40AF"
AMBER = "#D97706"
APP_QSS = """
QMainWindow { background: #F8FAFC; }
QWidget { color: #1E293B; font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"; font-size: 10pt; }
QWidget#contentHost { background: #F8FAFC; }
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #14243D, stop:1 #0B1524);
    border: none;
}
QLabel#brandTitle { color: #F8FAFC; font-size: 15pt; font-weight: bold; padding: 0; }
QLabel#brandSub { color: #8FA5C2; font-size: 8pt; }
QLabel#brandBadge {
    color: #BFDBFE; background: #1E3A5F; border-radius: 8px;
    padding: 2px 8px; font-size: 8pt;
}
QLabel#sideFooter { color: #7C8DA6; font-size: 8pt; padding: 10px 6px; }
QLabel#sideSection { color: #7C8DA6; font-size: 8pt; font-weight: bold; padding: 12px 12px 2px 12px; }
QLabel#pageTitle { color: #0F172A; font-size: 15pt; font-weight: bold; padding: 0 0 2px 0; }
QLabel#pageSubtitle { color: #64748B; font-size: 9pt; }
QLabel#heroTitle { color: #0F172A; font-size: 24pt; font-weight: bold; }
QLabel#heroSubtitle { color: #52637A; font-size: 10.5pt; line-height: 1.5; }
QLabel#sectionTitle { color: #0F172A; font-size: 11pt; font-weight: bold; padding-top: 6px; }

QListWidget#nav {
    background: transparent; border: none; outline: 0;
    color: #C7D2E3; font-size: 10.5pt;
}
QListWidget#nav::item {
    height: 40px; padding-left: 14px; margin: 2px 10px;
    border-radius: 8px; border: none;
}
QListWidget#nav::item:hover { background: #1B2C48; color: #F8FAFC; }
QListWidget#nav::item:selected { background: #1E40AF; color: #FFFFFF; }
QListWidget#nav:focus { border: none; outline: none; }

QPushButton {
    background: #FFFFFF; color: #1E293B;
    border: 1px solid #D6DFEA; border-radius: 8px;
    padding: 6px 14px; min-height: 16px;
}
QPushButton:hover { background: #F8FAFF; border-color: #93A9C4; }
QPushButton:pressed { background: #E8EEF7; }
QPushButton:disabled { color: #94A3B8; background: #F1F5F9; border-color: #E2E8F0; }
QPushButton#primaryButton {
    background: #1E40AF; color: #FFFFFF; border: 1px solid #1E40AF; font-weight: bold;
}
QPushButton#primaryButton:hover { background: #1E3A8A; border-color: #1E3A8A; }
QPushButton#primaryButton:pressed { background: #172554; }
QPushButton#primaryButton:disabled { background: #E2E8F0; border-color: #CBD5E1; color: #94A3B8; }
QPushButton#ghostButton { background: transparent; border: 1px solid #CBD5E1; color: #334155; }
QPushButton#ghostButton:hover { background: #EEF4FC; border-color: #94A3B8; }
QPushButton:focus { border: 2px solid #1E40AF; padding: 5px 13px; }
QPushButton#primaryButton:focus { border: 2px solid #93C5FD; }
QPushButton#ghostButton:focus { border: 2px solid #1E40AF; }
QPushButton#quickAction {
    text-align: left; padding: 13px 16px; font-size: 10.5pt;
    background: #FFFFFF; border: 1px solid #DBEAFE; border-radius: 12px;
}
QPushButton#quickAction:hover { background: #EFF6FF; border-color: #1E40AF; color: #1E3A8A; }
QPushButton#quickAction:focus { border: 2px solid #1E40AF; padding: 12px 15px; }

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #FFFFFF; color: #1E293B;
    border: 1px solid #D6DFEA; border-radius: 8px;
    padding: 5px 8px; min-height: 18px;
    selection-background-color: #DBEAFE; selection-color: #1E3A8A;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 2px solid #1E40AF; padding: 4px 7px;
}
QLineEdit:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: #F1F5F9; color: #94A3B8;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #FFFFFF; border: 1px solid #D6DFEA; border-radius: 6px;
    padding: 4px; outline: 0;
    selection-background-color: #DBEAFE; selection-color: #1E3A8A;
}
QCheckBox { spacing: 8px; color: #334155; }
QCheckBox::indicator { width: 16px; height: 16px; }

QTableWidget, QTreeWidget, QTextBrowser {
    background: #FFFFFF; border: 1px solid #DBEAFE; border-radius: 10px;
    gridline-color: #EEF2F7; alternate-background-color: #F8FAFC;
    selection-background-color: #DBEAFE; selection-color: #1E3A8A;
    padding: 2px;
}
QTableWidget:focus, QTreeWidget:focus, QTextBrowser:focus { border: 2px solid #93C5FD; }
QTableWidget::item, QTreeWidget::item { padding: 4px 6px; }
QTableWidget::item:hover, QTreeWidget::item:hover { background: #EFF6FF; }
QHeaderView::section {
    background: #EFF6FF; color: #1E3A8A; padding: 7px 6px;
    border: none; border-bottom: 1px solid #DBEAFE; font-weight: bold;
}
QTabWidget::pane { border: 1px solid #DBEAFE; border-radius: 10px; background: #FFFFFF; top: -1px; }
QTabBar::tab {
    background: transparent; color: #64748B; padding: 8px 16px;
    border: none; border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #1E293B; }
QTabBar::tab:selected { color: #1E40AF; border-bottom: 2px solid #1E40AF; font-weight: bold; }

QScrollArea { border: none; background: transparent; }
QScrollArea#panelCard {
    background: #FFFFFF; border: 1px solid #DBEAFE; border-radius: 10px;
}
QScrollArea#panelCard > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSlider::groove:horizontal { height: 4px; background: #E2E8F0; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #1E40AF; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; background: #1E40AF;
}
QSlider::handle:horizontal:hover { background: #1E3A8A; }

QProgressBar {
    background: #E2E8F0; border: none; border-radius: 5px;
    min-height: 10px; max-height: 10px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: #1E40AF; border-radius: 5px; }

QSplitter::handle { background: #E2E8F0; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QStatusBar { background: #FFFFFF; border-top: 1px solid #E2E8F0; color: #64748B; }
QStatusBar::item { border: none; }
QLabel#formSection {
    color: #1E40AF; font-size: 9pt; font-weight: bold;
    padding: 10px 0 2px 0;
}
QLabel#formHint { color: #64748B; font-size: 8.5pt; padding: 6px 0; }
QLabel#sourceHint {
    color: #1E3A8A; background: #EFF6FF; border: 1px solid #DBEAFE;
    border-left: 4px solid #1E40AF; border-radius: 6px;
    padding: 7px 10px; font-size: 8.5pt;
}
QLabel#tableEmpty { color: #94A3B8; font-size: 10pt; background: transparent; }
QLabel#plotPlaceholder {
    color: #64748B; font-size: 10.5pt; background: #FFFFFF;
    border: 1px dashed #CBD5E1; border-radius: 12px; padding: 24px;
}
QFrame#metricCard {
    background: #F8FAFF; border: 1px solid #DBEAFE; border-radius: 10px;
}
QLabel#metricCaption { color: #64748B; font-size: 8pt; font-weight: bold; }
QLabel#metricValue {
    color: #1E3A8A; font-family: "Cascadia Mono", "Consolas", "Microsoft YaHei UI";
    font-size: 15pt; font-weight: bold;
}
QLabel#metricDetail { color: #64748B; font-size: 8pt; }
QFrame#infoCard { background: #FFFFFF; border: 1px solid #DBEAFE; border-radius: 12px; }
QLabel#infoTitle { color: #0F172A; font-size: 10pt; font-weight: bold; }
QLabel#assumptionChip {
    color: #1E3A8A; background: #EFF6FF; border: 1px solid #DBEAFE;
    border-radius: 6px; padding: 5px 9px; font-size: 8.5pt;
}
QToolTip {
    background: #0F172A; color: #F8FAFC; border: none;
    border-radius: 6px; padding: 6px 8px;
}
"""


def apply_theme(app=None):
    """把统一主题应用到整个应用；重复调用安全。"""
    app = app or QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(APP_QSS)
