from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QAction, QIcon, QFont, QColor,QFontMetrics
import json
import builtins
import data
from sanitizeName import sanitize
from typing import List, Union,Optional,Dict,Any
from helperFunctions import addArrayItem
from nested_lookup import nested_lookup, nested_update
from .qButtons import QRemoveButton
from widgets.QCWLedWidget import QCWLedWidget
from widgets.QCWLedGroupWidget import QCWLedGroupWidget
from helperFunctions import traverseCWLversion

class QExternalLinksGroupWidget(QCWLedGroupWidget):
    # Define a custom signal to indicate that some information has changed
    
    def __init__(
            self, 
            parent=None,
            cwl_tool:Optional[str] = None,
            cwl_version:Optional[str] = None
        ):
        # Initialize widgets
        super().__init__(parent=parent,
                     cwl_tool=cwl_tool,
                     cwl_version=cwl_version,
                     widget_class=QExternalLinksWidget,
                     label="External Links"
                     )
        self.command_counter = 0
        
    def populateFromCWL(self, cwl_data: List[Dict[str,str]] = None):
        # print(f"Populating ExternalLinksGroupWidget with data: {json.dumps(cwl_data)}")
        super().populateFromCWL(cwl_data)
    

    def setCWLVersion(self, cwl_version: str=None):
        """
        Traverse the hierarchy of parent objects
        until we find the an object that has a
        CWL version set, and set that version
        for this widget and all its children.

        This happens because the baseCommand
        does not have a cwl version on its own,
        
        """
        # print(f"Traversing objects found {self.cwl_version}")
        self.cwl_version = traverseCWLversion(self)

    @pyqtSlot()
    def addWidget(self,
                  cwl_data: Optional[dict] = None):
        """Add a new QExternalLinks to the container."""
        # print("Adding a new external link")

        super().addWidget(
            cwl_data=cwl_data,
            entry_order=self.command_counter,
            parent=self,
            cwl_version=self.cwl_version
        )
        self.command_counter += 1

    def getData(self):
        """Get external links data as a list of dicts with 'URL' and 'type' keys."""
        contents = super().getData()
        return contents


class QExternalLinksWidget(QCWLedWidget):
    '''
    class to handle  a row of input for a basecommand
    param: entry_order : the order that this row was added (it is not shown on the UI)

    param: parent: the parent

    this class emits an editingFinished signal
    one can get the baseCommand, baseCommandOrder, baseCommandEntry using the named attributes
    '''
    
    def __init__(self, 
                 parent=None,
                 cwl_version:Optional[str]=None,
                 entry_order:Optional[int]=None,
                 cwl_data:Optional[dict]=None):
        super().__init__(parent=parent,
                         cwl_tool=cwl_data,
                         cwl_version=cwl_version)
        self.entry_order=entry_order
    
    def initUI(self):
        # Initialize widgets
        super().initUI()
        self.line_edit1 = QLineEdit(self)
        self.line_edit1.setPlaceholderText("external URL")
        self.line_edit2 = QLineEdit(self)
        self.line_edit2.setPlaceholderText("type")
        
        # Connect the remove button's clicked signal to the removeRequested signal
        self.line_edit1.editingFinished.connect(self._emit_editing_finished)
        self.line_edit2.editingFinished.connect(self._emit_editing_finished)
        # Create a layout and add widgets to it
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.line_edit1)
        layout.addWidget(self.line_edit2)
        
        # Set the layout for the widget
        self.setLayout(layout)

    def populateFromCWL(self, 
                        cwl_data: Optional[dict] = None):
        super().populateFromCWL(cwl_data)
        self.line_edit1.setText(self.default_value.get('URL',''))
        self.line_edit2.setText(self.default_value.get('type',''))



    def setCWL(self, 
               cwl_tool: Optional[dict]=None):
        """
        Check that the cwl_data is a dict with URL and type keys
        """
        if cwl_tool is not None:
            # print(f"Setting CWL data: {json.dumps(cwl_tool)}")
            if not isinstance(cwl_tool, dict):
                raise ValueError("cwl_data must be a dictionary")
            if 'URL' not in cwl_tool or 'type' not in cwl_tool:
                raise ValueError("cwl_data must contain 'URL' and 'type' keys")
        super().setCWL(cwl_tool)

    def getData( self) -> dict:
        """
        Get the external link data as a dictionary with 'URL' and 'type' keys.
        """
        url = self.line_edit1.text().strip()
        link_type = self.line_edit2.text().strip()
        data = {
            'URL': url,
            'type': link_type
        }
        return data
    
    def clear(self):
        """
        Clears the widget's data and resets its state.
        """
        super().clear()
        self.line_edit1.clear()
        self.line_edit2.clear()