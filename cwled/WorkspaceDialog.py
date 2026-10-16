"""
Dialogs for choosing a workspace on this machine or on an SSH server.

Also holds the shared connect flow (host-key trust and password prompts) and a
remote file/folder picker used wherever a native file dialog would only see
the local disk.
"""

import datetime
import logging
import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
                             QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                             QStyle, QTabWidget, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)
from upath import UPath

import data
import remote
from configuration import Configuration
from remote import SSHProfile

logger = logging.getLogger(__name__)

CWL_EXTENSIONS = ('.cwl', '.json', '.yaml')
ROLE_URI = Qt.ItemDataRole.UserRole
ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1
ROLE_LOADED = Qt.ItemDataRole.UserRole + 2


def connect_with_prompts(parent: Optional[QWidget], profile: SSHProfile,
                         password: Optional[str] = None,
                         passphrase: Optional[str] = None) -> Optional[UPath]:
    """
    Connect to a profile, asking the user to trust host keys and enter secrets.

    Unknown host keys are shown with their SHA256 fingerprint and only trusted on
    explicit confirmation. Changed host keys are refused. When the connection
    fails the user is asked for the password (or key passphrase) and may retry;
    cancelling gives up.

    Args:
        parent (QWidget, optional): parent for the message boxes.
        profile (SSHProfile): where to connect.
        password (str, optional): password already known.
        passphrase (str, optional): key passphrase already known.

    Returns:
        UPath | None: the remote root, or None if the user gave up.
    """
    while True:
        try:
            return remote.connect(profile, password=password, passphrase=passphrase)
        except remote.UnknownHostKeyError as exc:
            answer = QMessageBox.question(
                parent,
                "Trust host key?",
                f"{exc.hostname} presented a host key that is not yet trusted.\n\n"
                f"Fingerprint: {exc.fingerprint}\n\n"
                "Only trust this key if you recognise it. Trust it and connect?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            remote.trust_host_key(exc.hostname, exc.key)
        except remote.HostKeyMismatchError as exc:
            QMessageBox.critical(
                parent,
                "Host key changed",
                f"{exc}\n\nThe server may have been reinstalled, or the connection may be "
                "intercepted. Connection refused.",
            )
            return None
        except remote.RemoteError as exc:
            secret, ok = QInputDialog.getText(
                parent,
                "Authentication required",
                f"Connection to {profile.authority} failed:\n{exc}\n\n"
                "Enter the password (or the passphrase of the key):",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not secret:
                return None
            if profile.key_path:
                passphrase = secret
            else:
                password = secret


def _format_time(mtime: Optional[float]) -> str:
    """Modification time for display, blank when unknown."""
    if mtime is None:
        return ""
    return datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')


def _remote_folder(root: UPath, folder: str) -> UPath:
    """`root` joined with a folder given as an absolute POSIX path such as '/data/x'."""
    relative = folder.strip().strip('/')
    return root / relative if relative else root


class RemoteFileDialog(QDialog):
    """
    Pick a folder, or a workflow file, on a remote server.

    Folders expand lazily. In 'open' mode workflow files are selectable, in
    'save' mode a file name is typed, and in 'folder' mode only folders show.

    Attributes:
        result_uri (str | None): the chosen location once the dialog is accepted.
    """

    def __init__(self, parent: Optional[QWidget], root: UPath, mode: str,
                 default_name: str = ""):
        super().__init__(parent)
        if mode not in ('open', 'save', 'folder'):
            raise ValueError(f"Unknown mode {mode}")
        self.root = root
        self.mode = mode
        self.result_uri: Optional[str] = None
        self.setWindowTitle({'open': 'Open remote file',
                             'save': 'Save remote file',
                             'folder': 'Choose remote folder'}[mode])
        self.resize(560, 480)

        style = self.style()
        self._folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self._file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Server: {remote.to_uri(root)}"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Modified"])
        self.tree.setColumnWidth(0, 340)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)

        self.name_edit = None
        if mode == 'save':
            row = QHBoxLayout()
            row.addWidget(QLabel("File name:"))
            self.name_edit = QLineEdit(default_name)
            row.addWidget(self.name_edit)
            layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill(None, root)

    def _list(self, folder: UPath):
        """List a folder with a busy cursor, reporting failures to the user."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return remote.list_entries(folder)
        except Exception as exc:
            logger.error(f"Could not list {remote.to_uri(folder)}: {exc}")
            QMessageBox.warning(self, "Could not list folder", f"{remote.to_uri(folder)}\n\n{exc}")
            return []
        finally:
            QApplication.restoreOverrideCursor()

    def _fill(self, parent_item: Optional[QTreeWidgetItem], folder: UPath):
        """Add the folder's visible children under `parent_item` (or at the top level)."""
        entries = self._list(folder)
        if parent_item is None:
            self.tree.clear()
        else:
            parent_item.takeChildren()
        for entry in sorted(entries, key=lambda e: (not e.is_dir, e.path.name.lower())):
            name = entry.path.name
            if name.startswith('.'):
                continue
            if not entry.is_dir and (self.mode == 'folder' or not name.endswith(CWL_EXTENSIONS)):
                continue
            child = QTreeWidgetItem([name, _format_time(entry.mtime)])
            child.setData(0, ROLE_URI, remote.to_uri(entry.path))
            child.setData(0, ROLE_IS_DIR, entry.is_dir)
            child.setData(0, ROLE_LOADED, False)
            if entry.is_dir:
                child.setIcon(0, self._folder_icon)
                child.addChild(QTreeWidgetItem(["Loading..."]))
            else:
                child.setIcon(0, self._file_icon)
            if parent_item is None:
                self.tree.addTopLevelItem(child)
            else:
                parent_item.addChild(child)

    def _on_expanded(self, item: QTreeWidgetItem):
        """Load a folder's children the first time it is expanded."""
        if item.data(0, ROLE_LOADED):
            return
        item.setData(0, ROLE_LOADED, True)
        self._fill(item, remote.to_path(item.data(0, ROLE_URI)))

    def _on_double_click(self, item: QTreeWidgetItem, _column: int):
        """Double-clicking a file in open or save mode chooses it."""
        if self.mode in ('open', 'save') and not item.data(0, ROLE_IS_DIR):
            self.tree.setCurrentItem(item)
            self._on_accept()

    def _on_accept(self):
        """Resolve the chosen location for the current mode and close the dialog."""
        item = self.tree.currentItem()
        is_folder = bool(item.data(0, ROLE_IS_DIR)) if item is not None else True

        if self.mode == 'folder':
            self.result_uri = item.data(0, ROLE_URI) if item is not None and is_folder else remote.to_uri(self.root)
            self.accept()
            return

        if self.mode == 'open':
            if item is None or is_folder:
                QMessageBox.information(self, "Choose a file", "Select a workflow or tool file to open.")
                return
            self.result_uri = item.data(0, ROLE_URI)
            self.accept()
            return

        # save: the selected folder (or the folder holding the selected file) plus the typed name
        name = self.name_edit.text().strip() if self.name_edit is not None else ""
        if not name:
            QMessageBox.information(self, "Name required", "Type a file name to save.")
            return
        if item is None:
            folder_uri = remote.to_uri(self.root)
        elif is_folder:
            folder_uri = item.data(0, ROLE_URI)
        else:
            folder_uri = remote.to_uri(remote.to_path(item.data(0, ROLE_URI)).parent)
        self.result_uri = folder_uri.rstrip('/') + '/' + name
        self.accept()


