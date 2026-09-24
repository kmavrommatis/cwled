from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QFont
import logging
import sys
import data
from typing import Optional

import jinja2
from pathlib import Path
from dotenv import load_dotenv
import data
import getpass
import os
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from LLM import DraftToolLLM

class DraftTool(QDialog):
    """
    A dialog that allows users to paste help text or documentation
    and draft new CWL tools based on that text.
    """
    output_filename:str = None # the filename where the drafted CWL tool is saved
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger=logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get('logLevel',{}).get(self.__class__.__name__, 'DEBUG'))

        self.setWindowTitle("Draft CWL Tool")
        self.setModal(True)  # Make the dialog modal
        self.resize(800, 600)  # Set initial size
        self.initUI()

    def initUI(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Create a label for instructions
        instruction_label = QLabel("Paste help text of tools, or documentation:")
        instruction_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(instruction_label)

        # Create a large text edit box
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("Paste help text of tools, or documentation")
        self.text_edit.setMinimumHeight(400)
        
        # Set font for better readability
        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Monaco", 10)  # Alternative for macOS
        if not font.exactMatch():
            font = QFont("Courier New", 10)  # Fallback
        self.text_edit.setFont(font)
        
        layout.addWidget(self.text_edit)

        # Create button layout
        button_layout = QHBoxLayout()
        
        # Add stretch to push buttons to the right
        button_layout.addStretch()
        
        # Create Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(100)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        # Create Draft tool button
        self.draft_button = QPushButton("Draft tool")
        self.draft_button.setMinimumWidth(100)
        self.draft_button.setDefault(True)  # Make it the default button
        self.draft_button.clicked.connect(self.onDraftTool)
        button_layout.addWidget(self.draft_button)
        
        # Style the buttons
        # button_style = """
        #     QPushButton {
        #         background-color: #f0f0f0;
        #         border: 1px solid #c0c0c0;
        #         border-radius: 4px;
        #         padding: 8px 16px;
        #         font-size: 12px;
        #     }
        #     QPushButton:hover {
        #         background-color: #e0e0e0;
        #     }
        #     QPushButton:pressed {
        #         background-color: #d0d0d0;
        #     }
        #     QPushButton:default {
        #         background-color: #007acc;
        #         color: white;
        #         border-color: #005999;
        #     }
        #     QPushButton:default:hover {
        #         background-color: #005999;
        #     }
        # """
        # self.cancel_button.setStyleSheet(button_style)
        # self.draft_button.setStyleSheet(button_style)
        
        layout.addLayout(button_layout)
        
        # Set the main layout
        self.setLayout(layout)
        
        # Set focus to the text edit
        self.text_edit.setFocus()

    def onDraftTool(self):
        """Handle the Draft tool button click"""
        text_content = self.text_edit.toPlainText().strip()
        
        if not text_content:
            QMessageBox.warning(self, "Warning", "Please enter some text before drafting a tool.")
            return
        
        self.logger.debug(f"Draft tool requested with {len(text_content)} characters of text")
        
        try:
            # Extract tool name from help text (simple heuristic)
            tool_name = self.extractToolName(text_content)
            
            # Create DraftToolLLM instance and generate CWL
            draft_llm = DraftToolLLM(
                model=data.configuration.get('llm',{}).get('LLMModel','gemini-2.5-flash'),
                tool_name=tool_name,
                tool_version="latest"
            )
            cwl_content = draft_llm.preparePrompt(
                help_text=text_content
            )
            # Ensure no Markdown code fences (e.g., ```yaml ... ```)
            cwl_content = self.stripCodeFences(cwl_content)
            
            
            # Save to file
            self.outfilename = f"_draft_{tool_name}.cwl"

            with open(self.outfilename, 'w', encoding='utf-8') as f:
                f.write(cwl_content)
            
            self.logger.info(f"CWL tool definition saved to: {self.outfilename}")
            
            # Show success message
            QMessageBox.information(
                self,
                "Tool Generated",
                f"CWL tool definition has been generated and saved to:\n\n{self.outfilename}"
            )
            
            # Accept the dialog
            self.accept()
        except ValueError as ve:
            self.logger.warning(f"ValueError initializing DraftToolLLM: {str(ve)}")
            
        except Exception as e:
            # Close progress message if it exists
            if 'progress_msg' in locals():
                progress_msg.close()
                
            error_msg = f"Error generating CWL tool: {str(e)}"
            self.logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)

    def extractToolName(self, help_text: str) -> str:
        """
        Extract tool name from help text using simple heuristics.
        
        Args:
            help_text (str): The help text content
            
        Returns:
            str: Extracted tool name or "unknown" if not found
        """
        lines = help_text.split('\n')
        tool_name="unknown"
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            
            # Look for "Usage: toolname" pattern
            if line.lower().startswith('usage:'):
                parts = line.split()
                if len(parts) >= 2:
                    tool_name = parts[1].split('[')[0].split('(')[0]  # Remove options/args
                    tool_name= tool_name.strip()
                    break
            
            # Look for lines that might contain the tool name
            if any(keyword in line.lower() for keyword in ['command:', 'tool:', 'program:']):
                parts = line.split(':')
                if len(parts) >= 2:
                    tool_name = parts[1].strip().split()[0]
                    break
        
        # if the tool_name contains spaces return the last part
        # if the tool contains slahes (e.g., /usr/bin/tool), return the last part
        if ' ' in tool_name:
            tool_name = tool_name.split()[-1]
        if '/' in tool_name:
            tool_name = tool_name.split('/')[-1]
        if '\\' in tool_name:
            tool_name = tool_name.split('\\')[-1]
        if '|' in tool_name:
            tool_name = tool_name.split('|')[-1]
        # Fallback: return "unknown"
        return tool_name

    def getText(self) -> str:
        """Get the text content from the text edit"""
        return self.text_edit.toPlainText()

    def setText(self, text: str):
        """Set the text content in the text edit"""
        self.text_edit.setPlainText(text)

    def stripCodeFences(self, text: str) -> str:
        """
        Remove leading/trailing Markdown code fences from text.
        Handles patterns like:
        ```yaml\n...\n```
        or
        ```\n...\n```
        """
        if not text:
            return text
        s = text.strip()
        if s.startswith("```"):
            # Drop first fence line (with optional language), keep remainder
            first_nl = s.find('\n')
            if first_nl != -1:
                s = s[first_nl + 1:]
            else:
                # Single-line with just a fence
                return ""
            # Drop trailing fence if present
            if s.endswith("```"):
                s = s[:-3]
            s = s.strip()
        return s


