from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QAction, QIcon, QFont, QColor,QFontMetrics

from pathlib import Path, PurePath
from CWLparser import Parser
import json
from markdown2 import markdown 
from configuration import Configuration
import builtins
import data
import logging
from sanitizeName import sanitize
from typing import Union
from helperFunctions import addArrayItem
from nested_lookup import nested_lookup, nested_update
from widgets.qLabelLineEditWidget import QLabelLineEditWidget
from widgets.qButtons import *
import sys
from JavascriptEditor import JavaScriptEditorDialog

class QInitialWorkDirGroup(QWidget):
    # Define a custom signal to indicate that some information has changed
    editingFinished = pyqtSignal()
    files_counter=0
    builtins.labelWidth=100
    def __init__(self, cwl_dict:dict={}, parent=None):
        super().__init__(parent)
        self.logger=logging.getLogger(self.__class__.__name__)
        try:
            self.logger.setLevel(data.configuration.get('logLevel',{}).get(self.__class__.__name__, 'DEBUG'))
        except Exception as e:
            self.logger.setLevel("DEBUG")
        self.cwl_dict=cwl_dict
        # Initialize widgets
        
        self.initUI()

    def initUI(self):
        self.label = QLabel("Working directory", self)
        self.label.setFixedWidth(builtins.labelWidth)
        self.add_button = QPushButton("Add", self)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
    
        layout_label=QHBoxLayout()
        layout_label.addWidget(self.label)
        layout_label.addWidget(self.add_button)
        layout_label.addStretch(1)

        # self.container = QWidget(self)
        self.container_layout = QVBoxLayout()
        # self.container.setLayout(self.container_layout) 
        
        # # Create a layout for the main widget
        
        
        # # Set up the container to hold the QSecondaryFiles instances
        # self.scroll_area = QScrollArea(self)
        # self.scroll_area.setWidget(self.container)
        # self.scroll_area.setWidgetResizable(True)
        self.layout.addLayout(layout_label)
        # self.layout.addWidget(self.scroll_area)
        self.layout.addLayout(self.container_layout)
        # # Set the layout for the main widget
        self.setLayout(self.layout)
        # self.setLayout(self.container_layout)
        # # Connect the add button's clicked signal to the slot
        self.add_button.clicked.connect(self.addWorkDirWidget)
        
    
    @pyqtSlot()
    def onTextChange(self):
        self.editingFinished.emit()

    @pyqtSlot()
    def addWorkDirWidget(self, working_directory:dict=None):
        """Add a new QWorkDir to the container."""
        command_widget = QWorkDir(
            entry_order=self.files_counter,
            working_directory=working_directory,
            parent=self
        )
        command_widget.editingFinished.connect(self.onTextChange)
        if working_directory:
            command_widget.populatedFromCWL( working_directory)
        self.container_layout.addWidget(command_widget)
        
        
        # Force the container and scroll area to adjust size after adding the widget
        # self.container.adjustSize()
        # self.scroll_area.ensureWidgetVisible(command_widget)

    def getData(self):
        contents = []
        for i in range(self.container_layout.count()):
            item = self.container_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if isinstance(widget, QWorkDir):
                    contents.append(widget.text())
        return {'class':'InitialWorkDirRequirement', 'listing': contents}
    
    def populatedFromCWL( self , working_directory:list):
        '''
        sets the contents of widgets based on 
        existing data from cwl 
        '''

        self.logger.debug(f"Received commands { working_directory }  to add to the layout")
        self.files_counter=0
        self.clear()
        for requirement in working_directory:
            if requirement.get('class')=='InitialWorkDirRequirement':
                for ev in requirement.get('listing',[]):
                    self.logger.debug(f"Adding working directory { ev }")
                    self.addWorkDirWidget( working_directory=ev)

    def clear(self, layout=None):
        if not layout:
            layout=self.container_layout
            # layout=self.layout
        self.logger.debug(f"Cleaning up existing values")
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item.layout() and item.layout() != layout:
                self.clear(item.layout())
            elif item.widget():
                item.widget().deleteLater()
        self.logger.debug(f"Cleaning up finished")


