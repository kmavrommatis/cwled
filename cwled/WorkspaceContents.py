from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTreeView, 
                            QDialogButtonBox, QPushButton, QLabel, QHBoxLayout, QLineEdit,
                            QApplication, QStyledItemDelegate, QStyle)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from pathlib import Path
import logging
import os, re
from CWLparser import Parser
from schema_salad.exceptions import ValidationException
import data

# Custom data roles for lazy loading
ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_IS_LOADED = Qt.ItemDataRole.UserRole + 1
ROLE_IS_DIRECTORY = Qt.ItemDataRole.UserRole + 2


class VersionColumnDelegate(QStyledItemDelegate):
    """Center Version column content (icon or text)."""

    def paint(self, painter, option, index):
        if index.column() != 1:
            super().paint(painter, option, index)
            return

        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())

        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""

        if icon:
            base = option.decorationSize if option.decorationSize.isValid() else QSize(20, 20)
            target_size = QSize(int(base.width() * 1.5), int(base.height() * 1.5 ))
            pixmap = icon.pixmap(target_size)
            x = option.rect.x() + (option.rect.width() - pixmap.width()) // 2
            y = option.rect.y() + option.rect.height() - pixmap.height()
            painter.drawPixmap(x, y, pixmap)
        else:
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))

        painter.restore()

