import sys
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QBrush, QPen, QColor, QPainter, QFont
from PyQt6.QtWidgets import (QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem,
                             QGraphicsTextItem, QVBoxLayout, QWidget, QGraphicsItem, QGraphicsLineItem)

import builtins


from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QBrush, QPen, QColor, QPainter, QFont, QIcon
from PyQt6.QtWidgets import (QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem,
                             QGraphicsTextItem, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsItem,
                             QGraphicsLineItem, QPushButton, QFrame, QStyle)

class CWLGraphWidget(QGraphicsView):
    def __init__(self, tool_id, label, inputs, outputs):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Store the tool_id, label, inputs, and outputs for future reference
        self.tool_id = tool_id
        self.label = label
        self.inputs = inputs
        self.outputs = outputs

        # Initialize input and output boxes
        self.input_boxes = []
        self.output_boxes = []
        self.lines = []

        # Set up the initial layout
        self.setup_tool_box()
        self.add_inputs_outputs(inputs, outputs)

        # Enable anti-aliasing for better visuals
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Zoom factors
        self.zoom_factor = 1.25  # Amount of zoom per click

    def setup_tool_box(self):
        """Setup the central tool box with ID and label."""
        # Define colors for optional and mandatory boxes
        self.color_optional = QColor(255, 165, 0)  # Orange for optional
        self.color_mandatory = QColor(0, 128, 0)   # Green for mandatory

        # Create a large box for the tool in the center
        self.tool_box = QGraphicsRectItem(-75, -50, 150, 100)
        self.tool_box.setBrush(QBrush(Qt.GlobalColor.lightGray))
        self.scene.addItem(self.tool_box)
        self.tool_box.setZValue(2)  # Ensure the box is drawn above the lines

        # Add tool ID and label in the center box with larger font
        tool_text = f"ID: {self.tool_id}\nLabel: {self.label}"
        tool_text_item = QGraphicsTextItem(tool_text, self.tool_box)
        tool_text_item.setDefaultTextColor(Qt.GlobalColor.black)
        font = QFont()
        font.setPointSize(14)  # Set font size larger
        tool_text_item.setFont(font)
        tool_text_rect = tool_text_item.boundingRect()
        tool_text_item.setPos(-tool_text_rect.width() / 2, -tool_text_rect.height() / 2)
        tool_text_item.setZValue(3)  # Make sure the text is drawn above everything

        # Create a mask (rectangle) over the central box to hide lines under it
        self.create_line_mask()

    def create_line_mask(self):
        """Create a mask over the center box to hide parts of lines passing under the center."""
        mask_rect = QGraphicsRectItem(self.tool_box.rect())
        mask_rect.setBrush(QBrush(Qt.GlobalColor.lightGray))
        mask_rect.setPen(QPen(Qt.GlobalColor.lightGray))
        mask_rect.setPos(self.tool_box.pos())
        mask_rect.setZValue(1)  # Ensure the mask is below the middle box but above the lines
        self.scene.addItem(mask_rect)

    def add_inputs_outputs(self, inputs, outputs):
        """Create and add inputs and outputs boxes with lines."""
        input_y = -len(inputs) * 30 // 2
        output_y = -len(outputs) * 30 // 2

        # Create input boxes and connect them with lines
        for input_name, is_required in inputs:
            color = self.color_mandatory if is_required else self.color_optional
            input_box = MovableBox(input_name, color, is_input=True)
            input_box.setPos(-150, input_y)
            self.scene.addItem(input_box)

            # Create the line and assign it to the input box
            line = ConnectingLine(input_box, self.tool_box, is_input=True)
            input_box.set_connected_line(line)
            self.scene.addItem(line)

            self.input_boxes.append(input_box)
            self.lines.append(line)
            input_y += 60

        # Create output boxes and connect them with lines
        for output_name, is_required in outputs:
            color = self.color_mandatory if is_required else self.color_optional
            output_box = MovableBox(output_name, color, is_input=False)
            output_box.setPos(150, output_y)
            self.scene.addItem(output_box)

            # Create the line and assign it to the output box
            line = ConnectingLine(output_box, self.tool_box, is_input=False)
            output_box.set_connected_line(line)
            self.scene.addItem(line)

            self.output_boxes.append(output_box)
            self.lines.append(line)
            output_y += 60

    def clear_inputs_outputs(self):
        """Remove existing inputs, outputs, and their connecting lines."""
        for item in self.input_boxes + self.output_boxes + self.lines:
            self.scene.removeItem(item)
        self.input_boxes.clear()
        self.output_boxes.clear()
        self.lines.clear()

    def update_inputs_outputs(self, new_inputs, new_outputs):
        """Update the widget with new inputs and outputs."""
        # Clear existing items
        self.clear_inputs_outputs()

        # Add new inputs and outputs
        self.add_inputs_outputs(new_inputs, new_outputs)

        # Update the scene to reflect changes
        self.scene.update()

    def zoom_in(self):
        """Zoom in the scene."""
        self.scale(self.zoom_factor, self.zoom_factor)

    def zoom_out(self):
        """Zoom out the scene."""
        self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)


