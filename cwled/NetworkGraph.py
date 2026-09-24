import signal
from pathlib import Path
import logging
from copy import deepcopy
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QTransform
from CWLparser import  Parser
import json
from OdenGraphQt import (
    NodeGraph, BaseNode, BaseNodeCircle, GroupNode,
    PropertiesBinWidget,
    NodesTreeWidget,
    NodesPaletteWidget
)
import uuid
from OdenGraphQt import SubGraph
from OdenGraphQt.constants import PipeLayoutEnum
from OdenGraphQt.qgraphics.port import PortItem  # Add this import
from OdenGraphQt.qgraphics.node_base import NodeItem
from OdenGraphQt.qgraphics.pipe import LivePipePolygonItem
from OdenGraphQt.constants import PortTypeEnum  # Add this import
from configuration import Configuration
import builtins
import sys
import data
import os
import re
from typing import Union, Any
from copy import deepcopy
from GraphNodes import InputNode,OutputNode,StepNode
from cwl_utils.parser import save
from cwl_utils_handler import get_cwl_module, get_cwl_version
from GraphNodes import CWLNode, PortSplitter
from OdenGraphQt import constants as cc
cc.WIDTH=400
NODE_INPUT_WIDTH=70
NODE_OUTPUT_WIDTH=70
NODE_STEP_WIDTH=100