class WorkspaceContents(QMainWindow):
    """
    A class that displays the contents of a workspace in a tree view.
    Shows all files with .cwl, .json, .yaml extensions in a tree structure.
    """
    fileSelected = pyqtSignal(str)  # Signal emitted when a file is selected
    
    def __init__(self, workspace_path=None, parent=None):
        """
        Initialize the workspace contents view.
        
        Args:
            workspace_path (str, optional): Path to the workspace directory
            parent (QWidget, optional): Parent widget
        """
        super().__init__(parent)
        
        # Set up logging
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG'))
        
        self.workspace_path = workspace_path

        # Unique window identifier
        self.window_id = "WorkspaceContents"
        
        self.initUI()
        
        # Populate tree if a workspace path was provided
        if workspace_path:
            self.populate_tree(workspace_path)
    
    def initUI(self):
        """Initialize the UI components"""
        self.setWindowTitle("Workspace Contents")
        self.resize(500, 600)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Add path label
        self.path_label = QLabel("Workspace: Not set")
        main_layout.addWidget(self.path_label)
        
        # Create tree view
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(False)
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        # Set icon size to 20x20 pixels
        self.tree_view.setIconSize(QSize(20, 20))
        
        # Create model with three columns: Name, Version, Date Modified
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Name', 'Version', 'Format', 'Date Modified'])
        self.tree_view.setModel(self.model)
        self.tree_view.setItemDelegateForColumn(1, VersionColumnDelegate(self.tree_view))
        self.tree_view.setSortingEnabled(True)
        self.tree_view.header().setSortIndicatorShown(True)
        self.tree_view.header().setSectionsClickable(True)
        self.tree_view.header().sectionClicked.connect(self.on_treeview_section_clicked)
        
        main_layout.addWidget(self.tree_view)
        
        # Add buttons at the bottom
        button_box = QDialogButtonBox()
        
        # Rescan button to refresh the workspace view
        rescan_btn = QPushButton("Rescan")
        rescan_btn.clicked.connect(self.on_rescan_clicked)
        button_box.addButton(rescan_btn, QDialogButtonBox.ButtonRole.ActionRole)
        
        # Open button to open selected file
        open_btn = QPushButton("Open Selected File")
        open_btn.clicked.connect(self.on_open_clicked)
        button_box.addButton(open_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_box.addButton(close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        
        main_layout.addWidget(button_box)

        # Sorting controls
        sort_layout = QHBoxLayout()
        self.sort_by_name_btn = QPushButton("Sort by Name (Asc)")
        self.sort_by_name_btn.clicked.connect(self.on_sort_by_name)
        sort_layout.addWidget(self.sort_by_name_btn)
        self.sort_by_time_btn = QPushButton("Sort by Date Modified (Asc)")
        self.sort_by_time_btn.clicked.connect(self.on_sort_by_time)
        sort_layout.addWidget(self.sort_by_time_btn)
        main_layout.addLayout(sort_layout)

        # Sorting state
        self.sort_mode = 'name'  # or 'time'
        self.sort_ascending = True

        # Resize the filename column to fit the longest name after population
        self.tree_view.header().setSectionResizeMode(0, self.tree_view.header().ResizeToContents)
        self.tree_view.header().setSectionResizeMode(1, self.tree_view.header().ResizeToContents)
        self.tree_view.header().setSectionResizeMode(2, self.tree_view.header().ResizeToContents)
        self.tree_view.header().setSectionResizeMode(3, self.tree_view.header().ResizeToContents)
        self.tree_view.expanded.connect(self._on_item_expanded)
        self.tree_view.collapsed.connect(lambda idx: self.tree_view.resizeColumnToContents(0))

        # Add search box and button
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search names...")
        search_layout.addWidget(self.search_box)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.on_search_clicked)
        self.search_box.returnPressed.connect(
            lambda: self.search_btn.click() if self.search_box.text().strip() else None
        )
        search_layout.addWidget(self.search_btn)
        self.cancel_search_btn = QPushButton("Clear")
        self.cancel_search_btn.clicked.connect(self.on_cancel_search_clicked)
        search_layout.addWidget(self.cancel_search_btn)
        main_layout.addLayout(search_layout)

        # Enable drag from tree view
        self.tree_view.setDragEnabled(True)
        self.tree_view.viewport().setAcceptDrops(False)
        self.tree_view.setSelectionMode(self.tree_view.SelectionMode.SingleSelection)
        # Install event filter for custom drag logic
        self.tree_view.viewport().installEventFilter(self)
    


    def eventFilter(self, source, event):
        # Custom drag logic: only allow files to be dragged
        if source == self.tree_view.viewport() and event.type() == event.Type.MouseMove:
            index = self.tree_view.indexAt(event.pos())
            item = self.model.itemFromIndex(index)
            if item:
                path = item.data(ROLE_PATH)
                if path and os.path.isfile(path):
                    from PyQt6.QtCore import QMimeData, QUrl
                    from PyQt6.QtGui import QDrag
                    mime_data = QMimeData()
                    mime_data.setUrls([QUrl.fromLocalFile(path)])
                    drag = QDrag(self.tree_view)
                    drag.setMimeData(mime_data)
                    drag.exec(Qt.DropAction.CopyAction)
                    return True
        return super().eventFilter(source, event)

  



    def populate_tree(self, path):
        """
        Populate the tree with the root directory and its immediate children.
        Uses lazy loading - subdirectories are loaded when expanded.
        
        Args:
            path (str): Path to the workspace directory
        """
        self.logger.debug(f"Populating tree with files from {path}")
        self.workspace_path = path
        self.path_label.setText(f"Workspace: {path}")
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Name', 'Version', 'Format', 'Date Modified'])
        root_path = Path(path)
        
        # Create root item
        root_item = QStandardItem(root_path.name)
        root_version_item = QStandardItem("")
        root_format_item = QStandardItem("")
        root_mtime = root_path.stat().st_mtime if root_path.exists() else None
        root_date_item = QStandardItem(self._format_mtime(root_mtime))
        root_item.setData(str(root_path), ROLE_PATH)
        root_item.setData(True, ROLE_IS_DIRECTORY)
        root_item.setData(False, ROLE_IS_LOADED)
        self.model.appendRow([root_item, root_version_item, root_format_item, root_date_item])
        
        # Load the root directory's immediate children
        self._load_directory_children(root_item, root_path)
        root_item.setData(True, ROLE_IS_LOADED)
        
        self.tree_view.expand(self.model.indexFromItem(root_item))
        self.tree_view.resizeColumnToContents(0)
    
    def _on_item_expanded(self, index):
        """
        Handle expansion of a tree item. Lazy loads children if not already loaded.
        
        Args:
            index (QModelIndex): Index of the expanded item.
        """
        item = self.model.itemFromIndex(index)
        if item and item.data(ROLE_IS_DIRECTORY) and not item.data(ROLE_IS_LOADED):
            # Remove placeholder and load actual children
            path = Path(item.data(ROLE_PATH))
            self.logger.debug(f"Lazy loading directory: {path}")
            
            # Show busy cursor during loading
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                # Clear placeholder children
                item.removeRows(0, item.rowCount())
                self._load_directory_children(item, path)
                item.setData(True, ROLE_IS_LOADED)
            finally:
                QApplication.restoreOverrideCursor()
        
        self.tree_view.resizeColumnToContents(0)
    
    def _load_directory_children(self, parent_item, dir_path):
        """
        Load the immediate children of a directory into the tree.
        Adds placeholder children to subdirectories for lazy loading.
        
        Args:
            parent_item (QStandardItem): The parent item in the tree.
            dir_path (Path): Path to the directory to load.
        """
        try:
            # Get all items in the directory
            items = list(dir_path.iterdir())
        except PermissionError as e:
            self.logger.warning(f"Permission denied accessing {dir_path}: {e}")
            return
        except OSError as e:
            self.logger.warning(f"Error accessing {dir_path}: {e}")
            return
        
        # Separate directories and files
        directories = []
        files = []
        
        for item_path in items:
            if item_path.is_dir() and not item_path.name.startswith('.'):
                # Check if directory contains any relevant files (recursively)
                if self._directory_has_cwl_files(item_path):
                    directories.append(item_path)
            elif item_path.is_file() and item_path.suffix in ['.cwl', '.json', '.yaml']:
                files.append(item_path)
        
        # Sort directories
        if self.sort_mode == 'name':
            directories.sort(key=lambda d: d.name.lower(), reverse=not self.sort_ascending)
        else:
            directories.sort(key=lambda d: d.stat().st_mtime, reverse=not self.sort_ascending)
        
        # Add directories with placeholder children for lazy loading
        for dir_item_path in directories:
            dir_item = QStandardItem(dir_item_path.name)
            dir_mtime = dir_item_path.stat().st_mtime if dir_item_path.exists() else None
            dir_date_item = QStandardItem(self._format_mtime(dir_mtime))
            dir_item.setData(str(dir_item_path), ROLE_PATH)
            dir_item.setData(True, ROLE_IS_DIRECTORY)
            dir_item.setData(False, ROLE_IS_LOADED)
            
            # Add a placeholder child so the expand arrow appears
            placeholder = QStandardItem("Loading...")
            dir_item.appendRow([placeholder, QStandardItem(""), QStandardItem(""), QStandardItem("")])
            
            parent_item.appendRow([dir_item, QStandardItem(""), QStandardItem(""), dir_date_item])
        
        # Sort files
        if self.sort_mode == 'name':
            files.sort(key=lambda f: f.name.lower(), reverse=not self.sort_ascending)
        else:
            files.sort(key=lambda f: f.stat().st_mtime, reverse=not self.sort_ascending)
        
        # Add files
        for file_path in files:
            try:
                c, cwl_version, file_format = self.getDocumentMetadata(file_path)
                self._add_file_item(parent_item, file_path, c, cwl_version, file_format)
            except Exception as e:
                self.logger.warning(f"Error parsing file {file_path}: {e}")
    
    def _directory_has_cwl_files(self, dir_path):
        """
        Check if a directory or its subdirectories contain any relevant files.
        
        Args:
            dir_path (Path): Path to the directory to check.
            
        Returns:
            bool: True if the directory contains .cwl, .json, or .yaml files.
        """
        try:
            for ext in ['.cwl', '.json', '.yaml']:
                # Use glob with limit to quickly check if any files exist
                for _ in dir_path.glob(f'**/*{ext}'):
                    return True
            return False
        except (PermissionError, OSError):
            return False
    
    def _add_file_item(self, parent_item, file_path, class_, cwl_version=None, file_format=None):
        """
        Add a file item to the tree.
        
        Args:
            parent_item (QStandardItem): The parent item in the tree.
            file_path (Path): Path to the file.
            class_ (str): The CWL class of the file (CommandLineTool, ExpressionTool, Workflow).
            cwl_version (str, optional): CWL version detected from file metadata.
            file_format (str, optional): File format ('JSON' or 'YAML').
        """
        file_item = QStandardItem(file_path.name)
        file_item.setData(str(file_path), ROLE_PATH)
        file_item.setData(False, ROLE_IS_DIRECTORY)
        tooltip = str(file_path)
        if class_:
            tooltip += f"\nClass: {class_}"
        if cwl_version:
            tooltip += f"\nCWL Version: {cwl_version}"
        file_item.setToolTip(tooltip)
        file_mtime = file_path.stat().st_mtime if file_path.exists() else None
        file_date_item = QStandardItem(self._format_mtime(file_mtime))
        version_item = self._make_version_item(cwl_version)
        format_item = QStandardItem(file_format or "")
        
        # Set the tool icon for the file
        icon_path = None
        if class_ in ['CommandLineTool', 'ExpressionTool']:
            icon_path = data.configuration.get('icons').get('tool') 
        elif class_ in ['Workflow']:
            icon_path = data.configuration.get('icons').get('workflow') 
        
        if icon_path and os.path.exists(icon_path):
            file_item.setIcon(QIcon(icon_path))
        elif icon_path:
            self.logger.warning(f"Icon file not found: {icon_path}")
            
        parent_item.appendRow([file_item, version_item, format_item, file_date_item])
    
    
    
    def add_file_to_tree(self, file_path, root_path, dir_nodes, class_, cwl_version=None, file_format=None):
        """
        Add a file to the tree view, creating directory nodes as needed.
        
        Args:
            file_path (Path): Path to the file
            root_path (Path): Root workspace path
            dir_nodes (dict): Dictionary mapping directory paths to tree nodes
        """
        # Get the relative path from the workspace root
        rel_path = file_path.relative_to(root_path)
        
        # Current parent is the root node
        current_path = root_path
        parent_item = dir_nodes[str(root_path)]
        
        # Create directory nodes along the path if they don't exist
        for part in rel_path.parts[:-1]:  # All parts except the filename
            current_path = current_path / part
            if str(current_path) not in dir_nodes:
                # Create a new directory node
                dir_item = QStandardItem(part)
                dir_mtime = current_path.stat().st_mtime if current_path.exists() else None
                dir_date_item = QStandardItem(self._format_mtime(dir_mtime))
                dir_item.setData(str(current_path), ROLE_PATH)
                parent_item.appendRow([dir_item, QStandardItem(""), QStandardItem(""), dir_date_item])
                dir_nodes[str(current_path)] = dir_item
            
            # Move to the next parent
            parent_item = dir_nodes[str(current_path)]
        
        # Add the file as a leaf node with an icon
        file_item = QStandardItem(rel_path.name)
        file_item.setData(str(file_path), ROLE_PATH)
        file_item.setToolTip(str(file_path))
        file_mtime = file_path.stat().st_mtime if file_path.exists() else None
        file_date_item = QStandardItem(self._format_mtime(file_mtime))
        
        # Set the tool icon for the file
        icon_path = None
        if class_ in ['CommandLineTool', 'ExpressionTool']:
            icon_path = data.configuration.get('icons').get('tool') 
        elif class_ in ['Workflow']:
            icon_path = data.configuration.get('icons').get('workflow') 
        
        if icon_path and os.path.exists(icon_path):
            file_item.setIcon(QIcon(icon_path))
        elif icon_path:
            self.logger.warning(f"Icon file not found: {icon_path}")
            
        version_item = self._make_version_item(cwl_version)
        format_item = QStandardItem(file_format or "")
        parent_item.appendRow([file_item, version_item, format_item, file_date_item])

    def _make_version_item(self, cwl_version):
        """Build the CWL Version cell with icon fallback to text."""
        version_item = QStandardItem("")
        if not cwl_version:
            return version_item

        iconv_path = data.configuration.get('icons', {}).get(cwl_version)
        if iconv_path and os.path.exists(iconv_path):
            version_item.setIcon(QIcon(iconv_path))
            version_item.setToolTip(cwl_version)
        else:
            version_item.setText(cwl_version)
            version_item.setToolTip(cwl_version)

        return version_item

    def _format_mtime(self, mtime):
        """
        Format a modification time (timestamp) as a string.

        Args:
            mtime (float or None): Modification time as a Unix timestamp.

        Returns:
            str: Formatted date string, or empty string if mtime is None.
        """
        if mtime is None:
            return ""
        import datetime
        dt = datetime.datetime.fromtimestamp(mtime)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def on_item_double_clicked(self, index):
        """
        Handle double-click on a tree item. Emits the fileSelected signal if a file is selected.

        Args:
            index (QModelIndex): Index of the clicked item.
        """
        item = self.model.itemFromIndex(index)
        if item:
            path = item.data(ROLE_PATH)
            if path and os.path.isfile(path):
                self.logger.debug(f"File selected: {path}")
                self.fileSelected.emit(path)
                # self.close()
    
    def on_open_clicked(self):
        """
        Handle click on the Open button. Emits the fileSelected signal if a file is selected.
        """
        selected_indexes = self.tree_view.selectedIndexes()
        if selected_indexes:
            item = self.model.itemFromIndex(selected_indexes[0])
            path = item.data(ROLE_PATH)
            if path and os.path.isfile(path):
                self.logger.debug(f"Opening file: {path}")
                self.fileSelected.emit(path)
                # self.close()
    
    def on_rescan_clicked(self):
        """
        Handle click on the Rescan button by refreshing the file tree.
        """
        if self.workspace_path:
            self.logger.debug(f"Rescanning workspace: {self.workspace_path}")
            self.populate_tree(self.workspace_path)
        else:
            self.logger.warning("Cannot rescan - no workspace path set")

    def on_sort_by_name(self):
        """
        Sort the tree view by file/directory name, toggling ascending/descending order.
        """
        self.sort_mode = 'name'
        self.sort_ascending = not self.sort_ascending
        order = "Asc" if self.sort_ascending else "Desc"
        self.sort_by_name_btn.setText(f"Sort by Name ({order})")
        self.sort_by_time_btn.setText(
            "Sort by Date Modified (Asc)" if self.sort_mode != 'time' else self.sort_by_time_btn.text()
        )
        if self.workspace_path:
            self.populate_tree(self.workspace_path)

    def on_sort_by_time(self):
        """
        Sort the tree view by date modified, toggling ascending/descending order.
        """
        self.sort_mode = 'time'
        self.sort_ascending = not self.sort_ascending
        order = "Asc" if self.sort_ascending else "Desc"
        self.sort_by_time_btn.setText(f"Sort by Date Modified ({order})")
        self.sort_by_name_btn.setText(
            "Sort by Name (Asc)" if self.sort_mode != 'name' else self.sort_by_name_btn.text()
        )
        if self.workspace_path:
            self.populate_tree(self.workspace_path)

    def on_treeview_section_clicked(self, logicalIndex):
        """
        Handle sorting when a column header is clicked.

        Args:
            logicalIndex (int): 0 for Name, 1 for Version, 2 for Format, 3 for Date Modified.
        """
        # Toggle sort order if the same column is clicked again
        if logicalIndex == 0:
            self.on_sort_by_name()
        elif logicalIndex == 3:
            self.on_sort_by_time()

    def on_search_clicked(self):
        """
        Handle click on the Search button. Filters the tree view by the search string.
        """
        search_text = self.search_box.text().strip().lower()
        if not search_text:
            # Show all items
            if self.workspace_path:
                self.populate_tree(self.workspace_path)
            return
        # Filter items by search text
        self.filter_tree_by_name(search_text)

    def on_cancel_search_clicked(self):
        """
        Handle click on the Cancel button. Clears the search box and shows all files.
        """
        self.search_box.clear()
        if self.workspace_path:
            self.populate_tree(self.workspace_path)

    def filter_tree_by_name(self, search_text):
        """
        Filter the tree view to show only items matching the search string.
        Note: Search does a full scan and doesn't use lazy loading.

        Args:
            search_text (str): The string to search for in file and directory names.
        """
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Name', 'Version', 'Format', 'Date Modified'])
        root_path = Path(self.workspace_path)
        root_item = QStandardItem(root_path.name)
        root_version_item = QStandardItem("")
        root_format_item = QStandardItem("")
        root_mtime = root_path.stat().st_mtime if root_path.exists() else None
        root_date_item = QStandardItem(self._format_mtime(root_mtime))
        root_item.setData(str(root_path), ROLE_PATH)
        self.model.appendRow([root_item, root_version_item, root_format_item, root_date_item])
        dir_nodes = {str(root_path): root_item}
        # Gather all files and directories
        all_files = []
        all_dirs = set()
        for ext in ['.cwl', '.json', '.yaml']:
            try:
                for file_path in root_path.glob(f'**/*{ext}'):
                    all_files.append(file_path)
                    for parent in file_path.parents:
                        if parent != root_path and str(parent).startswith(str(root_path)):
                            all_dirs.add(parent)
            except OSError as e:
                raise Exception(f"Error accessing files with {ext} extension: {e}")
        # Sort directories
        sorted_dirs = sorted(all_dirs, key=lambda d: str(d).lower(), reverse=not self.sort_ascending)
        # Add matching directories
        for dir_path in sorted_dirs:
            rel_path = dir_path.relative_to(root_path)
            current_path = root_path
            parent_item = dir_nodes[str(root_path)]
            for part in rel_path.parts:
                current_path = current_path / part
                if str(current_path) not in dir_nodes:
                    if search_text in part.lower():
                        dir_item = QStandardItem(part)
                        dir_mtime = current_path.stat().st_mtime if current_path.exists() else None
                        dir_date_item = QStandardItem(self._format_mtime(dir_mtime))
                        dir_item.setData(str(current_path), ROLE_PATH)
                        parent_item.appendRow([dir_item, QStandardItem(""), QStandardItem(""), dir_date_item])
                        dir_nodes[str(current_path)] = dir_item
                    else:
                        dir_nodes[str(current_path)] = parent_item
                parent_item = dir_nodes[str(current_path)]
        # Sort files
        if self.sort_mode == 'name':
            all_files.sort(key=lambda f: f.name.lower(), reverse=not self.sort_ascending)
        else:
            all_files.sort(key=lambda f: f.stat().st_mtime, reverse=not self.sort_ascending)
        # Add matching files
        for file_path in all_files:
            if search_text in file_path.name.lower():
                try:
                    c, cwl_version, file_format = self.getDocumentMetadata(file_path)
                    self.add_file_to_tree(file_path, root_path, dir_nodes, c, cwl_version, file_format)
                except Exception as e:
                    self.logger.warning(f"Error parsing file: {e}")
        self.tree_view.expand(self.model.indexFromItem(root_item))
        self.tree_view.resizeColumnToContents(0)

    def getDocumentMetadata(self, file_path):
        """
        Lightweight metadata scan to detect document class and CWL version.

        Returns:
            tuple[str|None, str|None, str]: (class, cwl_version, file_format)
        """
        valid_classes = {'CommandLineTool', 'ExpressionTool', 'Workflow'}
        class_ = None
        cwl_version = None
        ext = Path(file_path).suffix.lower()
        file_format = 'JSON' if ext == '.json' else 'YAML'

        class_pattern = re.compile(r'^\s*["\']?class["\']?\s*:\s*["\']?([A-Za-z]+)["\']?')
        version_pattern = re.compile(r'^\s*["\']?cwlVersion["\']?\s*:\s*["\']?([^"\'\s#,]+)["\']?')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if class_ is None:
                        class_match = class_pattern.search(line)
                        if class_match:
                            candidate = class_match.group(1)
                            if candidate in valid_classes:
                                class_ = candidate

                    if cwl_version is None:
                        version_match = version_pattern.search(line)
                        if version_match:
                            cwl_version = version_match.group(1)

                    if class_ is not None and cwl_version is not None:
                        break
        except Exception as e:
            self.logger.error(f"Error reading file {file_path}: {e}")

        return class_, cwl_version, file_format

    def getDocumentClass(self, file_path):
        """
        Scan a file for a line matching 'class: <value>' where value is CommandLineTool, ExpressionTool, or Workflow.
        Returns the value if found, else None.

        Args:
            file_path (str or Path): Path to the file to scan.

        Returns:
            str or None: The class value if found, otherwise None.
        """
        class_, _, _ = self.getDocumentMetadata(file_path)
        return class_