class MovableBox(QGraphicsRectItem):
    def __init__(self, text, color, is_input=True, parent=None):
        super().__init__(-50, -25, 100, 50, parent)
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.GlobalColor.black))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Add a label to the box
        self.text_item = QGraphicsTextItem(text, self)
        self.text_item.setDefaultTextColor(Qt.GlobalColor.black)
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(-text_rect.width() / 2, -text_rect.height() / 2)

        # Store the line connected to the central box
        self.connected_line = None
        self.is_input = is_input

    def set_connected_line(self, line):
        self.connected_line = line

    def update_line_position(self, center_point):
        """ Update the connected line position dynamically when moved. """
        if self.connected_line:
            if self.is_input:
                start_point = QPointF(self.sceneBoundingRect().right(), self.sceneBoundingRect().center().y())  # Right center of the input box
            else:
                start_point = QPointF(self.sceneBoundingRect().left(), self.sceneBoundingRect().center().y())   # Left center of the output box
            self.connected_line.setLine(start_point.x(), start_point.y(), center_point.x(), center_point.y())

    def itemChange(self, change, value):
        """ Override to detect item position changes and update the line. """
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self.connected_line is not None:
                center_point = self.connected_line.center_point  # Get dynamic center
                self.update_line_position(center_point)
        return super().itemChange(change, value)


class ConnectingLine(QGraphicsLineItem):
    def __init__(self, start_item, center_item, is_input=True):
        super().__init__()
        self.start_item = start_item
        self.center_item = center_item  # Store the central box for dynamic center calculation
        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.is_input = is_input
        self.update_position()

    @property
    def center_point(self):
        """ Get the center point of the central box dynamically. """
        if self.is_input:
            # Left center for inputs
            return QPointF(self.center_item.sceneBoundingRect().left(), 
                           self.center_item.sceneBoundingRect().center().y())
        else:
            # Right center for outputs
            return QPointF(self.center_item.sceneBoundingRect().right(), 
                           self.center_item.sceneBoundingRect().center().y())

    def update_position(self):
        """ Update line position based on the start item and the center point. """
        if self.is_input:
            start_pos = QPointF(self.start_item.sceneBoundingRect().right(), 
                                self.start_item.sceneBoundingRect().center().y())  # Right center for inputs
        else:
            start_pos = QPointF(self.start_item.sceneBoundingRect().left(), 
                                self.start_item.sceneBoundingRect().center().y())   # Left center for outputs
        center_pos = self.center_point
        self.setLine(start_pos.x(), start_pos.y(), center_pos.x(), center_pos.y())


class GraphWidgetWithZoom(QWidget):
    """ Wrapper widget to add zoom buttons to the graph widget """
    def update_inputs_outputs(self,new_inputs, new_outputs):
        self.graph_widget.update_inputs_outputs( new_inputs, new_outputs )

    def __init__(self, tool_id, label, inputs, outputs):
        super().__init__()

        # Create the CWLGraphWidget
        self.graph_widget = CWLGraphWidget(tool_id, label, inputs, outputs)

        # Create zoom in/out buttons
        zoom_in_button = QPushButton('+')
        zoom_out_button = QPushButton('-')

        # Styling for zoom buttons
        zoom_in_button.setFixedSize(40, 40)
        zoom_out_button.setFixedSize(40, 40)

        # Connect zoom actions
        zoom_in_button.clicked.connect(self.graph_widget.zoom_in)
        zoom_out_button.clicked.connect(self.graph_widget.zoom_out)

        # Layout for buttons (stacked at bottom-right corner)
        button_layout = QVBoxLayout()
        button_layout.addWidget(zoom_in_button)
        button_layout.addWidget(zoom_out_button)
        button_layout.setContentsMargins(0, 0, 10, 10)  # Margins to position buttons in the corner
        button_layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        # Main layout with buttons over the graph widget
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.graph_widget)

        # Frame to overlay zoom buttons on the graph widget
        button_frame = QFrame(self)
        button_frame.setLayout(button_layout)
        button_frame.setFixedSize(60, 100)  # Fixed size for the frame
        button_frame.move(self.width() - button_frame.width(), self.height() - button_frame.height())

        # Add button frame to the widget
        main_layout.addWidget(button_frame)

        self.setLayout(main_layout)




class GraphicSummaryWidget(QWidget):
    inputs=[]
    outputs=[]
    tool_id=None
    label=None
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle('CWL Tool Graph')
        

        # Create the graph widget
        self.graph_widget = GraphWidgetWithZoom(self.tool_id, self.label, self.inputs, self.outputs)
        self.populateFromCWL()
        # Create layout and add the graph widget
        layout = QVBoxLayout()
        layout.addWidget(self.graph_widget)
        self.setLayout(layout)

    def populateFromCWL(self):
        # Example CWL tool data
        self.tool_id = builtins.cwl_dict.get('id','')
        self.label =   builtins.cwl_dict.get('label','')
        
        
        for i in builtins.cwl_dict.get('inputs',[]):
            is_required=True
            for t in i.get('type'):
                if t == 'null':
                    is_required=False
            self.inputs.append( (i.get('id'), is_required))
        for o in builtins.cwl_dict.get('outputs',[]):
            is_required=True
            for t in o.get('type'):
                if t == 'null':
                    is_required=False
            self.outputs.append( (o.get('id'), is_required))
        # inputs = [('input1', True), ('input2', False), ('input3', True)]   # (name, is_required)
        # outputs = [('output1', True), ('output2', False)]

        if not self.inputs:
            self.inputs = [('Unspecified', True)]
        if not self.outputs:
            self.outputs = [('Unspecified', True)]

        # Call this method to update the widget dynamically
        self.graph_widget.update_inputs_outputs(self.inputs, self.outputs)


# Application setup
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