# class DraftToolLLM:
#     """
#     Create an LLM to generate a CWL tool from 
#     the provided help text or documentation of the application
#     """
#     model=None # the LLM model to use
#     system_prompt = None  # the system prompt to use for the LLM
#     def __init__(self,
#                  model: Optional[str] =  "gpt-4o-mini",
#                  tool_name: str = "unknown",
#                  tool_version: str = "latest",
#                  help_message: str = ""
#                  ):
#         """Initialize the DraftToolLLM."""
#         self.logger = logging.getLogger(self.__class__.__name__)
#         self.logger.setLevel(data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG'))
        
#         self.setModel(model)
#         self.system_prompt = self.prepareSystemPrompt( 
#             tool_name=tool_name,
#             tool_version=tool_version,
#         )  # the system prompt to use for the LLM

#     def setModel(self, model: str):
#         """
#         Set the LLM model to use for generating the CWL tool.

#         Args:
#             model (str): The name of the LLM model to use.
#             e.g. "gpt-4o-mini"
#         """
#         if model in ["gpt-4o-mini", "gpt-4"]:
#             if not os.environ.get("OPENAI_API_KEY"):
#                 load_dotenv()  # Load environment variables from .env file if present
#                 if not os.environ.get("OPENAI_API_KEY"):
#                     print("OpenAI API key not found in environment variables.")
#                     print("You can set it in a .env file or enter it now.")
#                     os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")
#             self.model = init_chat_model(model, model_provider="openai")
#         if model in ["gemini-2.5-flash"]:
#             if not os.environ.get("GOOGLE_API_KEY"):
#                 load_dotenv()
#                 if not os.environ.get("GOOGLE_API_KEY"):
#                     print("Google API key not found in environment variables.")
#                     print("You can set it in a .env file or enter it now.")
#                     os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter API key for Google: ")
#             self.model = init_chat_model(model, model_provider="google_genai")
                    


#     def prepareSystemPrompt(self, 
#                             cwl_version: str = "v1.2",
#                             tool_name: str = "unknown", 
#                             tool_version: str = "latest"):
#         """
#         Prepare the system prompt for the LLM by reading and rendering the Jinja2 template.
        
