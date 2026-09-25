from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QVBoxLayout, QHBoxLayout, QDialog,
    QFileDialog, QLabel, QPushButton, QWidget,QMessageBox
)
from PyQt6.QtGui import QAction, QIcon, QFont, QColor, QFontMetrics, QPixmap, QKeySequence
from pathlib import Path, PurePath
from CWLparser import Parser
import json
from ruamel.yaml import YAML
import builtins
import data
import logging
import sys
import os
import webbrowser
import tempfile
import markdown2
from TabInfoWindow import InfoWindow
from widgets.qtoogle import QToggle
from TabCodeEditor import CodeWindow
from TabToolEditor import ToolEditor
from TabSummary import WorkflowSummary
from CWLtoolFactory import CWLRunner
from widgets.qButtons import ErrorDialog
from typing import Union,List
from pathlib import Path, PosixPath
from TabWorkflowEditor import WorkflowEditor
from ChildWindow import ChildWindow
from WorkspaceContents import WorkspaceContents
from logger import ErrorDialogHandler
from draft import DraftTool
import cwled
from platformdirs import user_config_path, user_log_path
import version
# class that defines the main window
class MainWindow( QMainWindow):
    '''
    class for the main window
    It hosts all the tabs menus etc
    When a menu action is triggered it passes a message to the downstream applications.
    '''
    cwl_dict={}  # this is the cwl dictionary that we carry over in this window
    openWindowFromFile = pyqtSignal(str) # this signal will transfer the filename to open in a window
    def __init__(self , 
                 input_files:List[PosixPath|Path]=None,
                 export_image_file:str=None):
        super().__init__()
        # load the configuration
        self.logger=logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get('logLevel',{}).get(self.__class__.__name__, 'DEBUG'))
        self.setupGlobalErrorDialogLogging()
        self.open_windows={}
        self.window_actions={}
        self.active_window=None
        self.logger.info(f"Setting up {self.__class__.__name__}")
        self.logger.info(f"Logging level set to {logging.getLevelName(self.logger.level)}")
        self.openWindowFromFile.connect( self.onCreateWindowFromFile )
        self.initUI()

        QTimer.singleShot(100, self._ensureWindowActive)
        
        if input_files:
            for idx,input_file in enumerate(input_files):
                # check if the file is an absolute path or not
                # if it is not, we make it one using the workspace directory as the baseline
                if Path( input_file ).is_absolute():
                    # check that the file is inside the workspace
                    if not str( Path( input_file ).parent ).startswith( str( data.workspace_directory ) ):
                        self.logger.error(f"Input file {input_file} is outside the workspace directory {data.workspace_directory}. Cannot open.")
                        return
                    pass
                else:
                    # make it absolute based on the workspace directory
                    input_files[idx]=input_files[idx].resolve()
                # check that the file exists
                if not Path( input_files[idx] ).exists():
                    self.logger.error(f"Input file {input_files[idx]} does not exist. Cannot open.")
                    return
                # print(f"Opening input file {input_files[idx]} in a new window")
                # child_window_id=self.add_window_to_menu()
                # self.open_windows[child_window_id].menuOpenFile.emit(input_file)
                self.openWindowFromFile.emit( str(input_files[idx]) )
                input_files[idx]=None
            
    def _ensureWindowActive(self):
        """Ensure window is active and menu bar is visible."""
        self.raise_()
        self.activateWindow()
        
        if sys.platform == 'darwin':
            self._refreshMenuBar()
        self.logger.debug("Window activated and raised")

    def _refreshMenuBar(self):
        """Force refresh of menu bar (macOS fix)."""
        menu_bar = self.menuBar()
        if menu_bar:
            menu_bar.setVisible(False)
            menu_bar.setVisible(True)
            menu_bar.update()
            # menu_bar.update()
            # menu_bar.repaint()
            
            # # Ensure all menus are visible
            # for action in menu_bar.actions():
            #     menu = action.menu()
            #     if menu:
            #         menu.setVisible(True)
            #         menu.update()
            self.logger.debug("Menu bar refreshed")

    def initUI(self):
        self.setWindowTitle("CWL editor")
        
        # Set the window icon
        icon_path = data.configuration.get('icons').get('cwllogo') 
        self.logger.info(f"Loading CWL Logo from {icon_path}")
        app_icon = QIcon(icon_path)
        self.setWindowIcon(app_icon)
        
        if app_icon.isNull():
            self.logger.warning(f"Could not load icon from {icon_path}")
        else:
            self.logger.info("CWL Logo loaded successfully")
        
        # Create the main menu
        self.menu=self.menuBar()
        self.setMenu()
        QApplication.instance().focusChanged.connect(self.set_active_child_window)
        
        # Create central widget with logo, app name, version and exit button
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add logo
        logo_label = QLabel()
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            # Scale the logo if needed
            scaled_pixmap = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)
        
        # Add app name
        app_name_label = QLabel("CWL Editor")
        app_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        app_name_label.setFont(font)
        layout.addWidget(app_name_label)
        
        # Add version
        version_label = QLabel(f"Version {version.__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        gnu_label= QLabel("""Copyright (C) 2026  K.Mavrommatis
    This program comes with 
    ABSOLUTELY NO WARRANTY; 
    for details check `COPYING` file. 
    This is free software, and you are welcome to 
    redistribute it under certain conditions.
        """)
        gnu_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(gnu_label)
        # Add some spacing
        layout.addSpacing(20)
        
        # add the location of the configuration file
        config_label=QLabel(f"""Configuration directory: 
        {user_config_path(appname='cwled')}""")
        config_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(config_label)
        layout.addSpacing(5) 
        log_label=QLabel(f"""Log directory:
        {user_log_path(appname='cwled')}""")
        log_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(log_label)
        # Add some spacing
        layout.addSpacing(10)   

        # Add tool creation buttons in a vertical layout
        tool_buttons_layout = QVBoxLayout()
        tool_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tool_buttons_layout.setSpacing(10)  # Add some spacing between buttons
        
        # Create CommandLineTool button
        cmd_tool_button = QPushButton("Create CommandLineTool")
        cmd_tool_button.clicked.connect(self.onMenuNewCommandTool)
        cmd_tool_button.setFixedWidth(250)  # Wider for better text display
        tool_buttons_layout.addWidget(cmd_tool_button)
        
        # Create ExpressionTool button
        expr_tool_button = QPushButton("Create ExpressionTool")
        expr_tool_button.clicked.connect(self.onMenuNewExpressionTool)
        expr_tool_button.setFixedWidth(250)  # Wider for better text display
        tool_buttons_layout.addWidget(expr_tool_button)
        
        # Create Workflow button
        workflow_button = QPushButton("Create Workflow")
        workflow_button.clicked.connect(self.onMenuNewWorkflow)
        workflow_button.setFixedWidth(250)  # Wider for better text display
        tool_buttons_layout.addWidget(workflow_button)
        
        # Create a horizontal layout for workspace buttons
        workspace_buttons_layout = QHBoxLayout()
        workspace_buttons_layout.setSpacing(10)  # Add some spacing between buttons
        
        # Create Open Workspace button
        workspace_button = QPushButton("Open Workspace")
        workspace_button.clicked.connect(self.onOpenWorkspace)
        workspace_button.setFixedWidth(188)  # Adjusted width to fit with the Set button
        workspace_buttons_layout.addWidget(workspace_button)
        
        # Create Set button
        set_workspace_button = QPushButton("Set")
        set_workspace_button.clicked.connect(self.onSetWorkspace)
        set_workspace_button.setFixedWidth(52)  # Smaller width for Set button
        workspace_buttons_layout.addWidget(set_workspace_button)
        
        # Add workspace buttons to the tool buttons layout
        tool_buttons_layout.addLayout(workspace_buttons_layout)
        
        # Add the tool buttons layout to the main layout
        layout.addLayout(tool_buttons_layout)
        
        # Add some spacing between tool buttons and exit button
        layout.addSpacing(10)
        
        # Add exit button
        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.close)
        exit_button.setFixedWidth(100)
        exit_button_layout = QHBoxLayout()
        exit_button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exit_button_layout.addWidget(exit_button)
        layout.addLayout(exit_button_layout)
        
        self.setCentralWidget(central_widget)
        

    def setupGlobalErrorDialogLogging(self):
        """Set up global error dialog logging for the entire application."""
        error_handler = ErrorDialogHandler(parent_window=self)
        error_handler.setLevel(logging.ERROR)
        
        # Add to root logger to catch all errors
        root_logger = logging.getLogger()
        root_logger.addHandler(error_handler)
        
        # Also ensure stderr output
        if not any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers):
            stderr_handler = logging.StreamHandler()
            stderr_handler.setLevel(logging.ERROR)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            stderr_handler.setFormatter(formatter)
            root_logger.addHandler(stderr_handler)


    
    @pyqtSlot(str)
    def onCreateWindowFromFile( self, input_file:str):
        '''
        Respond to a message to create new window from a file.
        If the file is already open in an existing window, bring that window forward.
        '''
        # Check if the file is already open in an existing window
        resolved_path = str(Path(input_file).resolve())
        for window in self.open_windows.values():
            if hasattr(window, 'file_path') and window.file_path:
                if str(Path(window.file_path).resolve()) == resolved_path:
                    window.raise_()
                    window.activateWindow()
                    return

        child_window_id=self.add_window_to_menu()
        # self.active_window.file_path=input_file
        self.open_windows[child_window_id].menuOpenFile.emit(input_file)
        
        # Add file to recent files and update the menu
        if data.configuration_manager:
            data.configuration_manager.addRecentFile(input_file)
            self.updateRecentMenu()

    def setMenu(self):
        '''
        set the menu in the main application
        '''
        file_open=QAction(  "&Open file ...",self)
        file_open.setShortcut(QKeySequence.StandardKey.Open)
        file_open.triggered.connect(self.onMenuOpenFile)
        file_save=QAction(  "&Save",self)
        file_save.setShortcut(QKeySequence.StandardKey.Save)
        file_save.triggered.connect(self.onMenuSaveFile)
        file_saveas=QAction(  "Save as ...",self)
        file_saveas.setShortcut(QKeySequence.StandardKey.SaveAs)
        file_saveas.triggered.connect(self.onMenuSaveAsFile)
        file_reload=QAction(  "Reload file",self)
        file_reload.setShortcut(QKeySequence.StandardKey.Refresh)
        file_reload.triggered.connect(self.onMenuReloadFile)
        # create a submenu for New
        

        tools_validate=QAction(  "Validate tool",self)
        tools_validate.triggered.connect(self.onMenuValidate)
        tools_maketemplate=QAction(  "Generate template",self)
        tools_maketemplate.triggered.connect(self.onMenuMakeTemplate)
        
        tools_upgrade=QAction(  "Upgrade CWL version",self)
        tools_upgrade.triggered.connect(self.onMenuUpgradeVersion)
        tools_pack_workflow=QAction(  "Pack workflow to single file",self)
        tools_pack_workflow.triggered.connect(self.onMenuPackWorkflow)
        tools_restructure_workflow=QAction(  "Repackage workflow with all tools",self)
        tools_restructure_workflow.triggered.connect(self.onMenuRestructureWorkflow)
        tools_save_documentation=QAction(  "Save workflow documentation",self)
        tools_save_documentation.triggered.connect(self.onMenuSaveDocumentation)
        tools_configuration=QAction( "Configuration",self)
        tools_configuration.setShortcut(QKeySequence.StandardKey.Preferences)
        tools_configuration.triggered.connect(self.onMenuConfiguration)
        tools_reset_configuration=QAction( "Reset configuration to default",self)
        tools_reset_configuration.triggered.connect(self.onMenuResetConfiguration)
        tools_draft_commandtool=QAction("Draft CommandLineTool from documentation", self)
        tools_draft_commandtool.triggered.connect(self.onMenuNewDraftCommandTool)

        tools_troubleshoot=QAction(  "Troubleshoot tool/workflow",self)
        tools_troubleshoot.triggered.connect(self.onMenuTroubleshooting)

        new_commandtool=QAction( "Command line tool", self)
        new_commandtool.triggered.connect(self.onMenuNewCommandTool)
        new_expressiontool=QAction("Expression tool", self)
        new_expressiontool.triggered.connect(self.onMenuNewExpressionTool)
        new_workflow=QAction("Workflow", self)
        new_workflow.triggered.connect(self.onMenuNewWorkflow)
        # Draft CommandLineTool placeholder action
        

        self.file_menu=self.menu.addMenu( "&File")
        self.file_menu.addAction( file_open )
        self.file_menu.addAction( file_save)
        self.file_menu.addAction( file_saveas )
        self.file_menu.addAction( file_reload )

        self.new_menu = QMenu("New", self)
        self.file_menu.addMenu(self.new_menu)
        self.new_menu.addAction( new_commandtool)
        self.new_menu.addAction( new_expressiontool)
        self.new_menu.addAction( new_workflow)
        self.new_menu.addSeparator()
        
        # Add Recent submenu
        self.recent_menu = QMenu("Recent", self)
        self.file_menu.addMenu(self.recent_menu)
        self.updateRecentMenu()
        

        self.tools_menu=self.menu.addMenu( "&Tools")
        self.tools_menu.addAction( tools_validate)
        self.tools_menu.addAction( tools_maketemplate)
        self.tools_menu.addAction( tools_pack_workflow)
        self.tools_menu.addAction( tools_restructure_workflow)
        self.tools_menu.addAction( tools_save_documentation)
        self.tools_menu.addAction( tools_upgrade)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction( tools_configuration)
        self.tools_menu.addAction( tools_reset_configuration)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction( tools_draft_commandtool)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction( tools_troubleshoot)
        
        self.window_menu=self.menu.addMenu("&Window")
        main_window_action = QAction("Main Window", self)
        main_window_action.triggered.connect(self._ensureWindowActive)
        self.window_menu.addAction(main_window_action)
        self.window_menu.addSeparator()
        
        # Help menu
        self.help_menu = self.menu.addMenu("&Help")
        help_user_guide = QAction("User Guide", self)
        help_user_guide.triggered.connect(self.onMenuHelp)
        self.help_menu.addAction(help_user_guide)

    def updateRecentMenu(self):
        """
        Update the Recent menu with the list of recently opened files.
        Shows up to 10 most recently opened files.
        Shows basename only if unique, or basename with parent directory if duplicates exist.
        """
        # Clear existing menu items
        self.recent_menu.clear()
        
        # Get recent files from configuration
        recent_files = data.configuration.get('recents', [])
        
        if not recent_files:
            # Show "No recent files" if the list is empty
            no_recent_action = QAction("No recent files", self)
            no_recent_action.setEnabled(False)
            self.recent_menu.addAction(no_recent_action)
        else:
            # Track files that need to be removed due to errors
            files_to_remove = []

            # Count how many times each basename appears to detect duplicates
            from collections import Counter
            valid_files = []
            for file_path in reversed(recent_files):
                try:
                    if Path(file_path).exists():
                        valid_files.append(file_path)
                    else:
                        files_to_remove.append(file_path)
                except (OSError, ValueError) as e:
                    self.logger.warning(f"Error accessing recent file {file_path}: {e}. Removing from recent files list.")
                    files_to_remove.append(file_path)

            basename_counts = Counter(Path(f).name for f in valid_files)

            # Add recent files (already in most-recent-first order)
            for file_path in valid_files:
                file_name = Path(file_path).name
                if basename_counts[file_name] > 1:
                    display_name = f"{file_name}  —  {Path(file_path).parent.name}"
                else:
                    display_name = file_name
                action = QAction(display_name, self)
                action.setToolTip(file_path)  # Show full path as tooltip
                action.triggered.connect(lambda checked, f=file_path: self.onOpenRecentFile(f))
                self.recent_menu.addAction(action)
            
            # Remove inaccessible files from the recent files list
            if files_to_remove:
                for file_path in files_to_remove:
                    if file_path in data.configuration['recents']:
                        data.configuration['recents'].remove(file_path)
                data.configuration_manager.saveConfiguration()
    
    def onOpenRecentFile(self, file_path:str):
        """
        Open a file from the recent files list.
        
        Args:
            file_path (str): Full path to the file to open.
        """
        try:
            if Path(file_path).exists():
                self.logger.info(f"Opening recent file {file_path}")
                self.onCreateWindowFromFile(file_path)
            else:
                self.logger.error(f"Recent file {file_path} no longer exists")
                QMessageBox.warning(self, "File Not Found", 
                                  f"The file {file_path} no longer exists.")
                # Remove the file from recent files list
                if file_path in data.configuration['recents']:
                    data.configuration['recents'].remove(file_path)
                    data.configuration_manager.saveConfiguration()
                    self.updateRecentMenu()  # Refresh the menu
        except (OSError, ValueError) as e:
            self.logger.error(f"Error accessing recent file {file_path}: {e}")
            QMessageBox.warning(self, "Error Opening File", 
                              f"Cannot access the file {file_path}:\n{str(e)}")
            # Remove the file from recent files list
            if file_path in data.configuration['recents']:
                data.configuration['recents'].remove(file_path)
                data.configuration_manager.saveConfiguration()
                self.updateRecentMenu()  # Refresh the menu
    
    def set_active_child_window(self, old, new):
        # Set the currently active child window
        any_window_active = False
        for window in self.open_windows.values():
            if window.isAncestorOf(new) or window == new:
                self.active_window = window
                any_window_active = True
                break
                
        if not any_window_active:
            self.logger.info("There does not seem to be any active window")
            self.active_window = None
        
        # Only log the window_id if we have an active window
        if self.active_window:
            self.logger.debug(f"Set the active window to {self.active_window.window_id}")
        else:
            self.logger.debug("No active window set")
    
    def add_window_to_menu(self, cwl_type:str='CommandLineTool'):

        window_id = len(self.open_windows) + 1
        child_window = ChildWindow(window_id=window_id, cwl_type=cwl_type, parent=self)
        
        # Set the same icon for the child window
        icon_path = data.configuration.get('icons').get('cwllogo') 
        app_icon = QIcon(icon_path)
        if not app_icon.isNull():
            child_window.setWindowIcon(app_icon)
        
        # Keep track of the window and show it
        self.open_windows[window_id] = child_window
        child_window.updateMenuSignal.connect(self.update_window_menu_entry)
        
        # Connect to the windowClosed signal to remove the window from the menu when closed
        child_window.windowClosed.connect(self.remove_window_from_menu)
        
        # Connect menu actions from child window to parent window handlers
        child_window.menuConfiguration.connect(self.onMenuConfiguration)
        
        # Add window to the window menu
        new_window=QAction(f"{window_id}: <{cwl_type}>", self)
        new_window.triggered.connect(lambda: self.onMenuFocus(window_id))
        self.window_menu.addAction(new_window)
        self.window_actions[window_id]=new_window
        
        # Show the window
        child_window.show()
        
        # Activate and raise the window to ensure it's in focus
        child_window.activateWindow()
        child_window.raise_()
        
        return(window_id)
        

    def update_window_menu_entry(self, window_id, new_name):
        if window_id in self.window_actions:
            self.logger.debug(f"Window {window_id} is in the list and its name will be updated to {new_name}")
            self.window_actions[window_id].setText(new_name)
        else:
            self.logger.warning(f"Window {window_id} is not in the list of windows")

    def remove_window_from_menu(self, window_id):
        # Remove the window entry from the Window menu
        if window_id in self.window_actions:
            self.logger.debug(f"Removing window {window_id} from the window menu")
            # Remove the action from the window menu
            self.window_menu.removeAction(self.window_actions[window_id])
            # Remove the action from our dictionary
            self.window_actions.pop(window_id, None)
        
        # Remove the closed window from the open windows dictionary
        self.open_windows.pop(window_id, None)
        
        # If this was the active window, set active_window to None
        if self.active_window and hasattr(self.active_window, 'window_id') and self.active_window.window_id == window_id:
            self.active_window = None

    def close_all_windows(self):
        # Close all child windows
        for window in list(self.open_windows.values()):
            if window:
                window.close()
        self.open_windows.clear()

    def onMenuNewExpressionTool(self):
        self.add_window_to_menu('ExpressionTool')

    def onMenuNewWorkflow(self):
        self.add_window_to_menu('Workflow')
        # self.setMenu()
        

    def onMenuNewCommandTool(self):
        '''
        create a new window for a command line tool
        '''
        self.add_window_to_menu('CommandLineTool')

    def onMenuNewDraftCommandTool(self):
        '''
        Open DraftTool dialog to generate a draft CommandLineTool via LLM.
        On accept, create a new CommandLineTool window and load the generated file.
        '''
  

        try:
            dialog = DraftTool(parent=self)
            result = dialog.exec()
            if result == QDialog.DialogCode.Accepted:
                # dialog.outfilename should contain generated file path (relative to CWD)
                out_file = getattr(dialog, 'outfilename', None)
                if out_file and Path(out_file).exists():
                    # Open new CommandLineTool window and load file
                    window_id = self.add_window_to_menu('CommandLineTool')
                    if window_id in self.open_windows:
                        self.open_windows[window_id].menuOpenFile.emit(str(Path(out_file).absolute()))
                else:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "Draft CommandLineTool", "No output file was produced or file missing.")
        # If rejected do nothing
        except Exception as e:
            self.logger.error(f"Error during Draft CommandLineTool creation: {e}")
            

    def onMenuFocus(self, window_id):
        if window_id in self.open_windows:
            self.open_windows[window_id].raise_()  # Bring the window to the front
            self.open_windows[window_id].activateWindow() 




    def onMenuValidate(self):
        '''
        validate a CWL tool or workflow using cwltool --validate or
        another command specified in the configuration file

        '''
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuValidate.emit()

    def onMenuConfiguration(self):
        """
        Open the configuration dialog to edit application settings.
        """
        self.logger.debug("Opening configuration dialog")
        
        from ConfigDialog import ConfigDialog
        dialog = ConfigDialog(self)
        
        # Show the dialog and process the result
        if (dialog.exec() == QDialog.DialogCode.Accepted):
            self.logger.info("Configuration updated")
            
            # Update logger levels for various components
            if hasattr(self, 'logger'):
                new_level = data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG')
                self.logger.setLevel(new_level)
                
            # Update logger levels for open windows
            for window in self.open_windows.values():
                if hasattr(window, 'logger'):
                    new_level = data.configuration.get('logLevel', {}).get(window.__class__.__name__, 'DEBUG')
                    window.logger.setLevel(new_level)

    def onMenuResetConfiguration(self):
        """
        Reset the configuration to the default values by reloading from the 
        original configuration file in the resources directory.
        """
        self.logger.debug("Resetting configuration to defaults")
        
        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "Reset Configuration",
            "Are you sure you want to reset the configuration to default values?\n\n"
            "This will overwrite your current settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from configuration import Configuration
                
                # Create a new Configuration instance pointing to the default config
                conf = Configuration(configuration_directory=data.config_directory)
                conf.resetConfigurationFile('cwled.yaml')
                
                self.logger.info("Configuration reset to defaults")
                QMessageBox.information(
                    self,
                    "Configuration Reset",
                    "Configuration has been reset to default values."
                )
                
                # Update logger levels
                if hasattr(self, 'logger'):
                    new_level = data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG')
                    self.logger.setLevel(new_level)
                    
            except Exception as e:
                self.logger.error(f"Failed to reset configuration: {e}")
                QMessageBox.critical(
                    self,
                    "Reset Failed",
                    f"Failed to reset configuration:\n{str(e)}"
                )

    def onMenuOpenFile(self):

        home_dir = str(data.workspace_directory) if hasattr(data, 'workspace_directory') else str(Path.home())
        fname=QFileDialog.getOpenFileName(
            self, 
            'Open file', 
            home_dir, 
            "*.txt;*.cwl;*.yaml;*.json")
        
        if fname[0]:
            self.logger.info(f"Opening file {fname[0]}")
            print(f"Opening file {fname[0]}")
            # self.file_path=fname[0]
            
            # self.pass_action_to_active_window("File Open")
            # if self.active_window:
            self.logger.info(f"Loading the file {fname[0]} to the current window")
            self.onCreateWindowFromFile( fname[0])
                # child_window_id=self.add_window_to_menu()
                # self.active_window.input_file=fname[0]
                # self.open_windows[child_window_id].menuOpenFile.emit(fname[0])
            # else:
                # print("No active window to load the file into, creating a new one")
            # self.loadCWL()
            # self.setWindowTitle( self.file_path)

    def onMenuSaveFile(self):
        # Invoke the Save As dialog if a file_path is not set
        # Otherwise save the file
        # if self.file_path:
        # self.saveFile(self.file_path, format)
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window.file_path :
            self.active_window.menuSaveFile.emit( 
                str(self.active_window.file_path) , 
                self.active_window.file_format
                )
        else:
            self.onMenuSaveAsFile()
        
    def onMenuSaveAsFile(self):
        # Invoke the Save As dialog
        # options = QFileDialog.Options()
        # options |= QFileDialog.Option.DontUseNativeDialog  # Optional: Use PyQt's dialog instead of the native OS one
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        else:
            aw=self.active_window
        # Use workspace directory by default, or fall back to existing file location or home directory
        if hasattr(data, 'workspace_directory'):
            home_dir = str(data.workspace_directory)
        elif self.active_window.file_path:
            home_dir = str(Path(self.active_window.file_path).parent)
        else:
            home_dir = str(Path.home())
            
        filters = "YAML (*.cwl);;YAML (*.yaml);;JSON (*.cwl);;JSON (*.json)"
        # Show the dialog and get the selected file path
        file_path, format = QFileDialog.getSaveFileName(
            self, 
            "Save As", 
            home_dir,  # Default directory or file name
            filters
        )
        if file_path:
            selected_format = 'YAML'
            selected_filter = (format or '').upper()
            suffix = Path(file_path).suffix.lower()

            if 'JSON' in selected_filter or suffix == '.json':
                selected_format = 'JSON'
            elif 'YAML' in selected_filter or suffix in ['.yaml', '.yml']:
                selected_format = 'YAML'

            aw.file_format = selected_format
            aw.menuSaveFile.emit(file_path, selected_format)
            
            # Add file to recent files list
            if data.configuration_manager:
                data.configuration_manager.addRecentFile(file_path)
                self.updateRecentMenu()
            
            return file_path
        
    def onMenuReloadFile(self):
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuReloadFile.emit()
    
    def onMenuUpgradeVersion(self):
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuUpgradeVersion.emit(None)
        
    def onMenuPackWorkflow(self):
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuPackWorkflow.emit(None)

    def onMenuRestructureWorkflow(self):
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuRestructureWorkflow.emit(None)

    def onMenuSaveDocumentation(self):
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuSaveDocumentation.emit()

    def onMenuMakeTemplate(self):
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            # print(f"Emitting signal for menu make template")
            self.active_window.menuMakeTemplate.emit()

    def onMenuTroubleshooting(self):
        """Handle the Troubleshoot tool/workflow menu action."""
        if not self.active_window:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return None
        if self.active_window:
            self.active_window.menuTroubleshoot.emit()

    def onMenuHelp(self):
        """
        Opens the User Guide in the system's default web browser.
        Converts the markdown documentation to HTML and displays it.
        """
        self.logger.debug("Opening User Guide")
        
        try:
            # Path to the User-guide.md file
            # Handle both development and packaged environments
            if getattr(sys, 'frozen', False):
                # Running in PyInstaller bundle
                base_path = Path(sys._MEIPASS)
            else:
                # Running in normal Python environment
                base_path = Path(__file__).parent.parent
            
            user_guide_path = base_path / 'docs' / 'User-guide.md'
            docs_dir = user_guide_path.parent
            
            if not user_guide_path.exists():
                self.logger.error(f"User guide not found at {user_guide_path}")
                QMessageBox.warning(
                    self,
                    "User Guide Not Found",
                    f"The user guide could not be found at:\n{user_guide_path}"
                )
                return
            
            # Read the markdown content
            with open(user_guide_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            # Convert markdown to HTML with extras for better formatting
            html_content = markdown2.markdown(
                markdown_content,
                extras=['tables', 'fenced-code-blocks', 'header-ids', 'code-friendly']
            )
            
            # Fix relative image paths to absolute file:// URLs
            import re
            def fix_image_path(match):
                src = match.group(1)
                # If it's a relative path (starts with ./ or just a filename)
                if not src.startswith(('http://', 'https://', 'file://')):
                    # Remove leading ./
                    src = src.lstrip('./')
                    # Create absolute path to image in docs directory
                    image_path = docs_dir / src
                    if image_path.exists():
                        return f'<img src="file://{image_path.absolute()}"'
                    else:
                        self.logger.warning(f"Image not found: {image_path}")
                return match.group(0)
            
            html_content = re.sub(r'<img src="([^"]+)"', fix_image_path, html_content)
            
            # Create styled HTML document
            styled_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>CWLed User Guide</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #fff;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-bottom: 1px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        h3 {{
            color: #555;
            margin-top: 20px;
        }}
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 0.9em;
            color: #c7254e;
        }}
        pre {{
            background-color: #f6f8fa;
            padding: 16px;
            border-radius: 6px;
            overflow-x: auto;
            border: 1px solid #e1e4e8;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            color: #24292e;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        blockquote {{
            border-left: 4px solid #3498db;
            margin: 20px 0;
            padding: 10px 20px;
            background-color: #f9f9f9;
        }}
        ul, ol {{
            padding-left: 30px;
        }}
        li {{
            margin: 8px 0;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            
            # Create a temporary HTML file
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
                f.write(styled_html)
                temp_path = f.name
            
            # Open in the default web browser
            webbrowser.open(f'file://{temp_path}')
            self.logger.info(f"Opened user guide in browser: {temp_path}")
            
        except Exception as e:
            self.logger.error(f"Error opening user guide: {e}")
            QMessageBox.critical(
                self,
                "Error Opening User Guide",
                f"An error occurred while opening the user guide:\n{str(e)}"
            )


    def onOpenWorkspace(self):
        """
        Opens the WorkspaceContents window to browse and select files from a workspace.
        Also adds the workspace window to the Window menu.
        If the workspace window is already open, brings it to the front.
        """
        self.logger.debug("Opening workspace browser")

        # If workspace window already exists and is visible, bring it forward
        workspace_id = "workspace"
        if workspace_id in self.open_windows:
            existing = self.open_windows[workspace_id]
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return

        workspace_path = data.workspace_directory if hasattr(data, 'workspace_directory') else str(Path.home())
        workspace_window = WorkspaceContents(workspace_path=workspace_path, parent=self)
        workspace_window.fileSelected.connect(self.onCreateWindowFromFile)
        workspace_window.show()
        workspace_window.activateWindow()
        workspace_window.raise_()

        # Add to open_windows and window menu
        workspace_id = "workspace"
        self.open_windows[workspace_id] = workspace_window
        workspace_action = QAction("Workspace", self)
        workspace_action.triggered.connect(lambda: workspace_window.raise_())
        self.window_menu.addAction(workspace_action)
        self.window_actions[workspace_id] = workspace_action

        # Remove menu entry when workspace window is closed
        def workspace_close_event(event):
            self.window_menu.removeAction(workspace_action)
            self.open_windows.pop(workspace_id, None)
            self.window_actions.pop(workspace_id, None)
            event.accept()
        workspace_window.closeEvent = workspace_close_event

    def onSetWorkspace(self):
        """
        Opens a directory dialog to set the workspace directory.
        This is equivalent to using the --workspace command line argument.
        """
        self.logger.debug("Setting workspace directory")
        
        # Get the current workspace directory if it exists
        current_dir = data.workspace_directory if hasattr(data, 'workspace_directory') else str(Path.home())
        
        # Open directory selection dialog
        new_workspace = QFileDialog.getExistingDirectory(
            self,
            "Select Workspace Directory",
            str(current_dir),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if new_workspace:
            # Convert to Path object for easier handling
            workspace_path = Path(new_workspace)
            
            # Store the workspace path in data module to make it available application-wide
            data.workspace_directory = str(workspace_path.absolute())
            self.logger.info(f"Set workspace directory to: {data.workspace_directory}")
            
            # Show a confirmation message
            message = f"\u2705 Workspace directory set successfully."
            details = f"The workspace directory has been changed to:\n{data.workspace_directory}"
            
            QMessageBox.information(
                self,
                "Workspace set",
                details
            )
            # dialog = QMessageBox.information(message, details, title="Workspace Set")
            
            # dialog.exec()

        os.chdir(str(data.workspace_directory))