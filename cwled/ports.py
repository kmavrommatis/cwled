import re
import logging
import data
import inspect

class PortSplitter:
    """
    A class to parse a CWL port identifier string and break it into its constituent parts.
    
    This utility class parses complex CWL port identifiers that may include file paths,
    workflow IDs, step IDs, and port names. It intelligently separates these components
    to allow easy access to individual parts of the port reference.
    
    Attributes:
        filename (str or None): 
            The file path component before the '#' character.
            Example: "file.cwl" in "file.cwl#workflow_id/step1/output1"
        
        full_port (str or None):
            The complete port identifier after the '#' character (everything except filename).
            Contains workflow_id, step_id, and port_id separated by '/'.
            Example: "workflow_id/step1/output1"
        
        node (str or None):
            All components except the final port_id, joined with '/'.
            Represents the path to the node without its port.
            Example: "workflow_id/step1" (everything before the last '/')
        
        stepport (str or None):
            The step_id and port_id joined with '/'. This is the step-relative port reference.
            If no step_id exists, contains only the port_id.
            Example: "step1/output1" or just "output1" if no step
        
        port_id (str):
            The final component after the last '/' character.
            Represents the port name itself (input or output parameter name).
            Example: "output1" in "file.cwl#workflow_id/step1/output1"
        
        step_id (str or None):
            The step identifier(s) between the workflow_id and port_id, joined with '/'.
            Can contain nested steps for complex workflows.
            Example: "step1" in "file.cwl#workflow_id/step1/output1"
            Example: "substep1/step2" for nested steps
        
        workflow_id (str or None):
            The workflow identifier, which is the first component after '#' if it matches
            the provided workflow_id parameter. Set to None if the first component doesn't
            match the expected workflow_id.
            Example: "workflow_id" in "file.cwl#workflow_id/step1/output1"
    
    Example usages:
        
        # Example 1: Full qualified port with file path
        ps1 = PortSplitter("file.cwl#workflow1/step1/output1", workflow_id="workflow1")
        # Results:
        # filename = "file.cwl"
        # full_port = "workflow1/step1/output1"
        # node = "workflow1/step1"
        # stepport = "step1/output1"
        # port_id = "output1"
        # step_id = "step1"
        # workflow_id = "workflow1"
        
        # Example 2: Port without file path
        ps2 = PortSplitter("step2/input1", workflow_id="workflow1")
        # Results:
        # filename = None
        # full_port = "step2/input1"
        # node = "step2"
        # stepport = "step2/input1"
        # port_id = "input1"
        # step_id = "step2"
        # workflow_id = None (no matching workflow ID in port)
        
        # Example 3: Workflow output (no step)
        ps3 = PortSplitter("final_output", workflow_id="workflow1")
        # Results:
        # filename = None
        # full_port = "final_output"
        # node = None
        # stepport = "final_output"
        # port_id = "final_output"
        # step_id = None
        # workflow_id = None
        
        # Example 4: Nested steps
        ps4 = PortSplitter("file.cwl#workflow1/substep1/step2/result", workflow_id="workflow1")
        # Results:
        # filename = "file.cwl"
        # full_port = "workflow1/substep1/step2/result"
        # node = "workflow1/substep1/step2"
        # stepport = "substep1/step2/result"
        # port_id = "result"
        # step_id = "substep1/step2"
        # workflow_id = "workflow1"
    """

    def __str__(self):
        """
        Return a string representation of the PortSplitter object.
        
        Shows a formatted summary of the parsed port components in the order:
        workflow_id / step_id / port_id
        
        Returns:
        str: A string in the format "<PortSplitter>: {workflow_id} / {step_id} / {port_id}\"
        where any component can be None
        
        Example:
        ps = PortSplitter("file.cwl#wf1/step1/output", workflow_id="wf1")
        print(ps)  # Output: <PortSplitter>: wf1 / step1 / output
              
        """
        return( f"<PortSplitter>: {self.workflow_id} / {self.step_id} / {self.port_id} " )
    
    def __eq__(self,other):
        """
        Compare two PortSplitter objects for equality.
        
        Two PortSplitter objects are considered equal if:
        1. Their full_port values match exactly, OR
        2. All non-None components match (port_id, step_id, and workflow_id)
        
        This flexible comparison allows matching ports with different levels of
        specificity. For example, a port with no workflow_id will match a port
        that has the same step_id and port_id, even if one specifies the workflow.
        
        Comparison Strategy:
            - First checks if both have full_port values and they're identical (fast path)
            - If not identical, compares individual components
            - For each component (port_id, step_id, workflow_id):
                * If both values are not None, they must match
                * If either value is None, that component is skipped
            - Returns True only if all non-None components agree
        
        Args:
            other: Another object to compare with (should be PortSplitter instance)
        
        Returns:
            bool: True if the ports are equal, False otherwise
            NotImplemented: If other is not a PortSplitter instance
        
        Examples:
            ps1 = PortSplitter("step1/output", workflow_id="wf")
            ps2 = PortSplitter("step1/output", workflow_id="wf")
            assert ps1 == ps2  # True - identical
            
            ps3 = PortSplitter("step1/output", workflow_id="wf")
            ps4 = PortSplitter("wf/step1/output", workflow_id="wf")
            # ps3 and ps4 may be equal if port components match
            
            ps5 = PortSplitter("step2/output", workflow_id="wf")
            assert ps1 != ps5  # False - different step_id
        """
        if not isinstance(other, PortSplitter):
            return NotImplemented

        if self.full_port is not None and other.full_port is not None and self.full_port == other.full_port:
            return True

        # Compare port_id, but only if both are not None
        if self.port_id is not None and other.port_id is not None:
            if self.port_id != other.port_id:
                return False

        # Compare step_id, but only if both are not None
        if self.step_id is not None and other.step_id is not None:
            if self.step_id != other.step_id:
                return False

        # Compare workflow_id, but only if both are not None
        if self.workflow_id is not None and other.workflow_id is not None:
            if self.workflow_id != other.workflow_id:
                return False
        
        return True


    def __init__(self, port: str, workflow_id: str = None):
        """
        Initializes the PortSplitter and parses the port string.
        
        This method breaks down a complex CWL port identifier string into its constituent
        components (filename, workflow ID, step ID, and port ID). The parsing logic
        intelligently determines which parts are present based on the structure of the
        port string and the provided workflow_id.
        
        Parsing Logic:
            1. Splits by '#' to separate filename from the port specification
            2. Extracts port_id as the last component after the final '/'
            3. Checks if the first remaining component matches the provided workflow_id
            4. Sets step_id to any components between workflow_id and port_id
            5. Constructs derived fields (node, stepport) from the components

        Args:
            port (str): 
                The port identifier string to parse. Can take various formats:
                - "filename.cwl#workflow_id/step_id/port_id" (fully qualified)
                - "step_id/port_id" (workflow-relative, no file)
                - "port_id" (just the port name)
                Can contain nested steps separated by '/' (e.g., "step1/substep/port")
                
            workflow_id (str):
                The expected workflow identifier. Used to determine if the first
                component of the port string is a workflow ID. If the first
                component matches this value, it will be stored as workflow_id;
                otherwise, it's treated as part of the step path.
                Example: If port="workflow1/step1/out" and workflow_id="workflow1",
                then workflow_id will be set; if workflow_id="workflow2", then
                workflow_id will be None and step_id will be "workflow1/step1"
        
        Raises:
            ValueError: If port or workflow_id is empty or None
            
        Examples:
            # Example 1: Complete port with file
            ps = PortSplitter("tool.cwl#my_workflow/my_step/output", workflow_id="my_workflow")
            # workflow_id = "my_workflow"
            # step_id = "my_step"
            # port_id = "output"
            # filename = "tool.cwl"
            
            # Example 2: Workflow-relative port without file
            ps = PortSplitter("process_step/result", workflow_id="main_workflow")
            # workflow_id = None
            # step_id = "process_step"
            # port_id = "result"
            # filename = None
            
            # Example 3: Bare port name
            ps = PortSplitter("input_file", workflow_id="main_workflow")
            # workflow_id = None
            # step_id = None
            # port_id = "input_file"
            # filename = None
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG'))
        
        self.filename = None
        self.full_port = None # everything including workflow id, step, port
        self.node = None  # all except port id
        self.stepport=None # step and port id

        self.port_id = None
        self.workflow_id = None
        self.step_id = None

        if not port :
            raise ValueError("PortSplitter received an empty or None port string.")
        if not workflow_id:
            raise ValueError("PortSplitter received an empty or None workflow_id string.")

        try:
            if '#' in port:
                self.filename, self.full_port = port.split('#', 1)
            else:
                self.filename = None
                self.full_port = port
        except ValueError as e:
            self.logger.error(f"Error splitting port '{port}' by '#': {e}")
            return

        if '#' in workflow_id:
            workflow_id = workflow_id.split('#', 1)[-1]

        parts = self.full_port.split('/')
        self.port_id = parts.pop(-1)
        self.stepport=self.port_id
        
        # if we have something let in the list we have steps and potentially workflow

        if parts:
            self.node = '/'.join(parts)
            if parts[0] == workflow_id:
                self.workflow_id = parts.pop(0) 
            else:
                self.workflow_id = None
        
        # This is the step id
        if parts:
            self.step_id = '/'.join(parts)
            self.stepport=self.step_id + '/' + self.port_id
        else:
            self.step_id = None

        self.logger.debug(f"Splitting '{port}' results in: "
                          f"filename={self.filename}, full_port={self.full_port}, "
                          f"node={self.node}, stepport={self.stepport},  workflow_id={self.workflow_id}, "
                          f"step_id={self.step_id}, port_id={self.port_id}")

    