class CWLGraph(QWidget):
    '''
    Create the graph based on the CWL dict.

    This class is responsible for creating a graph representation of a CWL (Common Workflow Language) document.
    It directly operates on the provided CWL dictionary, ensuring changes propagate to other parts of the application.
    The output of the class is not visible on screen; instead, it is a serialized graph which can be loaded
    (deserialized) on an existing graph.

    Attributes:
        cwl_dict (dict): Reference to the original CWL dictionary.
        nodes (list): List of nodes in the graph.
        logger (logging.Logger): Logger for the class.
    '''
    nodes=[]
    workflow_file=None
    cwl_version:str=None

    dragging_output_port:Any=None
    # Define a signal for connection notifications
    editingFinished = pyqtSignal()

    def __init__(self, 
                 parent=None, # parent Widget
                 workflow_file:str=None,  # this is the filename of the CWL. Used to find the path for steps called within
                 cwl_workflow:Any = None ,    # the dictionary describing the CWL
                 cwl_version:str =None
                 ):  
        '''
        Initialize the CWLGraph widget.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
            workflow_file (str, optional): Filename of the CWL. Used to find the path for steps called within. Defaults to None.
            cwl_dict (dict, optional): Dictionary describing the CWL. Defaults to None.
        '''
        super().__init__(parent=parent)
        # Enable drag and drop events for this widget
        self.setAcceptDrops(True)
        self.logger=logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get('logLevel',{}).get(self.__class__.__name__, 'DEBUG'))

        self.logger_addnodes=logging.getLogger(f"{self.__class__.__name__}_addnodes")
        self.logger_addnodes.setLevel(data.configuration.get('logLevel',{}).get(f"{self.__class__.__name__}_addnodes", 'DEBUG'))
        self.logger_removenodes=logging.getLogger(f"{self.__class__.__name__}_removenodes")
        self.logger_removenodes.setLevel(data.configuration.get('logLevel',{}).get(f"{self.__class__.__name__}_removenodes", 'DEBUG'))
        self.logger_makeedges=logging.getLogger(f"{self.__class__.__name__}_makeedges")
        self.logger_makeedges.setLevel(data.configuration.get('logLevel',{}).get(f"{self.__class__.__name__}_makeedges", 'DEBUG'))

        # Initialize the cwl_dict as an empty dictionary if none provided
        self.setCWL(cwl_workflow )
        # Set the base directory for all CWLNodes to resolve relative paths
        if workflow_file:
            self.setFileLocation(workflow_file)
            # Set the base directory for all nodes
            
            CWLNode.set_base_directory(workflow_file)
            
        self.logger.debug(f"The workflow comes from file {self.workflow_file}")
        
        self.graph=NodeGraph()

        viewer = self.graph.viewer()
        # def _no_ctx(e): e.ignore()
        # viewer.contextMenuEvent = _no_ctx
        # viewer.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        # # also disable built-in menus
        # self.graph.disable_context_menu
        # for name in ('graph', 'nodes'):
        #     menu = self.graph.get_context_menu(name)
        #     if menu and hasattr(menu, 'qmenu'):
        #         menu.qmenu.clear()
        #         menu.qmenu.setDisabled(True)
        

        # Connect to the viewer's mouse events
        self.graph.viewer().scene().installEventFilter(self)
        self.graph._dragging_output_port = None
        self.graph.register_node(StepNode)
        # self.graph.register_node(ToolNode)
        self.graph.register_node(InputNode)
        self.graph.register_node(OutputNode)



        self.graph.set_pipe_style(PipeLayoutEnum.CURVED.value) #PipeLayoutEnum.ANGLE.value
        self.graph_widget = self.graph.widget
        # Create the layout for the graph widget
        self.graph_layout = QVBoxLayout(self)
        self.graph_layout.addWidget(self.graph_widget)
        
        # Connect to the port_connected signal to be notified of new connections
        # self.graph.port_connected.connect(self.onPortConnected)
        
        # Connect the node double-click signal to handle all node types
        self.logger.debug("Connecting graph node_double_clicked signal to handler")
        self.graph.node_double_clicked.connect(self.onNodeDoubleClicked)
        self.graph.port_connected.connect(self.onPortConnected)
        self.graph.port_disconnected.connect(self.onPortDisconnected) 
        self.graph.context_menu_prompt.connect(lambda *args, **kwargs: print("[SIGNAL] context_menu_prompt emitted"))
        if cwl_workflow: 
            self.logger.debug(f"Provided the workflow cwl {self.cwl_workflow.id} as { json.dumps(save(self.cwl_workflow))[:150]} ...")
            self.makeGraph(
                cwl_workflow=self.cwl_workflow,
                file_location=self.workflow_file
            )
        else:
            self.logger.debug("The canvas is empty")

        self.showGraph()

    def eventFilter(self, obj, event):
        """Handle mouse events for drag-to-create functionality."""
        # if event.type() not in [QEvent.Type.GraphicsSceneMouseMove, 
        #                         QEvent.Type.Paint, 
        #                         QEvent.Type.ContextMenu,
        #                         QEvent.Type.GraphicsSceneContextMenu,
        #                         QEvent.Type.GraphicsSceneHoverMove]:
        # print(f"--- [EVENT] Seen event of type: {event.type().name}")

        node=None
        if event.type() == QEvent.Type.GraphicsSceneContextMenu:
            # print("--- [EVENT_FILTER] Caught GraphicsSceneContextMenu, swallowing event.")
            return True  # swallow the event

        elif event.type() == QEvent.Type.ContextMenu:
            # print("--- [EVENT_FILTER] Caught ContextMenu, swallowing event.")
            return True  # swallow the event
        
        # Handle key press events for deletion
        elif event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
                self.onNodeDeleted()
                return True  # Event handled

        elif event.type() == QEvent.Type.GraphicsSceneMousePress:
            item = self.graph.viewer().scene().itemAt(event.scenePos(), QTransform())
            # print(f"--- [EVENT_FILTER] MousePress on item: {type(item).__name__}")
            if isinstance(item, PortItem):
                if item.port_type == PortTypeEnum.OUT.value:
                    self.dragging_output_port = item
                    self.dragging_input_port = None
                elif item.port_type == PortTypeEnum.IN.value:
                    self.dragging_input_port = item  
                    self.dragging_output_port = None
                else:
                    self.dragging_output_port = None
                    self.dragging_input_port = None
            else:
                self.dragging_output_port = None
                self.dragging_input_port = None
                
        elif event.type() == QEvent.Type.GraphicsSceneMouseRelease :
            if self.dragging_input_port or self.dragging_output_port:
                scene = self.graph.viewer().scene()
                pos = event.scenePos()
                items_at_pos = scene.items(pos)
                item = self.graph.viewer().scene().itemAt(event.scenePos(), QTransform())
                create_node=False
                if ((not any([ isinstance( x , PortItem) for x in items_at_pos] )and
                    not any([ isinstance( x , NodeItem) for x in items_at_pos] ) ) or 
                    item is None):
                    create_node=True    
                print(f"Create node: {create_node}")
                # Handle output port drag (existing functionality)
                if self.dragging_output_port and create_node:
                    print(f"Creating output node from drag")
                    # print("--- [EVENT_FILTER] Decided to create an Output node.")
                    node=self.createOutputNodeFromDrag(event.scenePos())
                    
                # Handle input port drag (new functionality)
                elif self.dragging_input_port and create_node:
                    print(f"Creating input node from drag")
                    # print("--- [EVENT_FILTER] Decided to create an Input node.")
                    node=self.createInputNodeFromDrag(event.scenePos())

                self.dragging_output_port = None
                self.dragging_input_port = None
        return super().eventFilter(obj, event)


    def createInputNodeFromDrag(self, scene_pos):
        """Create InputNode when input port is dragged to empty space."""
        if not hasattr(self, 'dragging_input_port') or not self.dragging_input_port:
            return
            
        port_item = self.dragging_input_port
        target_node = self.graph.get_node_by_name(port_item.node.name)
        self.logger_addnodes.debug(f"Creating Input Node to {target_node.name()} and port {port_item.name}")
        # Convert scene position to view position
        view_pos = self.graph.viewer().mapFromScene(scene_pos)
        
        # Generate unique name for the input
        
        input_name =   port_item.name 
        if input_name in [ PortSplitter( x.name() , self.cwl_workflow.id).port_id for x in self.graph.all_nodes()] :
            input_name=f"{input_name}_{ str(uuid.uuid4())[:4]}"

        graph_x = scene_pos.x()
        graph_y = scene_pos.y()
        # Determine the input type from the target port
        # get the cwltool of the target node
        input_type = 'File'  # Default type if not found
        if hasattr(target_node, 'getCWLTool') and target_node.getCWLTool():
            for input_def in getattr(target_node.getCWLTool(),'inputs',[]):
                if PortSplitter(input_def.id, target_node.getCWLTool().id ).port_id == port_item.name:
                    input_type = input_def.type_
                    break
        # Create the InputNode
        input_node = self.graph.create_node(
            'cwled.input.InputNode', 
            name=input_name, 
            pos=[view_pos.x(), view_pos.y()],
            width=NODE_INPUT_WIDTH,
            text_alignment='left'
        )
        input_node.create_property('user_width', NODE_INPUT_WIDTH)
        self.logger_addnodes.debug(f"Created InputNode '{input_name}' at position ({view_pos.x()}, {view_pos.y()})")
        # Set up the CWL data for the input parameter
        module = get_cwl_module(self.cwl_version)
        
        # Create a WorkflowInputParameter
        if self.cwl_version == 'v1.0':
            input_param = module.InputParameter(
                id=input_name,
                type_=input_type
            )
        else:
            input_param = module.WorkflowInputParameter(
                id=input_name,
                type_=input_type
            )
        
        # Add additional properties from the target port if available
        if hasattr(target_node, 'cwl_tool') and target_node.cwl_tool:
            if hasattr(target_node.cwl_tool, 'inputs'):
                for input_def in target_node.cwl_tool.inputs:
                    if input_def.id == port_item.name:
                        # Copy relevant properties
                        for prop in ['doc', 'label', 'default', 'format', 'secondaryFiles']:
                            if hasattr(input_def, prop):
                                setattr(input_param, prop, getattr(input_def, prop))
                        break
        
        # Strip inputBinding from nested record fields since workflow inputs
        # don't have command line bindings
        self._stripInputBindingsFromType(input_param.type_)

        input_node.setCWL(input_param)
        input_node.setCustomTitle()
        
        # Make the connection from the new InputNode to the target port
        try:
            source_port = input_node.outputs()['source']  # InputNodes have 'source' output
            target_port = target_node.inputs()[port_item.name]
            source_port.connect_to(target_port)
            self.logger_addnodes.info(f"Created InputNode '{input_name}' connected to {target_node.name()}/{port_item.name}")
        except Exception as e:
            self.logger_addnodes.error(f"Error connecting new InputNode: {e}")
        
        # Set final position after connection
        input_node.set_pos(graph_x,graph_y)
        # self.editingFinished.emit()
        return input_node


    def createOutputNodeFromDrag(self, scene_pos):
        """Create OutputNode when output port is dragged to empty space."""
        if not hasattr(self, 'dragging_output_port') or not self.dragging_output_port:
            return
            
        port_item = self.dragging_output_port
        source_node = self.graph.get_node_by_name(port_item.node.name)
        self.logger_addnodes.debug(f"Creating Output Node to {source_node.name()} and port {port_item.name}")
        graph_x = scene_pos.x()
        graph_y = scene_pos.y()
        # Convert scene position to view position
        view_pos = self.graph.viewer().mapFromScene(scene_pos)

        # Generate unique name for the output
        # output_name = self.graph.get_unique_name( port_item.name)
        output_name =   port_item.name 
        if output_name in [ PortSplitter( x.name() , self.cwl_workflow.id).port_id for x in self.graph.all_nodes()] :
            output_name=f"{output_name}_{ str(uuid.uuid4())[:4]}"

        if hasattr( source_node.getCWL(), 'type_'):
            output_type=source_node.getCWL().type_
        else:
            output_type='File'
            

        # print(f"Creating Output Node from {source_node.name()} and port {port_item.name}")
        # sys.exit(345)
        # Create the OutputNode
        output_node = self.graph.create_node(
            'cwled.output.OutputNode', 
            name=output_name, 
            pos=[view_pos.x(), view_pos.y()],
            width=NODE_OUTPUT_WIDTH,
            text_alignment='left'
        )
        output_node.create_property('user_width', NODE_OUTPUT_WIDTH)
        self.logger_addnodes.debug(f"Created OutputNode '{output_name}' at position ({view_pos.x()}, {view_pos.y()})")
        # Set up the CWL data
        module = get_cwl_module(self.cwl_version)
        
        output_param = module.WorkflowOutputParameter(
            id=output_name,
            type_=output_type,  # Default type
            outputSource=f"{source_node.name()}/{port_item.name}"
        )
        
        output_node.setWorkflowID( self.cwl_workflow.id )
        output_node.setCWL(output_param)
        output_node.setCustomTitle()
        
        # Make the connection
        try:
            source_port = source_node.outputs()[port_item.name]
            target_port = output_node.inputs()['sink']
            source_port.connect_to(target_port)
            self.logger_addnodes.info(f"Created OutputNode '{output_name}' connected to {source_node.name()}/{port_item.name}")
        except Exception as e:
            self.logger_addnodes.error(f"Error connecting new OutputNode: {e}")
        output_node.set_pos(graph_x, graph_y)

        # self.editingFinished.emit()
        return output_node

    def setCWLVersion(self, cwl_version: str=None):
        if not isinstance(cwl_version, str):
            self.cwl_version = get_cwl_version(self.cwl_workflow)
        else:
            self.cwl_version = cwl_version

    def checkToolWorkflowVersionCompatibility(self,
                                              tool_cwl: Any = None,
                                              tool_version: str = None,
                                              workflow_version: str = None) -> bool:
        """
        Compare tool/workflow CWL versions and warn the user if the tool version
        is lower than the workflow version.

        Args:
            tool_cwl: Parsed CWL object of the tool (optional, used to infer version).
            tool_version: Explicit tool CWL version (optional, e.g. 'v1.0').
            workflow_version: Explicit workflow CWL version (optional, e.g. 'v1.2').

        Returns:
            bool: True when versions are compatible or cannot be compared,
                  False when a mismatch was detected (tool < workflow) and warning shown.
        """
        def _normalize_version(version_value: Any) -> tuple[Any, tuple[int, ...] | None]:
            if version_value is None:
                return None, None
            version_text = str(version_value).strip()
            if not version_text:
                return None, None
            match = re.search(r'(\d+)(?:\.(\d+))?', version_text)
            if not match:
                return version_text, None
            major = int(match.group(1))
            minor = int(match.group(2) or 0)
            return f"v{major}.{minor}", (major, minor)

        resolved_workflow_version = workflow_version if isinstance(workflow_version, str) else self.cwl_version
        resolved_tool_version = tool_version if isinstance(tool_version, str) else get_cwl_version(tool_cwl)

        workflow_label, workflow_tuple = _normalize_version(resolved_workflow_version)
        tool_label, tool_tuple = _normalize_version(resolved_tool_version)

        self.logger.debug(
            f"Version compatibility check: workflow={workflow_label} ({workflow_tuple}), "
            f"tool={tool_label} ({tool_tuple})"
        )

        if workflow_tuple is None or tool_tuple is None:
            self.logger.debug("Skipping version compatibility warning: unable to parse one or both versions")
            return True

        if tool_tuple > workflow_tuple:
            QMessageBox.warning(
                self,
                "CWL Version Mismatch",
                (
                    "The selected tool uses an newer CWL version than the current workflow.\n\n"
                    f"Workflow version: {workflow_label}\n"
                    f"Tool version: {tool_label}\n\n"
                    "Please use matching CWL versions before adding or connecting this tool."
                )
            )
            self.logger.warning(
                f"CWL version mismatch detected: tool {tool_label} > workflow {workflow_label}"
            )
            return False

        return True


    def setFileLocation(self, file_location:Union[str|Path]=None):
        '''
        set the file path that contains the CWL for this graph
        '''
        self.logger.debug(f"Setting the filepath for this CWL to {file_location}")
        self.workflow_file=file_location

    def _stripInputBindingsFromType(self, type_obj):
        """Remove inputBinding from nested record fields recursively.
        
        Workflow inputs don't have command line bindings, so when creating
        an InputNode from a CommandLineTool's input, we need to strip
        inputBinding from the record fields.
        """
        if isinstance(type_obj, list):
            for item in type_obj:
                self._stripInputBindingsFromType(item)
        elif hasattr(type_obj, 'fields') and type_obj.fields:
            for field in type_obj.fields:
                if hasattr(field, 'inputBinding'):
                    field.inputBinding = None
                if hasattr(field, 'type_'):
                    self._stripInputBindingsFromType(field.type_)

    def resolveWorkflowStepIDCollision(self,
                                       changed_kind: str,
                                       changed_id: str) -> str:
        """
        Ensure workflow id and step ids do not collide.

        If a collision is detected, show a warning and return a unique id by appending
        a 4-character UUID suffix.

        Args:
            changed_kind: Either 'workflow' or 'step' indicating which id changed.
            changed_id: The new id value after edit.

        Returns:
            str: Original id if no collision, otherwise a uniquified id.
        """
        if not changed_id or not hasattr(self, 'cwl_workflow') or self.cwl_workflow is None:
            return changed_id

        step_ids = [
            getattr(step, 'id', None)
            for step in getattr(self.cwl_workflow, 'steps', [])
            if getattr(step, 'id', None)
        ]
        workflow_id = getattr(self.cwl_workflow, 'id', None)

        collision = False
        if changed_kind == 'step':
            collision = (changed_id == workflow_id)
        elif changed_kind == 'workflow':
            collision = (changed_id in step_ids)
        else:
            return changed_id

        if not collision:
            return changed_id

        unique_id = f"{changed_id}_{str(uuid.uuid4())[:4]}"
        while unique_id == workflow_id or unique_id in step_ids:
            unique_id = f"{changed_id}_{str(uuid.uuid4())[:4]}"

        if changed_kind == 'step':
            message = (
                "Step ID collides with workflow ID.\n\n"
                f"Workflow ID: {workflow_id}\n"
                f"Step ID: {changed_id}\n\n"
                f"The step ID has been changed to: {unique_id}"
            )
        else:
            message = (
                "Workflow ID collides with an existing step ID.\n\n"
                f"Workflow ID: {changed_id}\n"
                f"Conflicting step ID: {changed_id}\n\n"
                f"The workflow ID has been changed to: {unique_id}"
            )

        QMessageBox.warning(self, "ID Collision", message)
        self.logger.warning(
            f"Resolved {changed_kind} id collision: {changed_id} -> {unique_id}"
        )
        return unique_id
        
    def setCWL(self, cwl_workflow:Any):
        '''
        Set the cwl_dict that is used for parsing.
        This method stores a direct reference to the provided dictionary,
        not a copy, so changes to the dictionary will propagate to other parts
        of the application.
        
        Args:
            cwl_dict (dict): Dictionary containing the CWL description.
        '''
        previous_workflow_id = getattr(self, '_last_known_workflow_id', None)
        self.cwl_workflow = cwl_workflow

        current_workflow_id = getattr(self.cwl_workflow, 'id', None)
        if previous_workflow_id is not None and current_workflow_id != previous_workflow_id:
            resolved_workflow_id = self.resolveWorkflowStepIDCollision(
                changed_kind='workflow',
                changed_id=current_workflow_id
            )
            if resolved_workflow_id != current_workflow_id:
                self.cwl_workflow.id = resolved_workflow_id
                if hasattr(self, 'graph') and self.graph is not None:
                    for node in self.graph.all_nodes():
                        if hasattr(node, 'setWorkflowID'):
                            node.setWorkflowID(resolved_workflow_id)
                current_workflow_id = resolved_workflow_id

        self._last_known_workflow_id = current_workflow_id
        self.setCWLVersion()
        self.logger.debug(f"Setting the CWL dict to {json.dumps(save(cwl_workflow))[:150]}")

    def getGraph(self):
        return self.graph
    

    def getData(self):
        """
        go through the nodes of the graph
        and retrieve all the components
        at the end create and present a CWL workflow
        """
        self.logger.info(f"Getting the node data from the graph")
        # Get all step nodes
        step_nodes = [n for n in self.graph.get_nodes_by_type('cwled.step.StepNode') ]

        # Get all input nodes
        input_nodes = [n for n in self.graph.get_nodes_by_type('cwled.input.InputNode')]

        # Get all output nodes
        output_nodes = [n for n in self.graph.get_nodes_by_type('cwled.output.OutputNode')]

        # module=get_cwl_module( self.cwl_version)
        # update the existing workflow
        self.cwl_workflow.inputs=[ i.getData() for i in input_nodes]
        self.cwl_workflow.outputs=[ o.getData() for o in output_nodes]
        self.cwl_workflow.steps=[s.getData() for s in step_nodes]
        self.logger.info(f"\u2705 All node data have been retrieved")
        # print(f"The updated workflow is {json.dumps( save(self.cwl_workflow), indent=3, default=str)}")
        
        return self.cwl_workflow



    def showGraph( self ):
        '''
        prepare the graph for visualization,
        by laying out the nodes and arranging the
        inputs and outputs
        '''

        self.graph_widget.show()
        self.graph.clear_selection()
        self.graph.toggle_node_search()

        if hasattr(self.parent(), 'node_coordinates') and self.parent().node_coordinates:
            self.logger.debug(f"We will get the coordinates from the parent object")
            # self.parent().setNodeCoordinates()
            try:
                self.arrange_inputs_outputs(force_all=True)
            except Exception:
                pass
        else:
            self.logger.debug(f"We will calculate the coordinates automatically")
            self.graph.auto_layout_nodes()
            try:
                self.arrange_inputs_outputs(force_all=True)
            except Exception as e:
                pass
            self.graph.clear_selection()
            self.graph.fit_to_selection()

    def makeGraph(self, 
                  cwl_workflow:Any=None,
                  file_location:str=None 
                  ):
        '''
        creates the nodes of the graphs
        '''

        if not file_location:
            file_location=self.workflow_file
        if not cwl_workflow:
            cwl_workflow=self.cwl_workflow
        self.logger.info(f"Making the graph for {cwl_workflow.id}")
        self.logger.debug(f"Clearing graph content before drawing new graph.")

        # Block the connect_port / disconnect_port signals temporarily
        try:
            self.graph.port_connected.disconnect(self.onPortConnected)
        except (TypeError, RuntimeError):
            pass
        try:
            self.graph.port_disconnected.disconnect(self.onPortDisconnected)
        except (TypeError, RuntimeError):
            pass

        # Clear all nodes and connections from the graph
        self.clear()
        
        self.logger.debug(f"Internal node list (self.nodes) cleared. Count: {len(self.nodes)}")
        self.logger.debug(f"OdenGraphQt graph node count after clearing: {len(self.graph.all_nodes())}")

        self.logger.debug(f"makeGraph received filename {file_location}")    
        self.logger.debug(f"makeGraph received {json.dumps(save( cwl_workflow))[:150]} ... { json.dumps(save( cwl_workflow))[-50:]}")

        node_names=[n.name() for n in self.graph.all_nodes() ]
        self.logger.debug(f"makeGraph the graph current has {len(self.nodes)} nodes")
        self.logger.debug("The existing graph contains \n%s", json.dumps( self.graph.all_nodes(), indent=3, default=str))
        
        # go through the CWL steps and create the nodes
        self.logger.info(f"Loading steps for workflow {cwl_workflow.id}")
        for step in cwl_workflow.steps:
            # Note: After clear(), node_names should be empty, but we check anyway for safety
            # This allows nodes to be recreated with updated inputs/outputs when tool files change
            if step.id in node_names:
                self.logger.warning(f"makeGraph: step {step.id} still exists after clear() - this shouldn't happen")
                # Remove the existing node to ensure it gets recreated with updated ports
                existing_node = self.graph.get_node_by_name(step.id)
                if existing_node:
                    self.graph.delete_node(existing_node)
            self.logger.info(f"Adding step {step.id} to the graph")
            self.logger.debug(f"Creating new step node for step with id {step.id}")
            x=y=0
            if hasattr( self.parent(), 'node_coordinates') and self.parent().node_coordinates:
                try:
                    x=self.parent().node_coordinates.get(step.id).get('x')
                    y=self.parent().node_coordinates.get(step.id).get('y')
                except:
                    pass
            node=self.graph.create_node( 
                'cwled.step.StepNode', 
                name= step.id ,
                pos=(x,y),
                width=NODE_STEP_WIDTH,
                text_alignment='left')
            node.create_property('user_width', NODE_STEP_WIDTH)
            self.logger.debug(f"Setting file {step.run} for {step.id}")

            
            # set the filename of the specific node 
            # node.setNodeFile( step.run )
            # load the file with the CWL description of this step
            # the tool is a StepNode which knows what its icon, inputs and outputs are.
            # node.loadTool( step.run)
            node.setWorkflowID( cwl_workflow.id )
            node.setWorkflowFilename( self.workflow_file )
            node.setCWL( step ) 
            node.setCustomTitle()
            
            QTimer.singleShot(0, node.addPortTooltips)  # Defer to next event loop
    
            node.stepnodeUpdated.connect(self.onStepNodeUpdated)
            
            # add the outputSource to the node 
            self.nodes.append( node )
        # go through the CWL of the workflow
        # and create the nodes for the inputs
        # Each input is an InputNode which knows its type (e.g string, int, etc.)
        # and its icon.
        for input in cwl_workflow.inputs:
            if input.id in node_names:
                self.logger.warning(f"makeGraph: input {input.id} still exists after clear() - this shouldn't happen")
                # Remove the existing node to ensure it gets recreated with updated properties
                existing_node = self.graph.get_node_by_name(input.id)
                if existing_node:
                    self.graph.delete_node(existing_node)
            self.logger.info(f"Adding input {input.id} to the graph")
            x=y=0
            if hasattr( self.parent(), 'node_coordinates') and self.parent().node_coordinates:
                try:
                    x=self.parent().node_coordinates.get(input.id).get('x')
                    y=self.parent().node_coordinates.get(input.id).get('y')
                except:
                    pass
            node=self.graph.create_node( 
                'cwled.input.InputNode', 
                name= input.id , 
                pos=(x,y),
                width=NODE_INPUT_WIDTH,
                text_alignment='left')
            node.create_property('user_width', NODE_INPUT_WIDTH)
            node.setWorkflowID( cwl_workflow.id )
            node.setWorkflowFilename( self.workflow_file )
            node.setCWL( input )
            node.setCustomTitle()
            QTimer.singleShot(0, node.addPortTooltips)  # Defer to next event loop
    
            node.inputnodeUpdated.connect(self.onInputNodeUpdated)
            self.nodes.append( node ) 
            
        
        # go through the CWL of the workflow 
        # and create the nodes for the inpoutputsuts
        # Each input is an OutputNode which knows its type (e.g string, int, etc.)
        # and its icon.
        for output in cwl_workflow.outputs:
            if output.id in node_names:
                self.logger.warning(f"makeGraph: output {output.id} still exists after clear() - this shouldn't happen")
                # Remove the existing node to ensure it gets recreated with updated properties
                existing_node = self.graph.get_node_by_name(output.id)
                if existing_node:
                    self.graph.delete_node(existing_node)
            self.logger.info(f"Adding output {output.id} to the graph")
            x=y=0
            if hasattr( self.parent(), 'node_coordinates') and self.parent().node_coordinates:
                try:
                    x=self.parent().node_coordinates.get(output.id).get('x')
                    y=self.parent().node_coordinates.get(output.id).get('y')
                except:
                    pass
            node=self.graph.create_node( 
                'cwled.output.OutputNode', 
                name= output.id,
                pos=(x,y),
                width=NODE_OUTPUT_WIDTH,
                text_alignment='left'
                )
            node.create_property('user_width', NODE_OUTPUT_WIDTH)
            node.setWorkflowID( cwl_workflow.id )
            node.setWorkflowFilename( self.workflow_file )
            node.setCWL( output )
            node.setCustomTitle()
            QTimer.singleShot(0, node.addPortTooltips)  # Defer to next event loop
    
            node.outputnodeUpdated.connect(self.onOutputNodeUpdated)
            # node.setNodeFile( file_location )
            # node.loadTool( output )
            self.nodes.append( node ) 

        
        # after all teh nodes have been added 
        # go through them and add their edges
        self.logger.debug(f"makeGraph the graph current has {len(self.nodes)} nodes")
        self.logger.debug("Adding the edges now")
        # print(f"==========================")
        # print("==== Making the edges === ")
        
        try:
            for node in self.nodes:
                node.addEdge()
        finally:
            self.graph.port_connected.connect(self.onPortConnected)
            self.graph.port_disconnected.connect(self.onPortDisconnected)

    def clear( self):
        """
        Clear the graph of all nodes and connections.
        """
        self.graph.clear_session()
        self.nodes.clear()
        self.logger.info("Graph cleared of all nodes and connections.")



    def arrange_inputs_outputs(self, force_all=False):
        """
        Reposition input and output nodes intelligently.
        
        Args:
            force_all (bool): If True, rearrange all nodes. If False, only arrange unpositioned nodes.
        """
        vertical_gap = 120
        minimum_step_gap = 24
        step_column_tolerance = max(NODE_STEP_WIDTH, 25)

        input_nodes = [n for n in self.graph.all_nodes() if n.type_ == 'cwled.input.InputNode']
        output_nodes = [n for n in self.graph.all_nodes() if n.type_ == 'cwled.output.OutputNode']
        step_nodes = [n for n in self.graph.all_nodes() if n.type_ == 'cwled.step.StepNode']
        
        if not input_nodes and not output_nodes and not step_nodes:
            return
        
        # Get the bounds of existing positioned nodes
        if input_nodes:
            min_left = min(n.x_pos() for n in input_nodes)
            # Check if inputs are already well-positioned (aligned vertically)
            input_x_positions = [n.x_pos() for n in input_nodes]
            inputs_aligned = len(set(input_x_positions)) <= 1  # All at same X position
        else:
            min_left = -200
            inputs_aligned = True
            
        if output_nodes:
            max_right = max(n.x_pos() for n in output_nodes)
            # Check if outputs are already well-positioned
            output_x_positions = [n.x_pos() for n in output_nodes]
            outputs_aligned = len(set(output_x_positions)) <= 1  # All at same X position
        else:
            max_right = 200
            outputs_aligned = True
        
        # Only rearrange if forced or nodes are not properly aligned
        if not force_all and inputs_aligned and outputs_aligned and not step_nodes:
            return
        
        # Calculate reference middle from step nodes
        if step_nodes:
            step_y_positions = [n.y_pos() for n in step_nodes]
            step_middle = (max(step_y_positions) + min(step_y_positions)) / 2
        else:
            step_middle = 0
        
        # Arrange input nodes
        if input_nodes and (force_all or not inputs_aligned):
            # Sort by current Y position to maintain relative order
            input_nodes.sort(key=lambda n: n.y_pos())
            
            for i, node in enumerate(input_nodes):
                node.set_x_pos(min_left)
                # Only adjust Y position if forcing or if node is far from the reference
                if force_all or abs(node.y_pos() - step_middle) > 300:
                    target_y = step_middle + (i - len(input_nodes)/2) * vertical_gap
                    node.set_y_pos(target_y)
        
        # Arrange output nodes
        if output_nodes and (force_all or not outputs_aligned):
            # Sort by current Y position to maintain relative order
            output_nodes.sort(key=lambda n: n.y_pos())
            
            for i, node in enumerate(output_nodes):
                node.set_x_pos(max_right)
                # Only adjust Y position if forcing or if node is far from the reference
                if force_all or abs(node.y_pos() - step_middle) > 300:
                    target_y = step_middle + (i - len(output_nodes)/2) * vertical_gap
                    node.set_y_pos(target_y)

        # Arrange step nodes by x-coordinate columns around the same middle line
        if step_nodes:
            def _node_x(node):
                x = node.x_pos()
                return float(x) if x is not None else 0.0

            def _node_height(node):
                measured_height = 0.0
                try:
                    if hasattr(node, 'view') and node.view:
                        if hasattr(node.view, 'sceneBoundingRect'):
                            rect = node.view.sceneBoundingRect()
                            if rect and rect.height():
                                measured_height = max(measured_height, float(rect.height()))
                        if hasattr(node.view, 'height'):
                            h = node.view.height()
                            if h:
                                measured_height = max(measured_height, float(h))
                        if hasattr(node.view, 'boundingRect'):
                            rect = node.view.boundingRect()
                            if rect and rect.height():
                                measured_height = max(measured_height, float(rect.height()))
                except Exception:
                    pass

                # Conservative fallback based on number of visible ports.
                # Step nodes grow with many inputs/outputs; this avoids underestimating height.
                try:
                    in_count = len(node.inputs()) if hasattr(node, 'inputs') else 0
                except Exception:
                    in_count = 0
                try:
                    out_count = len(node.outputs()) if hasattr(node, 'outputs') else 0
                except Exception:
                    out_count = 0
                port_rows = max(in_count, out_count)
                estimated_height = 72.0 + (port_rows * 22.0)

                return max(measured_height, estimated_height, float(vertical_gap))

            step_nodes_sorted_by_x = sorted(step_nodes, key=_node_x)
            step_columns = []

            for node in step_nodes_sorted_by_x:
                if not step_columns:
                    step_columns.append({'x': _node_x(node), 'nodes': [node]})
                    continue

                last_column = step_columns[-1]
                if abs(_node_x(node) - last_column['x']) <= step_column_tolerance:
                    last_column['nodes'].append(node)
                    last_column['x'] = sum(_node_x(n) for n in last_column['nodes']) / len(last_column['nodes'])
                else:
                    step_columns.append({'x': _node_x(node), 'nodes': [node]})

            for column in step_columns:
                column_nodes = column['nodes']
                column_nodes.sort(key=lambda n: n.y_pos())
                target_ys = [
                    step_middle + (i - (len(column_nodes) - 1) / 2) * vertical_gap
                    for i in range(len(column_nodes))
                ]

                for i in range(1, len(column_nodes)):
                    prev_node = column_nodes[i - 1]
                    prev_height = _node_height(prev_node)
                    min_y = target_ys[i - 1] + prev_height + minimum_step_gap
                    if target_ys[i] < min_y:
                        target_ys[i] = min_y

                if target_ys:
                    target_middle = (max(target_ys) + min(target_ys)) / 2
                    middle_offset = step_middle - target_middle
                    target_ys = [y + middle_offset for y in target_ys]

                for node, target_y in zip(column_nodes, target_ys):
                    node.set_y_pos(target_y)
    


    def onPortConnected(self, in_port, out_port):
        """
        Handle the signal emitted when a port connection is created.
        
        This method is called automatically when the NodeGraph's port_connected signal is emitted.
        It processes the connection information and emits our custom connection_created signal
        with useful information about the connected nodes and ports.
        
        Args:
            in_port (Port): The input port that received the connection
            out_port (Port): The output port that was connected to the input port
        """
        # print(f"--- [SIGNAL] 'onPortConnected' triggered for: {out_port.node().name()}.{out_port.name()} -> {in_port.node().name()}.{in_port.name()}")
        
        # Get the nodes that own these ports
        source_node = out_port.node()
        target_node = in_port.node()
        
        # Get port names
        source_port_name = out_port.name()
        target_port_name = in_port.name()
        
        # Log the connection
        self.logger_makeedges.info(f"\U0000231B Creating connection: {source_node.name().split('#')[-1]}.{source_port_name} -> "
                                   f"{target_node.name().split('#')[-1]}.{target_port_name}")
        # # if the source is a StepNode and the target is a StepNode do the necessary
        # # updates
        if ( type(source_node).__name__ == 'StepNode' and 
             type(target_node).__name__ == 'StepNode'):
            self.logger_makeedges.info(f"Creating connection: StepNode  -> "
                                       f"StepNode ")
        #     # in the target node, we need to specify that the 
        #     # input with id = target_port_name
        #     # will be getting its source = source_port_name
            target_node.setInputSource( target_port_name, source_node.name(),source_port_name )
        
        # if the source is a StepNode and the target is a StepNode do the necessary
        # updates
        if ( type(source_node).__name__ == 'StepNode' and 
             type(target_node).__name__== 'OutputNode'):
            self.logger_makeedges.info(f"Creating connection: StepNode -> "
                                       f"OutputNode")
            target_node.setInputSource( target_port_name, source_node.name(),source_port_name )
        # If the source is an InputNode, rename it to match the target port name
        # and update it with details from the target port
        if ( type(source_node).__name__ == 'InputNode' and 
             type(target_node).__name__ in ['StepNode', 'ToolNode']):
            self.logger_makeedges.info(f"Creating connection: InputNode  -> "
                                       f"StepNode")
            target_node.setInputSource( target_port_name, source_node.name(),source_port_name )

        
        # # Emit our custom signal with the connection information
        self.logger_makeedges.info('\U0001F6A8 New Port created - updating the network')
        self.editingFinished.emit()
        

    def onPortDisconnected(self, in_port, out_port):
        """
        Handle the signal emitted when a port connection is disconnected.
        
        This method is called automatically when the NodeGraph's port_disconnected signal is emitted.
        It updates the CWL model to reflect the disconnection.
        
        Args:
            in_port (Port): The input port that was disconnected.
            out_port (Port): The output port that was disconnected from the input port.
        """
        source_node = out_port.node()
        target_node = in_port.node()
        
        source_port_name = out_port.name()
        target_port_name = in_port.name()

        self.logger_makeedges.info(f"✂️ Disconnecting: {source_node.name()}.{source_port_name} -> "
                                   f"{target_node.name()}.{target_port_name}")

        # The connection information is stored in the target node's CWL object.
        # We call a method on the target node to remove the source for that specific input port.
        if hasattr(target_node, 'removeInputSource'):
            target_node.removeInputSource(target_port_name, source_node.name(), source_port_name)
            self.logger_makeedges.info(f"Updated CWL for target node '{target_node.name()}' to remove source for port '{target_port_name}'.")
        else:
            self.logger_makeedges.warning(f"Node type {type(target_node).__name__} does not have a 'removeInputSource' method.")
            

        # Emit the signal to indicate the graph has been edited.
        self.editingFinished.emit()




    def onInputNodeUpdated(self,node_id):
        """
        Handle the signal emitted when an input node is updated.
        
        This method is called when an InputNode's inputnodeUpdated signal is emitted.
        It updates the CWL dictionary to reflect the changes made to the node.
        
        Args:
            node (InputNode): The input node that was updated
        """
        self.logger.info(f"Signal updated - Input node updated: {node_id}")
        # print("Signal updated")
        # self.getData()
        self.editingFinished.emit()

    def onOutputNodeUpdated(self,node_id):
        """
        Handle the signal emitted when an output node is updated.
        
        This method is called when an OutputNode's outputnodeUpdated signal is emitted.
        It updates the CWL dictionary to reflect the changes made to the node.
        
        Args:
            node (OutputNode): The output node that was updated
        """
        self.logger.info(f"Signal updated - Output node updated: {node_id}")
        # print("Signal updated")
        # self.getData()
        self.editingFinished.emit()

    def onStepNodeUpdated(self, node_id):
        """
        Handle the signal emitted when a step node is updated.
        
        This method is called when a StepNode's stepnodeUpdated signal is emitted.
        It updates the CWL dictionary to reflect the changes made to the node.
        
        Args:
            node (StepNode): The step node that was updated
        """
        self.logger.info(f"Step node updated: {node_id}")
        
        # Update the CWL dictionary with the latest graph state
        # self.convertGraphToCWL()
        # self.getData()
        self.editingFinished.emit()
        
    def onNodeDoubleClicked(self, node):
        """
        Handle double-click events on nodes in the graph.
        
        Routes the event to the appropriate node's handler. If the node's ID changes
        as a result of the double-click (e.g., through a dialog), this method automatically
        updates all references to the node in connected nodes.
        
        The update process includes:
        1. Calling the node's own renameReferenceOfSelfID to update its internal references
        2. Finding all nodes connected to this node (both input and output connections)
        3. Calling renameReferenceOfConnectedNode on each connected node to update their
           references to the renamed node
        
        Args:
            node: The node that was double-clicked. Must have an onNodeDoubleClicked method
                  and a getCWL() method that returns an object with an 'id' attribute.
        
        Returns:
            None
        
        Side Effects:
            - Emits editingFinished signal after processing
            - Updates CWL references in all connected nodes
            - Logs information about the rename operation
        """
        
        self.logger.debug(f"Double-click detected on node: {node.name()} (type: {type(node).__name__})")
        
        # Check if the node has its own double-click handler
        if hasattr(node, 'onNodeDoubleClicked'):
            self.logger.debug(f"Calling double-click handler for node: {node.name()}")
            old_id=node.getCWL().id
            node.onNodeDoubleClicked(node)
            new_id = node.getCWL().id
            if old_id != new_id:
                resolved_step_id = self.resolveWorkflowStepIDCollision(
                    changed_kind='step',
                    changed_id=new_id
                )
                if resolved_step_id != new_id:
                    node.getCWL().id = resolved_step_id
                    new_id = resolved_step_id

                self.logger.info(f"Node renamed from {old_id} to {new_id}. Updating references.")
                
                node.renameReferenceOfSelfID(old_id, new_id)
                
                # find the nodes that are connected to this node
                # and update the references to the id of this node
                input_connected = node.connected_input_nodes()
                output_connected = node.connected_output_nodes()
                self.logger.info(f"Input connected {input_connected}")
                self.logger.info(f"Output connected {output_connected}")
                
                nodes_to_change=[]
                for input_nodes in list(input_connected.values()) + list(output_connected.values()): # this returns the list of nodes connected to each port.
                    nodes_to_change.extend( input_nodes )
                nodes_to_change=list(set(nodes_to_change))

                self.logger.info(f"This node is referenced in {nodes_to_change}. We will update them")
                
                for n in nodes_to_change:
                    # change the references in these nodes.
                    n.renameReferenceOfConnectedNode( old_id, new_id )
            self.editingFinished.emit()
                
        else:
            self.logger.warning(f"Node {node.name()} does not have a double-click handler")

    def onNodeDeleted( self):
        """Delete all currently selected nodes from the graph."""
        try:
            selected_nodes = self.graph.selected_nodes()
            if not selected_nodes:
                self.logger_removenodes.info("No nodes selected for deletion")
                return
                
            # Confirm deletion if there are multiple nodes
            if len(selected_nodes) > 1:
                reply = QMessageBox.question(
                    self,
                    'Confirm Deletion',
                    f'Delete {len(selected_nodes)} selected nodes?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # Delete the selected nodes (this will trigger onNodeDeleted)
            self.graph.delete_nodes(selected_nodes)
            
            # Rearrange remaining nodes
            # self.arrange_inputs_outputs(force_all=False)
            
            self.logger_removenodes.info(f"\u2705 Deleted {len(selected_nodes)} selected nodes")
            
        except Exception as e:
            self.logger_removenodes.error(f"Error deleting selected nodes: {e}")
        # self.node_deleted.emit()
        self.editingFinished.emit()





if __name__ == '__main__':
    logger=logging.getLogger('')
    formatter = logging.Formatter('%(levelname)s:[%(asctime)s] %(name)s  -  %(message)s')
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.setLevel('WARNING')
    logger.addHandler(stderr_handler)
    # load the configuration
    conf=Configuration()
    conf.loadConfiguration( "config.yaml")#,"dataStructures.yaml"] )
    data.configuration=conf.getConfiguration()
    datatypes=Configuration()
    datatypes.loadConfiguration("dataStructures.yaml")
    builtins.datatypes=datatypes.get('data_types')
    app = QApplication([])
    # window = QMainWindow()
    # window.show()
    # load a test CWL
    tests_dir=Path(__file__).resolve().parents[1] / "tests"
    fn=str(tests_dir / "50-workflow.cwl")
    
    # this is the main CWL that we want to work with
    p=Parser(fn)
    cwl_workflow= p.getCWL()
    # Create main layout and window
    main_layout = QVBoxLayout()

    nw=CWLGraph(workflow_file=fn,
                cwl_workflow=cwl_workflow)
    
    nw.showGraph( )
    main_layout.addWidget(nw)

    # Set up a central widget and show the window
    central_widget = QWidget()
    central_widget.setLayout(main_layout)
    window = QMainWindow()
    window.setCentralWidget(central_widget)
    window.show()

    app.exec()



