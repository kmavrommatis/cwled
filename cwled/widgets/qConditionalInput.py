"""
This module contains widgets for handling conditional inputs in workflow steps.
Conditional inputs are inputs that don't directly map to tool inputs but are used
in 'when' statements for conditional execution.
"""
from typing import Any, Dict, List, Optional
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit
import logging

from widgets.QCWLedWidget import QCWLedWidget
from widgets.QCWLedGroupWidget import QCWLedGroupWidget
from cwl_utils_handler import get_cwl_module


class QConditionalInputsGroupWidget(QCWLedGroupWidget):
    """
    Group widget that manages a list of conditional input widgets.
    """
    
    def __init__(self,
                 parent: Optional[QWidget] = None,
                 cwl_tool: Optional[List] = None,
                 cwl_version: Optional[str] = None):
        
        if cwl_version is None and hasattr(parent, 'cwl_version'):
            cwl_version = getattr(parent, 'cwl_version')
        
        super().__init__(
            parent=parent,
            cwl_tool=cwl_tool,
            cwl_version=cwl_version,
            widget_class=QConditionalInput,
            label="Conditional Inputs (for 'when' statements)")


class QConditionalInput(QCWLedWidget):
    """
    Widget for a single conditional input with ID and Source fields.
    
    A conditional input is a workflow step input that doesn't match any tool input
    but is needed for conditional execution using 'when' statements.
    """
    
    editingFinished = pyqtSignal()
    
    def __init__(self,
                 parent: Optional[QWidget] = None,
                 cwl_tool: Optional[Any] = None,
                 cwl_version: str = "v1.0"):
        """
        Initialize the conditional input widget.
        
        Args:
            parent: Parent widget
            cwl_tool: WorkflowStepInput object or None
            cwl_version: CWL version string
        """
        super().__init__(parent=parent,
                        cwl_tool=cwl_tool,
                        cwl_version=cwl_version)
    
    def initUI(self):
        """Initialize the user interface."""
        super().initUI()
        
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5)
        
        # ID field
        id_label = QLabel("ID:")
        id_label.setMinimumWidth(30)
        self.main_layout.addWidget(id_label)
        
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Input ID")
        self.id_input.setMinimumWidth(150)
        self.main_layout.addWidget(self.id_input)
        
        # Source field
        source_label = QLabel("Source:")
        source_label.setMinimumWidth(50)
        self.main_layout.addWidget(source_label)
        
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Source (comma-separated for multiple)")
        self.main_layout.addWidget(self.source_input, 1)
        
        self.setLayout(self.main_layout)
        
        # Connect signals
        self.id_input.editingFinished.connect(self._emit_editing_finished)
        self.source_input.editingFinished.connect(self._emit_editing_finished)
    
    def getData(self) -> Optional[Any]:
        """
        Retrieve data as a WorkflowStepInput object.
        
        Returns:
            WorkflowStepInput object or None if no data
        """
        input_id = self.id_input.text().strip()
        source_text = self.source_input.text().strip()
        
        if not input_id:
            return None
        
        module = get_cwl_module(self.cwl_version)
        
        # Parse source - can be a single string or a list
        source = None
        if source_text:
            if ',' in source_text:
                source = [s.strip() for s in source_text.split(',') if s.strip()]
            else:
                source = source_text
        
        # Create WorkflowStepInput
        return module.WorkflowStepInput(
            id=input_id,
            source=source,
            default=None
        )
    
    def populateFromCWL(self, cwl_data: Any):
        """
        Populate the widget with data from a WorkflowStepInput.
        
        Args:
            cwl_data: WorkflowStepInput object
        """
        super().populateFromCWL(cwl_data)
        
        if cwl_data:
            # Extract ID (remove workflow prefix if present)
            if hasattr(cwl_data, 'id') and cwl_data.id:
                input_id = cwl_data.id.split('#')[-1].split('/')[-1]
                self.id_input.setText(input_id)
            
            # Extract source(s)
            if hasattr(cwl_data, 'source') and cwl_data.source:
                if isinstance(cwl_data.source, list):
                    self.source_input.setText(", ".join(cwl_data.source))
                else:
                    self.source_input.setText(cwl_data.source)
    
    def clear(self):
        """Clear all fields in the widget."""
        super().clear()
        self.id_input.clear()
        self.source_input.clear()
