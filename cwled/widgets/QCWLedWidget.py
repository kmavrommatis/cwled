import logging
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget
from typing import Any, Optional
from cwl_utils_handler import get_cwl_version
import data
import json
from cwl_utils.parser import save

class QCWLedWidget(QWidget):
    """
    Base class for all CWL-related widgets in the application.
    
    This class provides a standardized interface for widgets that work with
    Common Workflow Language (CWL) data. It includes common functionality
    such as:
    - CWL version management
    - Tool data association
    - Logging configuration
    - Standard UI initialization patterns
    
    All CWL-specific widgets should inherit from this class to ensure
    consistent behavior and interface across the application.
    
    Attributes:
        editingFinished (pyqtSignal): Signal emitted when widget editing is
            complete
        cwl_tool (Optional[Any]): The CWL tool data object associated with
            this widget
        cwl_version (Optional[str]): The CWL version string for this widget
    """
    editingFinished = pyqtSignal()
    default_value: Optional[Any]
    cwl_version: Optional[str]=None
    cwl_tool: Optional[Any]
    
    def __init__(self, 
                 parent: QWidget,
                 cwl_tool: Optional[Any] = None,
                 cwl_version: Optional[str] = None):
        """
        Initialize a new QCWLedWidget instance.
        
        Sets up the widget with optional parent, CWL tool data, and version.
        Automatically configures logging, sets the CWL version, and calls
        initUI() for subclass-specific UI initialization.
        
        Args:
            parent (Optional[QWidget]): The parent widget. Defaults to None.
            cwl_tool (Optional[Any]): CWL tool data object to associate with
                this widget. Defaults to None.
            cwl_version (Optional[str]): CWL version string (e.g., 'v1.0',
                'v1.2'). Defaults to None.
        
        Returns:
            None
        """
        super().__init__(parent)
        self.default_value = None
        self._setup_logger()
        if not parent:
            self.logger.critical("QCWLedWidget initialized without a parent widget.")

        self.cwl_tool = None
        if cwl_version:
            self.setCWLVersion(cwl_version)
        if cwl_tool:
            self.setCWL(cwl_tool) # this will set the version if none
        
        
        


        # self.setCWLVersion(cwl_version)
        self.initUI()

    def _setup_logger(self):
        """Sets up the logger for the widget."""
        self.logger = logging.getLogger(self.__class__.__name__)
        log_level_config = data.configuration.get('logLevel', {})
        default_log_level = 'INFO'  # Default log level
        class_log_level = log_level_config.get(
            self.__class__.__name__, default_log_level
        )
        self.logger.setLevel(class_log_level)

        # Basic configuration if no handlers are present for the root logger,
        # to ensure output is visible
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

    def initUI(self):
        """
        Initialize the user interface components.
        Subclasses should override this method.
        """
        pass

    def setCWL(self, cwl_tool: Optional[Any]):
        """
        Sets the CWL tool data for the widget.
        and the CWL version if available.

        Args:
            cwl_tool: The CWL tool data object.
        """
        if cwl_tool is not None:
            self.default_value = cwl_tool
            self.logger.debug(f"Set CWL tool: {type(cwl_tool).__name__}")
            if not self.cwl_version:
                self.setCWLVersion()

    def setCWLVersion(self, 
                      cwl_version: Optional[str]=None):
        """
        Set the CWL version for this widget and its associated tool.
        
        Updates the cwl_version attribute. If cwl_version is explicitly provided,
        it will be used. Otherwise, attempts to detect the version from the tool
        object or inherit from parent.
        
        
        Args:
            cwl_version (Optional[str]): The CWL version to set (e.g., 'v1.0',
                'v1.2'). If provided, this version will be used directly.
                If None, the version will be detected from the tool object.
        
        Returns:
            None
        """

        # If version is explicitly provided, use it directly
        if cwl_version:
            self.cwl_version = cwl_version
            return self.cwl_version

        # if we don't have a tool
        # as it happens when things are not initialized
        # we can't detect the version
        if not self.default_value:
            # Try to inherit from parent if available
            if hasattr(self.parent(), 'cwl_version'):
                self.cwl_version = self.parent().cwl_version
            return self.cwl_version

        # try to get the version of the tool
        # from its parser module.
        # if this does not work we can try to set it manually
        if isinstance( self.default_value, list):
            cwl_versions=[get_cwl_version(e) for e in self.default_value]
            cwl_versions=list(set( cwl_versions ))
            if len(cwl_versions) >1: 
                raise ValueError(f"The CWL object {self.default_value} "
                                 "contains multiple elements of different version"
                                 f"{ json.dumps( cwl_versions)}")
            self.cwl_version=cwl_versions[0]
            return self.cwl_version

        try:
            self.cwl_version= get_cwl_version( self.default_value)
            
        except Exception as e:
            self.cwl_version=None
        if not self.cwl_version and hasattr(self.parent(), 'cwl_version'):
            self.cwl_version=self.parent().cwl_version
        return self.cwl_version



    def getCWL(self) -> Optional[Any]:
        """
        Returns the CWL tool data associated with the widget.

        Returns:
            The CWL tool data object or None.
        """
        # if cwl_version:
        #     self.setCWLVersion(cwl_version)

        if not self.cwl_version and self.default_value:
            self.logger.warning(f"CWL version is not set for "
                                f"{self.__class__.__name__}. Returning None.")
            # raise ValueError(f"CWL version is not set for "
            #                  f"{self.__class__.__name__}.")
        return self.default_value

    def populateFromCWL(self, 
                        cwl_data: Optional[Any] = None):
        """
        Populates the widget with data from a CWL object.
        If cwl_data is not provided, subclasses might use self.cwl_tool.
        Subclasses should override this method.

        Args:
            cwl_data: The CWL data to populate from. Defaults to None.
        """
        if cwl_data is not None:
            self.setCWL(cwl_data)  # Use setCWL to assign to self.cwl_tool
            if not self.cwl_version:
                self.logger.warning("Trying to populate the widgets from an "
                                     f"existing object {cwl_data} "
                                     f"with content {save(cwl_data)}, but no cwl version has "
                                     "been defined")
            
        self.logger.debug(
            f"Populating from CWL data (base class using self.cwl_tool): "
            f"{self.default_value}"
        )
        pass

    def clear(self):
        """
        Clears the widget's data and resets its state.
        Subclasses should override this method to clear their UI elements.
        This base implementation clears self.cwl_tool.
        """
        self.logger.debug("Clearing widget data (base class).")
        self.default_value = None
        pass

    # Changed return type to Optional[Any]
    def getData(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        """
        Retrieves data from the widget, typically for a CWL object.
        Subclasses should override this method.

        Returns:
            The data extracted from the widget, or None.
        """
        self.logger.debug("Getting data from widget (base class).")
        return None

    def _emit_editing_finished(self):
        """
        Helper method to emit the editingFinished signal.
        """
        # print(f"-- {self.__class__.__name__} emitting editingFinished signal")
        self.logger.debug("Emitting editingFinished signal.")
        self.editingFinished.emit()
