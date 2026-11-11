from PyQt6.QtWidgets import QDialog, QApplication
from PyQt6.QtCore import Qt
import builtins
import data


class BaseDialog(QDialog):
    """
    Base dialog class for CWLed dialogs with shared functionality.
    
    This class provides common methods for all dialog windows in the application,
    ensuring consistent behavior across different dialog types.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the base dialog.
        
        Args:
            parent: Parent widget if any
        """
        super().__init__(parent)
        # WindowModal blocks only the parent window (ChildWindow), not the entire app.
        # WindowStaysOnTopHint prevents macOS Cocoa from converting the dialog into a sheet.
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    
    def show_next_to_main_window(self):
        """
        Position the dialog to the left of the top right corner of the screen.
        
        This method positions the dialog at the top right of the screen with its right edge
        aligned to the screen edge. The height matches the MainWindow height if available,
        otherwise uses the screen height. The dialog appears on the same screen as the main window.
        
        The width is taken from the configuration key 'input_window.initial_width'.
        StepDialog is 20% wider than Input/Output dialogs.
        """
        # Get dialog width from configuration with safe default
        base_width = data.configuration.get('input_window', {}).get('initial_width', 400)
        try:
            base_width = int(base_width)
        except (TypeError, ValueError):
            base_width = 400

        dialog_width = base_width
        if self.__class__.__name__ == 'StepDialog':
            dialog_width = int(base_width * 1.2)
        
        parent_widget = self.parentWidget()
        anchor_window = parent_widget.window() if parent_widget is not None else None

        if anchor_window is None and hasattr(builtins, 'main_window'):
            anchor_window = builtins.main_window

        # Resolve screen deterministically.
        screen = anchor_window.screen() if anchor_window is not None else None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        screen_geom = screen.availableGeometry()
        if anchor_window is not None:
            anchor_geom = anchor_window.geometry()
            dialog_height = min(anchor_geom.height(), screen_geom.height())
            dialog_y = max(screen_geom.y(), anchor_geom.y())
        else:
            dialog_height = screen_geom.height()
            dialog_y = screen_geom.y()

        dialog_x = screen_geom.x() + screen_geom.width() - dialog_width - 50

        # Enforce requested width relation even when size hints differ.
        self.setMinimumWidth(dialog_width)
        self.resize(dialog_width, dialog_height)
        self.move(dialog_x, dialog_y)