def choose_remote_path(parent: Optional[QWidget], workspace_uri: str, mode: str,
                       default_name: str = "") -> Optional[str]:
    """
    Show the remote picker rooted at the server of an open workspace.

    Args:
        parent (QWidget, optional): parent window.
        workspace_uri (str): an sftp:// URI on the connected server.
        mode (str): 'open', 'save' or 'folder'.
        default_name (str): file name pre-filled in save mode.

    Returns:
        str | None: the chosen sftp:// URI, or None if cancelled.
    """
    root = remote.to_path(workspace_uri)
    if not isinstance(root, UPath):
        raise ValueError(f"{workspace_uri} is not a remote location")
    dialog = RemoteFileDialog(parent, root, mode, default_name)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.result_uri
    return None


class WorkspaceDialog(QDialog):
    """
    Choose the workspace: a local folder, or a folder on an SSH server.

    Remote options are an ~/.ssh/config host, host + key, or host + password.
    Secrets are typed each time and never written to disk.

    Attributes:
        result_workspace (str | None): local path or sftp:// URI chosen.
        result_profile (SSHProfile | None): connection profile for a remote choice.
    """

    LOCAL, SSH_CONFIG, KEY, PASSWORD = range(4)

    def __init__(self, parent: Optional[QWidget], current: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Select Workspace")
        self.resize(560, 400)
        self.result_workspace: Optional[str] = None
        self.result_profile: Optional[SSHProfile] = None
        self._root: Optional[UPath] = None
        self._root_profile: Optional[SSHProfile] = None
        self._ssh_aliases = remote.list_ssh_config_aliases()  # names only; options resolved on selection

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_local_tab(current), "Local folder")
        self.tabs.addTab(self._build_ssh_config_tab(), "SSH config host")
        self.tabs.addTab(self._build_key_tab(), "SSH key")
        self.tabs.addTab(self._build_password_tab(), "Password")
        layout.addWidget(self.tabs)

        remote_row = QHBoxLayout()
        remote_row.addWidget(QLabel("Remote folder:"))
        self.remote_folder = QLineEdit("/")
        remote_row.addWidget(self.remote_folder)
        self.remote_browse = QPushButton("Browse...")
        self.remote_browse.clicked.connect(self._browse_remote)
        remote_row.addWidget(self.remote_browse)
        layout.addLayout(remote_row)
        self.tabs.currentChanged.connect(self._update_remote_row)
        self._update_remote_row()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # tab builders -------------------------------------------------------

    def _build_local_tab(self, current: str) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        start = current if current and not remote.is_remote(current) else os.path.expanduser("~")
        self.local_edit = QLineEdit(start)
        row.addWidget(self.local_edit)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_local)
        row.addWidget(browse)
        return page

    def _build_ssh_config_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.alias_combo = QComboBox()
        for alias in self._ssh_aliases:
            self.alias_combo.addItem(alias, alias)
        if not self._ssh_aliases:
            self.alias_combo.addItem("No Host entries found in ~/.ssh/config")
            self.alias_combo.setEnabled(False)
        self.alias_details = QLabel("")
        self.alias_combo.currentIndexChanged.connect(self._show_alias_details)
        form.addRow("Host:", self.alias_combo)
        form.addRow("Resolved:", self.alias_details)
        form.addRow(QLabel("The password or key passphrase is asked when connecting."))
        self._show_alias_details()
        return page

    def _build_key_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.key_host = QLineEdit()
        self.key_port = QSpinBox()
        self.key_port.setRange(1, 65535)
        self.key_port.setValue(remote.DEFAULT_PORT)
        self.key_user = QLineEdit()
        self.key_path = QLineEdit(os.path.expanduser("~/.ssh/id_ed25519"))
        self.key_passphrase = QLineEdit()
        self.key_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_passphrase.setPlaceholderText("Only if the key is encrypted (not saved)")
        form.addRow("Host:", self.key_host)
        form.addRow("Port:", self.key_port)
        form.addRow("User name:", self.key_user)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_path)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_key)
        key_row.addWidget(browse)
        form.addRow("Private key:", key_row)
        form.addRow("Passphrase:", self.key_passphrase)
        return page

    def _build_password_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.pw_host = QLineEdit()
        self.pw_port = QSpinBox()
        self.pw_port.setRange(1, 65535)
        self.pw_port.setValue(remote.DEFAULT_PORT)
        self.pw_user = QLineEdit()
        self.pw_password = QLineEdit()
        self.pw_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_password.setPlaceholderText("Not saved")
        form.addRow("Host:", self.pw_host)
        form.addRow("Port:", self.pw_port)
        form.addRow("User name:", self.pw_user)
        form.addRow("Password:", self.pw_password)
        return page

    # helpers ------------------------------------------------------------

    def _show_alias_details(self, *_):
        """Resolve only the selected alias, for display."""
        alias = self.alias_combo.currentData()
        if not alias:
            self.alias_details.setText("")
            return
        host = remote.resolve_ssh_config_host(alias)
        if host is None:
            self.alias_details.setText("not available")
            return
        user = host.username or "(local user)"
        self.alias_details.setText(f"{user}@{host.hostname}:{host.port}")

    def _update_remote_row(self):
        """The remote folder row only applies to the remote tabs."""
        is_remote_tab = self.tabs.currentIndex() != self.LOCAL
        self.remote_folder.setEnabled(is_remote_tab)
        self.remote_browse.setEnabled(is_remote_tab)

    def _browse_local(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Workspace Directory", self.local_edit.text())
        if folder:
            self.local_edit.setText(folder)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", os.path.dirname(self.key_path.text()))
        if path:
            self.key_path.setText(path)

    def _current_profile(self) -> Optional[SSHProfile]:
        """The profile for the active remote tab, or None if its fields are incomplete."""
        index = self.tabs.currentIndex()
        if index == self.SSH_CONFIG:
            alias = self.alias_combo.currentData()
            if alias is None:
                return None
            host = remote.resolve_ssh_config_host(alias)
            if host is None:
                QMessageBox.warning(self, "Not available", f"{alias} could not be read from ~/.ssh/config.")
                return None
            try:
                return host.to_profile()
            except remote.RemoteError as exc:
                QMessageBox.warning(self, "Not supported", str(exc))
                return None
        if index == self.KEY:
            host, user = self.key_host.text().strip(), self.key_user.text().strip()
            if not host or not user:
                return None
            return SSHProfile(name=host, host=host, username=user, port=self.key_port.value(),
                              key_path=self.key_path.text().strip() or None)
        if index == self.PASSWORD:
            host, user = self.pw_host.text().strip(), self.pw_user.text().strip()
            if not host or not user:
                return None
            return SSHProfile(name=host, host=host, username=user, port=self.pw_port.value())
        return None

    def _typed_secrets(self) -> tuple[Optional[str], Optional[str]]:
        """(password, passphrase) typed in the active tab. Used once, never saved."""
        if self.tabs.currentIndex() == self.KEY:
            return None, self.key_passphrase.text() or None
        if self.tabs.currentIndex() == self.PASSWORD:
            return self.pw_password.text() or None, None
        return None, None

    def _ensure_connected(self) -> Optional[UPath]:
        """Connect the active remote tab unless this same profile is already connected here."""
        profile = self._current_profile()
        if profile is None:
            QMessageBox.information(self, "Incomplete", "Fill in the host and user name first.")
            return None
        if self._root is not None and profile == self._root_profile:
            return self._root
        password, passphrase = self._typed_secrets()
        root = connect_with_prompts(self, profile, password=password, passphrase=passphrase)
        if root is not None:
            self._root, self._root_profile = root, profile
        return root

    def _browse_remote(self):
        root = self._ensure_connected()
        if root is None:
            return
        chosen = choose_remote_path(self, remote.to_uri(_remote_folder(root, self.remote_folder.text())), 'folder')
        if chosen:
            self.remote_folder.setText(remote.to_path(chosen).path)

    def _on_accept(self):
        """Validate the active tab and set the result."""
        if self.tabs.currentIndex() == self.LOCAL:
            folder = self.local_edit.text().strip()
            if not folder:
                QMessageBox.information(self, "Folder required", "Choose a local folder.")
                return
            os.makedirs(folder, exist_ok=True)
            self.result_workspace = os.path.abspath(folder)
            self.result_profile = None
            self.accept()
            return

        root = self._ensure_connected()
        if root is None:
            return
        target = _remote_folder(root, self.remote_folder.text())
        try:
            if not target.is_dir():
                QMessageBox.warning(self, "Not a folder", f"{remote.to_uri(target)} is not a folder on the server.")
                return
        except Exception as exc:
            QMessageBox.warning(self, "Could not check folder", str(exc))
            return
        self.result_workspace = remote.to_uri(target)
        self.result_profile = self._root_profile
        self.accept()


def open_workspace_dialog(parent: Optional[QWidget], current: str = "") -> Optional[WorkspaceDialog]:
    """
    Run the workspace dialog and return it when the user accepted a choice.

    Args:
        parent (QWidget, optional): parent window.
        current (str): the current workspace, used to pre-fill the local tab.

    Returns:
        WorkspaceDialog | None: the dialog with results set, or None if cancelled.
    """
    dialog = WorkspaceDialog(parent, current)
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_workspace:
        return dialog
    return None


def restore_remote_workspace(workspace_uri: str) -> Optional[str]:
    """
    Reconnect to the remote workspace saved in the configuration at startup.

    Secrets are asked for if the saved key or ssh config does not authenticate
    on its own.

    Args:
        workspace_uri (str): the saved sftp:// workspace URI.

    Returns:
        str | None: the URI when the connection and folder are available, else None.
    """
    profile_data = data.configuration.get('workspace_profile')
    if not profile_data:
        logger.warning(f"No connection profile is saved for the remote workspace {workspace_uri}")
        return None
    profile = SSHProfile.from_dict(profile_data)
    if connect_with_prompts(None, profile) is None:
        return None
    try:
        if not remote.to_path(workspace_uri).is_dir():
            logger.warning(f"Remote workspace {workspace_uri} is not a folder on the server")
            return None
    except Exception:
        logger.exception(f"Could not check the remote workspace {workspace_uri}")
        return None
    return workspace_uri


def workspace_is_remote() -> bool:
    """True when the open workspace lives on an SSH server."""
    return remote.is_remote(data.workspace_directory)


def ask_open_file(parent: Optional[QWidget], caption: str, start_dir: str, name_filter: str) -> Optional[str]:
    """
    Ask for a file to open, on the local disk or on the remote workspace server.

    Args:
        parent (QWidget, optional): parent window.
        caption (str): dialog title.
        start_dir (str): starting folder for local dialogs.
        name_filter (str): Qt name filter for local dialogs.

    Returns:
        str | None: the local path or sftp:// URI, or None if cancelled.
    """
    if workspace_is_remote():
        return choose_remote_path(parent, data.workspace_directory, 'open')
    path, _ = QFileDialog.getOpenFileName(parent, caption, start_dir, name_filter)
    return path or None


def ask_save_file(parent: Optional[QWidget], caption: str, start_dir: str,
                  default_name: str, name_filter: str) -> tuple[Optional[str], str]:
    """
    Ask where to save a file, on the local disk or on the remote workspace server.

    Args:
        parent (QWidget, optional): parent window.
        caption (str): dialog title.
        start_dir (str): starting folder for local dialogs.
        default_name (str): suggested file name.
        name_filter (str): Qt name filter for local dialogs.

    Returns:
        tuple[str | None, str]: (path or sftp:// URI or None, selected filter).
            Remote saves return an empty filter; callers should use the suffix.
    """
    if workspace_is_remote():
        return choose_remote_path(parent, data.workspace_directory, 'save', default_name), ''
    path, selected = QFileDialog.getSaveFileName(parent, caption, start_dir, name_filter)
    return path or None, selected


def persist_workspace(workspace: str, profile: Optional[SSHProfile]) -> None:
    """
    Remember the workspace (and its non-secret connection profile) in cwled.yaml.

    Args:
        workspace (str): local path or sftp:// URI.
        profile (SSHProfile | None): connection profile for a remote workspace.
    """
    data.configuration['workspace'] = workspace
    data.configuration['workspace_profile'] = profile.to_dict() if profile else None
    try:
        configuration = Configuration(configuration_directory=data.config_directory)
        configuration.setConfiguration(data.configuration)
        configuration.saveConfiguration()
        logger.info(f"Saved workspace {workspace}")
    except Exception:
        logger.exception("Could not save the workspace setting")
