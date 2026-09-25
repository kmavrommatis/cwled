from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QLabel, QMessageBox, QSizePolicy, 
                             QTreeWidget, QTreeWidgetItem, QApplication, QWidget, QSplitter)
from PyQt6.Qsci import QsciScintilla, QsciLexerJavaScript
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSlot, Qt
import subprocess
import json
import os
import data
import sys
import logging 
from typing import Any
import re
import tempfile
from pathlib import Path

class JavaScriptEditorDialog(QDialog):
    def __init__(self, 
                 cwl_dict: Any = None, 
                 parent=None):
        
        if parent is None:
            raise Exception("JavaScriptEditorDialog requires a parent widget")
        
        super().__init__(parent)
        self.jsconfig = str(data.config_directory / "jshint.conf")
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel('DEBUG')
        self.setWindowTitle("JavaScript Editor with JSHint Validation")
        self.setMinimumSize(800, 400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, 
                          QSizePolicy.Policy.Expanding)
        self.cwl_dict = cwl_dict
        
            
        self.cwl_tool = self.get_cwl_tool()
        # Initialize the JavaScript editor
        self.editor = QsciScintilla(self)
        self.editor.setUtf8(True)

        # Set up the JavaScript lexer for syntax highlighting
        lexer = QsciLexerJavaScript()
        lexer.setDefaultFont(QFont("Courier", 12))
        self.editor.setLexer(lexer)

        # Set editor properties
        self.editor.setMarginLineNumbers(1, True)
        self.editor.setMarginWidth(1, 40)
        self.editor.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        # Set initial JavaScript text
        initial_js_code = """function helloWorld() {
    console.log('Hello, world!');
}
"""
        self.editor.setText(initial_js_code)  # Set initial content

        # Create a button to validate the JavaScript with JSHint
        self.validate_button = QPushButton("Check for errors")
        self.validate_button.clicked.connect(self.validate_js)

        # Create a button to submit the JavaScript expression
        self.submit_button = QPushButton("Close")
        self.submit_button.clicked.connect(self.accept_js)

        # Text area to display validation errors (if any)
        self.validation_errors = QTextEdit()
        self.validation_errors.setReadOnly(True)
        self.validation_errors.setPlaceholderText("Validation output will be displayed here...")

        # Create the tree widget for predefined terms
        self.term_tree = QTreeWidget()
        self.term_tree.setHeaderLabel("Predefined Terms")
        self.populate_term_tree()

        # Connect tree item click signal to insert term into editor
        self.term_tree.itemClicked.connect(self.insert_term)

        # Create a horizontal splitter for the editor and tree widget
        editor_tree_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_tree_splitter.addWidget(self.editor)
        editor_tree_splitter.addWidget(self.term_tree)
        editor_tree_splitter.setSizes([600, 200])  # Editor wider by default

        # Create a vertical splitter for the editor-tree and validation errors
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(editor_tree_splitter)
        main_splitter.addWidget(self.validation_errors)
        main_splitter.setSizes([300, 100])  # Editor/Tree section taller by default

        # Layout setup for the buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.validate_button)
        button_layout.addWidget(self.submit_button)

        # Create a label to display the jsconfig file location
        self.jsconfig_label = QLabel(f"JSHint Config: {self.jsconfig }")
        self.jsconfig_label.setStyleSheet(
            "QLabel { background-color: #f0f0f0; padding: 5px; "
            "border-top: 1px solid #ccc; font-size: 10px; color: #666; }"
        )
        self.jsconfig_label.setWordWrap(False)
        self.jsconfig_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Main layout setup
        main_layout = QVBoxLayout()
        main_layout.addWidget(QLabel("JavaScript Editor"))
        main_layout.addWidget(main_splitter)  # Add the vertical splitter
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.jsconfig_label)  # Add config path label at bottom
        self.setLayout(main_layout)

    def populate_term_tree(self):
        """
        Populate the tree with predefined JavaScript terms.
        """
        self.logger.debug("Populating term tree with available datatypes")
        inputs_dict = {}
        
        # Only try to populate inputs if we have a cwl_tool with inputs
        if self.cwl_tool and hasattr(self.cwl_tool, 'inputs'):
            try:
                for input in self.cwl_tool.inputs:
                    id = input.id.split("#")[-1]
                    tp = input.type_
                    tp_list = []
                    
                    if not isinstance(tp, list):
                        tp_list.append(tp)
                    else:
                        tp_list = tp
                    inputs_dict[id] = id
                    self.logger.debug(f"Getting datatypes for {tp}")
                    for tp in tp_list:
                        if data.datatypes.get(tp):
                            inputs_dict[id] = data.datatypes.get(tp)
            except Exception as e:
                self.logger.error(f"Error populating tree: {e}")
                inputs_dict = {}
        if hasattr( self.cwl_dict, 'in_'):
            try:
                for input in self.cwl_dict.in_:
                    id = input.id.split("#")[-1]
                    inputs_dict[id] = id
                    self.logger.debug(f"Getting datatypes for {tp}")
                    inputs_dict[id] = 'unknown'
            except Exception as e:
                self.logger.error(f"Error populating tree: {e}")
                inputs_dict = {}
            
            

        terms = {
            "inputs": inputs_dict,
            "runtime": data.datatypes.get('runtime'),
            "self": data.datatypes.get('File') 
        }

        # print(f"terms = {json.dumps( terms, indent=3, default=str)}")
        # sys.exit(1)
        # Recursive function to add items to the tree
        def add_items(parent, items):
            """
            Add items to a QTreeWidgetItem parent, recursively supporting multi-layered structure.
            """
            if isinstance(items, dict):  # If the item is a dictionary, it contains sub-layers
                for key, value in items.items():
                    child = QTreeWidgetItem([key])
                    parent.addChild(child)
                    add_items(child, value)  # Recursively add sub-items
            elif isinstance(items, list):  # If the item is a list, it contains the final terms
                for term in items:
                    term_item = QTreeWidgetItem([term])
                    parent.addChild(term_item)

        # Add the hierarchical terms to the tree
        for category, items in terms.items():
            category_item = QTreeWidgetItem([category])
            self.term_tree.addTopLevelItem(category_item)
            add_items(category_item, items)

    @pyqtSlot(QTreeWidgetItem, int)
    def insert_term(self, item, column):
        """
        Insert the selected term from the tree into the editor at the current cursor position.
        
        Recursively get the full path of the selected QTreeWidgetItem,
        with each level separated by a '.'.
        """
        # Initialize an empty list to store the parts of the path
        path_parts = []
        
        # Traverse up from the selected item to the root
        while item is not None:
            path_parts.insert(0, item.text(0))  # Insert at the beginning
            item = item.parent()  # Move to the parent item
        
        self.editor.insert('.'.join(path_parts))

    @pyqtSlot()
    def validate_js(self):
        """
        Validate the JavaScript using JSHint (run JSHint as a subprocess).
        """
        # Get the code from the editor
        js_code = self.editor.text()
        js_code=re.sub( r'^\s*\$[\{\(]\s*', '', js_code)
        js_code = re.sub(r'\s*[\)\}]\s*$', '', js_code)
        # Write the code to a temporary file for JSHint to validate
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', delete=False, suffix=".js", dir=str(data.workspace_directory)
            ) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(js_code)

            # Run JSHint as a subprocess
            # jsconfig = str(data.config_directory / "jshint.conf")
            self.logger.debug(f"Using JSHint config: {self.jsconfig}")
            result = subprocess.run(
                ['jshint', '--config', self.jsconfig, temp_filename],
                capture_output=True,
                text=True
            )

            # Display the result
            if result.returncode == 0:
                self.validation_errors.setText("No errors found by JSHint.")
            else:
                self.validation_errors.setText(result.stdout)

        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "JSHint is not installed or not found.")
        
        finally:
            if 'temp_filename' in locals() and os.path.exists(temp_filename):
                os.unlink(temp_filename)  # Clean up the temporary file

    @pyqtSlot()
    def accept_js(self):
        """
        Retrieve and return the JavaScript code when submitting.
        """
        js_code = self.editor.text()
        # Return the JavaScript code as a result of the dialog
        self.accept()  # Close the dialog and set it as accepted
        # QMessageBox.information(self, "Submitted JavaScript", f"JavaScript submitted:\n\n{js_code}")

    def get_javascript_code(self):
        """
        Obsolete:
        The javascript editor should return the text as a javascript expresision
        only if it is a javascript expression :) but this fix results in modifying
        all the text in the editor, even if it is just a simple variable name, which is not ideal.


        Retrieves the JavaScript code from the editor and ensures it is properly
        formatted.

        This method gets the text from the QsciScintilla editor, checks if it
        is already wrapped in a CWL-style expression (e.g., `${...}` or
        `$(...)`), and if not, wraps it in a `${...}` block before returning it.


        Args:
            self: The instance of the JavaScriptEditorDialog.

        Returns:
            str: The JavaScript code, wrapped in a CWL expression block if it
                 wasn't already.
        """
        text = self.editor.text()
        return text
        # Check if the text is already wrapped in a CWL expression
        if re.match(r'^\s*\$[\{\(].*[\)\}]\s*$', text, re.DOTALL):
            return text
        else:
            # If not, wrap it in the standard CWL expression format
            return f"${{{text}}}"
        
    def get_cwl_tool(self):
        """
        Recursively traverses up the parent hierarchy to find a ChildWindow
        and returns its cwl_tool.
        
        Returns:
            The cwl_tool object from the parent ChildWindow, or None if not
            found
        """
        def find_child_window_parent(widget):
            """
            Inner helper function to recursively search for a ChildWindow
            parent.
            
            Args:
                widget: The current widget to check
                
            Returns:
                The parent ChildWindow object or None if not found
            """
            if widget is None:
                return None
                
            # Check if this is a ChildWindow
            # (using string check to avoid import)
            self.logger.info(f"Checking widget {widget.__class__.__name__} ")
            if hasattr(widget, 'cwl_tool') and \
               hasattr(widget.cwl_tool, 'type_'):
                self.logger.debug(f"Contains CWL {widget.cwl_tool.type_}")
            if widget.__class__.__name__ == "ChildWindow":
                self.logger.debug(f"Found ChildWindow: {widget}")
                return widget
                
            # Continue recursion with the parent
            return find_child_window_parent(widget.parent())
        self.logger.info("Traversing tool hierarchy to find the cwl tool")
        
        # Start the recursive search from this widget's parent
        self.logger.info(f"starting with {self.parent().__class__.__name__}")
        child_window = find_child_window_parent(self.parent())
        
        # If we found a ChildWindow, return its cwl_tool
        if child_window is not None:
            if hasattr(child_window, 'cwl_tool'):
                self.logger.debug("Found cwl_tool in ChildWindow")
                return child_window.cwl_tool
                
        self.logger.debug("No cwl_tool found in parent hierarchy")
        return None


# Example application setup
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Show the dialog
    dialog = JavaScriptEditorDialog(parent=self)
    
    # Example of how the tool would find the parent window
    # print("Dialog will look for cwl_tool in parent ChildWindow if needed")
    
    if dialog.exec() == QDialog.DialogCode.Accepted:
        # Get the JavaScript code when dialog is accepted
        js_code = dialog.get_javascript_code()
        # print("JavaScript code submitted:", js_code)

    sys.exit(app.exec())