#         Args:
#             tool_name (str): The name of the tool. Defaults to "unknown".
#             tool_version (str): The version of the tool. Defaults to "latest".
#             help_message (str): The help text or documentation. Defaults to "".
            
#         Returns:
#             str: The rendered system prompt.
#         """
#         try:
#             # Get the config directory path (relative to the current file)
#             template_path = data.config_directory / "systemPrompt.jinja2"
            
#             # Check if template file exists
#             if not template_path.exists():
#                 self.logger.error(f"Template file not found: {template_path}")
#                 raise FileNotFoundError( "Template file not found.")
            
#             # Set up Jinja2 environment
#             env = jinja2.Environment(
#                 loader=jinja2.FileSystemLoader(data.config_directory),
#                 autoescape=jinja2.select_autoescape(['html', 'xml'])
#             )
            
#             # Load the template
#             template = env.get_template(template_path.name)
            
#             # Render the template with provided variables
#             rendered_prompt = template.render(
#                 cwlVersion=cwl_version,
#                 argumentFormat=data.configuration.get('sanitize_id'),
#                 tool_name=tool_name,
#                 tool_version=tool_version
#             )
            
#             self.logger.debug(f"System prompt rendered successfully for tool: {tool_name}")
#             self.system_prompt = rendered_prompt
#             return rendered_prompt
            
#         except jinja2.TemplateError as e:
#             self.logger.error(f"Jinja2 template error: {e}")
#             raise Exception( f"Template rendering error: {e}")
#         except Exception as e:
#             self.logger.error(f"Error preparing system prompt: {e}")
#             raise Exception( f"Error preparing system prompt: {e}")
        


#     def preparePrompt(self, help_text: str) -> str:
#         """
#         Prepare the prompt for the LLM based on the provided help text.

#         Args:
#             help_text (str): The help text or documentation of the application.
#             tool_name (str): The name of the tool. Defaults to "unknown".
#             tool_version (str): The version of the tool. Defaults to "latest".
            
#         Returns:
#             str: The generated CWL content from the LLM.
#         """

        
#         messages = [
#             SystemMessage(content=self.system_prompt),
#             HumanMessage(content=help_text),
#         ]

#         response = self.model.invoke(messages)
        
#         return response.content


# Testing/debugging section
if __name__ == '__main__':
    """
    This section allows running the DraftTool dialog standalone
    for testing and debugging purposes.
    """
    
    # Create the QApplication
    app = QApplication(sys.argv)
    
    # Initialize data configuration for logging (if needed)
    if not hasattr(data, 'configuration'):
        data.configuration = {'logLevel': {'DraftTool': 'DEBUG', 'DraftToolLLM': 'DEBUG'}}
    
    # Test the DraftToolLLM class and prepareSystemPrompt method
    # print("Testing DraftToolLLM.prepareSystemPrompt()...")
    # llm_tool = DraftToolLLM(model="gemini-2.5-flash")
    # test_help_text = """Usage: myapp [OPTIONS] INPUT_FILE OUTPUT_FILE
# A sample command line tool for processing files."""
    
   
    
    # print("System prompt preview (first 200 chars):")
    # print(llm_tool.system_prompt)
    # print()
    

    # print(llm_tool.preparePrompt(test_help_text))
    # Create and show the dialog
    dialog = DraftTool()
    
    # Set some sample text for testing
    sample_text = """Usage: myapp [OPTIONS] INPUT_FILE OUTPUT_FILE

A sample command line tool for processing files.

Options:
  -v, --verbose     Enable verbose output
  -q, --quiet       Suppress all output
  -f, --format FMT  Output format (json, xml, csv)
  -n, --number NUM  Process NUM items (default: 10)
  --help            Show this help message

Examples:
  myapp input.txt output.txt
  myapp -v -f json input.txt output.json
  myapp --number 100 --quiet input.txt output.txt
"""
    dialog.setText(sample_text)
    
    # Show the dialog and handle the result
    result = dialog.exec()
    
    if result == QDialog.DialogCode.Accepted:
        print("Dialog accepted")
        print(f"Text content: {dialog.outfilename}")
    else:
        print("Dialog cancelled")

    
    
    # Exit the application
    sys.exit(app.exec())