class QWorkDir(QWidget):
    '''
    class to handle  a row of input for a working directory
    param: entry_order : the order that this row was added (it is not shown on the UI)
    param: working_directory  = {'listing': {'entryname':'xx', 'writable': false, 'entry': 'xxxx'}}
    param: parent: the parent

    this class emits an editingFinished signal
    one can get the baseCommand, baseCommandOrder, baseCommandEntry using the named attributes
    '''
    # Define a custom signal to indicate that some information has changed
    editingFinished = pyqtSignal()
    codeUpdated=pyqtSignal()
    working_directory=None
    def __init__(self, 
                 entry_order=0,
                 working_directory:dict=None,
                 parent=None):
        super().__init__(parent)
        self.logger=logging.getLogger(self.__class__.__name__)
        try:
            self.logger.setLevel(data.configuration.get('logLevel',{}).get(self.__class__.__name__, 'DEBUG'))
        except Exception as e:
            self.logger.setLevel("DEBUG")
        self.entry_order=entry_order
        
        if working_directory:
            self.working_directory=working_directory
        self.logger.debug(f"For the WorkDir we got {self.working_directory}")
        self.initUI()
    
    def initUI(self):
        # Initialize widgets
        self.entry_edit_box = QLineEdit(self)
        self.entry_edit_box.setPlaceholderText("Filename or Expression")
        self.entryname_edit_box=QLineEdit(self)
        self.entryname_edit_box.setPlaceholderText("Target Filename")
        self.writable_checkbox=QCheckBox( "Writable")
        if self.working_directory:
            self.entry_edit_box.setText( self.working_directory.get('entry',''))
            self.entryname_edit_box.setText( self.working_directory.get('entryname',''))
            self.writable_checkbox.setChecked( self.working_directory.get('writable',False))

        self.remove_button = QRemoveButton(parent= self)
        self.edit_button=QCodeButton(parent=self)
        
        # Connect the remove button's clicked signal to the removeRequested signal
        self.remove_button.clicked.connect(self.onRemoveClicked)
        self.entry_edit_box.editingFinished.connect(self.onTextChange)
        self.entryname_edit_box.editingFinished.connect(self.onTextChange)
        self.edit_button.clicked.connect(lambda:self.onCodeEditor(self.entry_edit_box))
        # Create a layout and add widgets to it
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.entry_edit_box)
        layout.addWidget(self.entryname_edit_box)
        layout.addWidget(self.writable_checkbox)
        layout.addWidget(self.remove_button)
        layout.addWidget(self.edit_button)
        
        # Set the layout for the widget
        self.setLayout(layout)

    @pyqtSlot()
    def onCodeEditor(self, widget_to_update=None):

         # Show the dialog
        dialog = JavaScriptEditorDialog(parent=self)
        dialog.cwl_dict=self.cwl_dict
        if widget_to_update and  widget_to_update.text():
            dialog.editor.setText( widget_to_update.text())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get the JavaScript code when dialog is accepted
            code = dialog.get_javascript_code()
            # print("JavaScript code submitted:", code)
            if code:
                widget_to_update.setText( code)
                self.codeUpdated.emit()
                
    def populatedFromCWL( self , working_directory:dict):
        if working_directory:
            self.entry_edit_box=working_directory.get('entry','')
            self.entryname_edit_box=working_directory.get('entryname','')
            self.writable_checkbox.setChecked(  working_directory.get('writable', False) )
        

    @pyqtSlot()
    def onRemoveClicked(self):
        """Emit the removeRequested signal when the remove button is clicked."""
        if self.parent():
            self.setParent(None)  # Remove widget from its parent layout
            self.hide()  # Optionally hide the widget if needed
            self.deleteLater()

    @pyqtSlot()
    def onTextChange(self):
        self.editingFinished.emit()

    def text(self):

        # this follows the InitialWorkDirRequirement
        # https://www.commonwl.org/v1.2/CommandLineTool.html#InitialWorkDirRequirement
        return ({ 'entry': self.entry_edit_box.text(),
                  'entryname': self.entryname_edit_box.text(),
                  'writable': self.writable_checkbox.isChecked()})
    
# Application setup
if __name__ == "__main__" :

    logger=logging.getLogger('')
    conf=Configuration()
    conf.loadConfiguration( "commandLineWindow.yaml")#,"dataStructures.yaml"] )
    data.configuration=conf.getConfiguration()
    app = QApplication(sys.argv)
    tag_widget = QInitialWorkDirGroup()
    tag_widget.show()

    tag_widget.populateFromCWL( [{"entry":"NAME","entryname":"TEST"}])
    # Example usage to get tag values
    def print_tag_values():
        print("Tag values:", tag_widget.getData())

    # Print tag values after adding some tags
    print_tag_values()
    import time
    time.sleep(2)  # Allow some time for user interaction


    sys.exit(app.exec())
