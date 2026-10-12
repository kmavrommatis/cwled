from PyQt6.QtWidgets import QMessageBox
import logging
import traceback
import sys

class QErrorMessage:
    """
    Utility class for displaying standardized error messages in the application.
    
    This class provides methods to show critical error messages using QMessageBox
    with consistent styling and handling. It can be used anywhere in the application
    where critical errors need to be displayed to the user.
    """
    
    @staticmethod
    def show_critical(parent, title, message, exception=None, logger=None):
        """
        Display a critical error message dialog.
        
        Args:
            parent: The parent widget for the QMessageBox
            title (str): The title for the error dialog
            message (str): The main error message to display
            exception (Exception, optional): The exception object if available
            logger (logging.Logger, optional): Logger object to log the error
            
        Returns:
            int: The dialog result code from QMessageBox.exec()
        """
        # Log the error if a logger is provided
        if logger:
            if exception:
                logger.critical(f"{message}: {str(exception)}")
                logger.debug(traceback.format_exc())
            else:
                logger.critical(message)
        
        # Create and configure the error dialog
        error_dialog = QMessageBox(parent)
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(message)
        
        # Add detailed information about the exception if available
        if exception:
            error_details = str(exception)
            if hasattr(exception, '__traceback__') and exception.__traceback__:
                tb_info = traceback.format_exception(type(exception), exception, exception.__traceback__)
                error_details += "\n\nTraceback:\n" + "".join(tb_info)
            error_dialog.setInformativeText(f"Error details:\n{error_details}")
        
        error_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Show the dialog and return the result
        return error_dialog.exec()
    
    @staticmethod
    def show_and_raise(parent, title, message, exception, logger=None, raise_exception=True):
        """
        Display a critical error message and optionally raise the exception afterward.
        
        This is useful for showing the error to the user before potentially
        terminating the current operation due to the exception.
        
        Args:
            parent: The parent widget for the QMessageBox
            title (str): The title for the error dialog
            message (str): The main error message to display
            exception (Exception): The exception object
            logger (logging.Logger, optional): Logger object to log the error
            raise_exception (bool): Whether to raise the exception after showing the dialog
            
        Raises:
            The provided exception if raise_exception is True
        """
        QErrorMessage.show_critical(parent, title, message, exception, logger)
        
        if raise_exception:
            raise exception
