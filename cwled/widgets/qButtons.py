from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QAction, QIcon, QFont, QColor,QFontMetrics

from copy import deepcopy
from helperFunctions import addArrayItem
import unicodedata
import data
import re

class QLineSeparator(QFrame):
     def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)

class QEditButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setIcon(QIcon(data.configuration.get('icons').get('edit') ))
        self.setIconSize(QSize(32,32 ))
        self.setFixedSize(QSize(33,33))
        self.setStyleSheet("border: none;")

class QCodeButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setIcon(QIcon(data.configuration.get('icons').get('programming') ))
        self.setIconSize(QSize(32,32 ))
        self.setFixedSize(QSize(33,33))
        self.setStyleSheet("border: none;")
    
class QRemoveButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setIcon(QIcon(data.configuration.get('icons').get('remove') ))
        self.setIconSize(QSize(32,32 ))
        self.setFixedSize(QSize(33,33))
        self.setStyleSheet("border: none;")
class QAddButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # self.setText("Add")
        self.setIcon(QIcon(data.configuration.get('icons').get('add') ))
        self.setIconSize(QSize(32,32 ))
        self.setFixedSize(QSize(33,33))
        self.setStyleSheet("border: none;")

class ErrorDialog(QDialog):
    def __init__(self, error_message, details, title="Error"):
        super().__init__()
        self.setWindowTitle(title)
        self.setModal(True)
        
        # Layout for the error dialog
        layout = QVBoxLayout(self)

        # Main error message label
        error_message= "".join(ch for ch in error_message if unicodedata.category(ch)[0]!="C")
        error_label = QLabel(error_message)
        if re.search('error' , title.lower()):
            error_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        else:
            error_label.setStyleSheet("color: green; font-size: 16px; font-weight: bold;")
        layout.addWidget(error_label)

        # Scrollable area for detailed text
        detailed_text = QTextEdit()
        cleaned_details = self.remove_ansi_escape_codes(details)
        cleaned_details= "".join(ch for ch in cleaned_details if unicodedata.category(ch)[0]!="C")
        cleaned_details.replace("\n", "<br>")
        detailed_text.setHtml(cleaned_details)
        detailed_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        
        # Set HTML formatted detailed error message
        detailed_text.setPlainText(details)
        detailed_text.setStyleSheet("background-color: #f8f8f8; padding: 5px;")
        
        # Add the QTextEdit to the layout
        layout.addWidget(detailed_text)

        # OK button to close the dialog
        close_button = QPushButton("OK")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    @staticmethod
    def remove_ansi_escape_codes( text:str):
        # Regular expression pattern for ANSI escape codes
        ansi_escape_pattern = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        return ansi_escape_pattern.sub('', text)