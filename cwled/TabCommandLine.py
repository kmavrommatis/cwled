from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QSizePolicy
)
from PyQt6.QtGui import QColor, QTextCharFormat, QFont
import logging
import data
from typing import Union, Any
from cwl_utils.parser import save
from CWLparser import is_optional
import json
import sys
import re
class CommandLine(QWidget):
    """
    Status bar displaying a command line representation of the CWL tool.
    
    This widget shows a read-only colored text view that displays
    the command line that would be executed based on the CWL tool.
    Appears at the bottom of CommandLineTool windows.
    """
    
    def __init__(self, cwl_tool: Union[Any, None], parent=None):
        """
        Initialize the CommandLine tab.
        
        Args:
            cwl_tool: The CWL tool to display
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG'))
        
        self.cwl_tool = cwl_tool
        self.initUI()
        
    def initUI(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create a read-only text viewer with colored text support
        self.command_display = QTextEdit(self)
        self.command_display.setReadOnly(True)
        self.command_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Set a monospace font for command line display
        font = QFont(data.configuration.get('command_line_window').get('font_family'), 
                     data.configuration.get('command_line_window').get('font_size'))
        self.command_display.setFont(font)
        
        # Add to layout
        layout.addWidget(self.command_display)
        self.setLayout(layout)
        
        # Populate with initial content
        self.populateFromCWL()
        
    def setCWLTool(self, cwl_tool):
        """
        Set the CWL tool and update the display.
        
        Args:
            cwl_tool: The CWL tool to display
        """
        self.cwl_tool = cwl_tool
        self.populateFromCWL()
        
    def populateFromCWL(self):
        """
        Update the command line display based on the current CWL tool.
        
        This method processes the CWL tool to generate a visual representation
        of the command line that would be executed.
        """
        self.command_display.clear()
        
        # Set up text formats for different colors
        green_format = QTextCharFormat()
        green_format.setForeground(QColor("green"))
        
        red_format = QTextCharFormat()
        red_format.setForeground(QColor("red"))
        
        # Italic red format for optional inputs
        red_italic_format = QTextCharFormat()
        red_italic_format.setForeground(QColor("red"))
        red_italic_format.setFontItalic(True)
        
        orange_format = QTextCharFormat()
        orange_format.setForeground(QColor("orange"))
        # For now, just display placeholder text with different colors
        cursor = self.command_display.textCursor()
        
        # Insert "command line" in green
        # cursor.insertText("command line", green_format)
        
        # Insert space
        # cursor.insertText(" ")
        
        # Insert "v0.1a" in red
        # cursor.insertText("v0.1a", red_format)
        
        # Future implementation would parse the CWL and show the actual command line
        components=self.getCMD()
        self.logger.debug(f"{json.dumps( components , indent=3)}")
        cursor.insertText(components.get('basecommand',''), green_format)
        cursor.insertText(" ")
        for k in components.get('arguments', (None,None) ):
            if k[1] == 'input': 
                # Check if input is optional (k[2] contains is_required flag)
                is_required = k[2] if len(k) > 2 else True
                fmt = red_format if is_required else red_italic_format
            elif k[1] == 'argument': 
                fmt = orange_format
            cursor.insertText(k[0], fmt)
            cursor.insertText(" ")



    def replace_js_expressions(self, text):
        """
        Replace JavaScript expressions $(...)  and ${...} with $<JS> in a string.
        
        This handles cases where JS expressions are embedded within larger strings,
        such as:
        - '$( inputs.normal.basename).reference.cnn' -> '$<JS>.reference.cnn'
        - 'cp $(inputs.file.path) output' -> 'cp $<JS> output'
        - '${inputs.reference.basename}' -> '$<JS>'
        - '${inputs.secondaryFiles[0].basename}' -> '$<JS>'
        
        Args:
            text: String that may contain JavaScript expressions
            
        Returns:
            String with all $(...)  and ${...} patterns replaced by $<JS>
        """
        if not isinstance(text, str):
            return text
        
        result = text
        
        # First, handle $(...) expressions - match balanced parentheses
        # Find all $( and match to their closing )
        i = 0
        while i < len(result):
            if i < len(result) - 1 and result[i:i+2] == '$(':
                # Find the matching closing parenthesis
                depth = 1
                j = i + 2
                while j < len(result) and depth > 0:
                    if result[j] == '(':
                        depth += 1
                    elif result[j] == ')':
                        depth -= 1
                    j += 1
                if depth == 0:
                    # Found matching closing paren
                    result = result[:i] + '$<JS>' + result[j:]
                    i += 5  # Length of '$<JS>'
                else:
                    i += 1
            else:
                i += 1
        
        # Then, handle ${...} expressions - match balanced braces
        i = 0
        while i < len(result):
            if i < len(result) - 1 and result[i:i+2] == '${':
                # Find the matching closing brace
                depth = 1
                j = i + 2
                while j < len(result) and depth > 0:
                    if result[j] == '{':
                        depth += 1
                    elif result[j] == '}':
                        depth -= 1
                    j += 1
                if depth == 0:
                    # Found matching closing brace
                    result = result[:i] + '$<JS>' + result[j:]
                    i += 5  # Length of '$<JS>'
                else:
                    i += 1
            else:
                i += 1
        
        return result

    def extract_input_bindings_from_type(self, input_param, input_index):
        """
        Recursively extract input bindings from complex types (records, arrays, unions).
        
        Args:
            input_param: The input parameter to process
            input_index: The index of this input in the inputs list
            
        Returns:
            List of tuples: [(command_part, position, index, 'input'), ...]
        """
        bindings = []
        
        def process_type_recursive(type_def, base_id, base_index):
            """Recursive function to process type definitions."""
            # print(f"Processing type definition: {json.dumps(save(type_def), indent=3)}")
            # print(f"Base ID: {base_id}, Base Index: {base_index}")
            if (hasattr(type_def,'type_') and  
                type_def.type_== 'record' and 
                hasattr(type_def, 'fields')):
                for field_idx, field in enumerate(type_def.fields):
                    field_id = field.name or f"field_{field_idx}"
                    
                    # Check if this field has inputBinding
                    if hasattr(field,'inputBinding') and field.inputBinding:
                        binding = field.inputBinding
                        position = binding.position or 0
                        prefix = binding.prefix or ''
                        separate = binding.separate or True
                        shell_quote = binding.shellQuote or True
                        
                        # Use field name as value
                        value = field_id
                        value=value.split("#")[-1]
                        value = self.replace_js_expressions(value)
                        
                        sep = " " if separate else ""
                        qt = "'" if shell_quote else ""
                        
                        command_part = f"{prefix}{sep}{qt}{value}{qt}"
                        # For nested fields, assume required unless proven otherwise
                        is_required = True
                        bindings.append([command_part, position, base_index, 'input', is_required])
                    
                    # # Recursively process field type if it's complex
                    field_type = field.type_
                    if isinstance(field_type, (dict, list)):
                        process_type_recursive(field_type, field_id, base_index)
                
                    # # Handle array types
                    # elif type_def.type_ == 'array':
                    #     items_type = type_def.items
                    #     if isinstance(items_type, (dict, list)):
                    #         process_type_recursive(items_type, base_id, base_index)
            
            elif isinstance(type_def, list):
                # Handle union types (list of types)
                for union_type in type_def:
                    process_type_recursive(union_type, base_id, base_index)
        
        # Start the recursive processing
        if hasattr(input_param, 'type_'):
            process_type_recursive(input_param.type_, input_param.id, input_index)
        
        return bindings


    def getCMD(self):
        self.logger.debug("Parsing the CWL tool")
        self.logger.debug(f"{save(self.cwl_tool)}")

        # get the basecommand
        bc=self.cwl_tool.baseCommand # we get an array
        if not isinstance(bc, list):
            bc=[bc]
        # Filter out None values from baseCommand
        bc = [cmd for cmd in bc if cmd is not None]
        self.logger.debug(f"Basecommand is {bc}")

        # get the arguments
        arg=arg_sort=[]
        if hasattr( self.cwl_tool, 'arguments') and self.cwl_tool.arguments:
            for idx,input_param in enumerate(self.cwl_tool.arguments):
                p=input_param.prefix if hasattr(input_param,'prefix') and input_param.prefix else ''
                v=input_param.valueFrom if hasattr(input_param, 'valueFrom') and input_param.valueFrom else ''
                if isinstance( input_param , str):
                    v=input_param
                v = self.replace_js_expressions(v)
                
                if hasattr(input_param,'separate') and  input_param.separate is False:
                    sep=""
                else:
                    sep=" "
                if hasattr(input_param, 'shellQuote') and input_param.shellQuote is True:
                    qt="'"
                else:
                    qt=""
                s=int(input_param.position) if hasattr(input_param, 'position') and input_param.position else 0
                arg.append( [f"{p}{sep}{qt}{v}{qt}", s, idx, 'argument', True])
            
        # get the inputs
        if hasattr( self.cwl_tool, 'inputs') and self.cwl_tool.inputs:
            for idx,input_param in enumerate(self.cwl_tool.inputs):
                self.logger.debug(f"Input {idx} is a {type(input_param).__name__} with content {json.dumps(save(input_param), indent=3)}")
                
                if hasattr( input_param, 'inputBinding') and input_param.inputBinding :
                    binding = input_param.inputBinding
                    s = int(binding.position) if binding.position else 0
                    p = binding.prefix if hasattr(binding, 'prefix') and binding.prefix else ''
                    
                    # Handle valueFrom if present, otherwise use input id
                    is_boolean_without_value = False
                    if hasattr(binding, 'valueFrom') and binding.valueFrom:
                        v = self.replace_js_expressions(binding.valueFrom)
                    else:
                        # Check if this is a boolean type (simple or in a union)
                        is_boolean = False
                        if input_param.type_ == 'boolean':
                            is_boolean = True
                        elif isinstance(input_param.type_, list):
                            # Check if 'boolean' is in the union type
                            is_boolean = 'boolean' in input_param.type_
                        
                        # For boolean inputs without valueFrom, only show prefix
                        if is_boolean:
                            v = ''
                            is_boolean_without_value = True
                        else:
                            v = input_param.id if input_param.id else input_param.type_
                            v = v.split("#")[-1]
                            # Check for default value
                            if hasattr(input_param, 'default') and input_param.default is not None:
                                default_val = input_param.default
                                if isinstance(default_val, (dict, list)):
                                    v = f"<{v}={json.dumps(default_val)}>"
                                else:
                                    v = f"<{v}={default_val}>"
                            else:
                                v = f"<{v}>"
                    
                    # Handle separate
                    if hasattr(binding, 'separate') and binding.separate is False:
                        sep = ""
                    else:
                        sep = " "
                    
                    # Handle shellQuote
                    if hasattr(binding, 'shellQuote') and binding.shellQuote is True:
                        qt = "'"
                    else:
                        qt = ""
                    
                    # Handle itemSeparator for array inputs only
                    if hasattr(binding, 'itemSeparator') and binding.itemSeparator:
                        # Check if the input type is actually an array
                        type_str = str(input_param.type_) if hasattr(input_param, 'type_') else ''
                        is_array = (
                            '[]' in type_str or 
                            (isinstance(input_param.type_, dict) and input_param.type_.get('type') == 'array') or
                            (isinstance(input_param.type_, list) and any('[]' in str(t) or (isinstance(t, dict) and t.get('type') == 'array') for t in input_param.type_))
                        )
                        if is_array:
                            item_sep = binding.itemSeparator
                            v = f"{v}{item_sep}{v}..."  # Show that items will be joined
                    
                    # Handle loadContents for File inputs
                    if hasattr(binding, 'loadContents') and binding.loadContents:
                        v = f"{v}[contents]"
                    
                    # Check if input is required (not optional)
                    is_required = not is_optional(input_param)
                    
                    # For boolean without valueFrom, only show the prefix
                    if is_boolean_without_value:
                        command_part = p
                    else:
                        command_part = f"{p}{sep}{qt}{v}{qt}"
                    arg.append([command_part, s, idx, 'input', is_required])

                    self.logger.debug(f"prefix {p} value {v}, position {s} index {idx}")

                else:
                    # Extract bindings from nested record/union/array types
                    nested_bindings = self.extract_input_bindings_from_type(input_param, idx)
                    arg.extend(nested_bindings)
                    
                    if nested_bindings:
                        self.logger.debug(f"Found {len(nested_bindings)} nested input bindings in input {idx}")
                        for binding in nested_bindings:
                            self.logger.debug(f"  Nested binding: {binding}")
        
        # we need to sort by s and then idx
        self.logger.debug(f"The args is {json.dumps(arg, indent=3)}")
        arg_sort=sorted(arg, key=lambda x: ( 
                        x[1], 
                        x[2]))
        # Return (command_part, type, is_required)
        arg_sort=[ (x[0], x[3], x[4]) for x in arg_sort]

        
            
        return { 'basecommand': ' '.join(bc) ,
                 'arguments':  arg_sort }

    def updateCommandLine(self):
        """
        Update the command line display based on the current tool state.
        Can be called externally when the tool is modified.
        """
        self.populateFromCWL()
