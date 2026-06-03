import sys
import os
import signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette, QColor
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from src.gui import MainWindow
from src.utils import init_logging

# Suppress noisy Qt internal cleanup messages that appear on exit
# (e.g. "QThreadStorage: entry N destroyed before end of thread")
_SUPPRESSED = (
    "QThreadStorage",
    "QThread: Destroyed",
    "QSocketNotifier",
)

def _qt_message_handler(msg_type, context, msg):
    if any(s in msg for s in _SUPPRESSED):
        return  # silently drop
    # Print everything else to stderr as normal
    print(msg, file=sys.stderr)

def apply_theme(app):
    palette = app.palette()
    is_dark = palette.color(QPalette.Base).lightness() < 128
    
    if is_dark:
        # A simple but effective dark stylesheet
        dark_stylesheet = """
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QLineEdit, QTextEdit, QComboBox {
            background-color: #3b3b3b;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 4px;
        }
        QPushButton {
            background-color: #3b3b3b;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 6px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #4b4b4b;
        }
        QTabWidget::pane {
            border: 1px solid #555555;
        }
        QTabBar::tab {
            background-color: #3b3b3b;
            color: #ffffff;
            padding: 8px 16px;
            border: 1px solid #555555;
        }
        QTabBar::tab:selected {
            background-color: #555555;
        }
        QGroupBox {
            border: 1px solid #555555;
            margin-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }
        """
        app.setStyleSheet(dark_stylesheet)
        return True
    return False

def main():
    # Suppress Qt internal cleanup noise before QApplication is created
    qInstallMessageHandler(_qt_message_handler)
    
    # Allow clean exit via CTRL+C in terminal without Qt cleanup crashes
    signal.signal(signal.SIGINT, lambda sig, frame: os._exit(0))
    
    # Initialize logging directory
    init_logging()
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    is_dark_mode = apply_theme(app)
    
    # Set application icon
    if is_dark_mode:
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon-light.svg")
    else:
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon-dark.svg")
        
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = MainWindow(is_dark_mode=is_dark_mode)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
