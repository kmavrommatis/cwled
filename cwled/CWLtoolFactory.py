import subprocess
import os
import logging
from pathlib import Path
import tempfile
import data
from typing import Any
from CWLparser import Parser
import sys
import shutil
from shutil import which
from ruamel.yaml import YAML
class CWLRunner(object):
    '''
    class to handle various activities with cwltool et al
    '''

    def __init__(self):
        super().__init__()
        # load the configuration
        self.logger=logging.getLogger(__name__)
        self.logger.setLevel(data.configuration.get('logLevel',{}).get(__name__, 'DEBUG'))
        self.checkTools()

    def _resolve_command(self, command: str) -> str:
        '''
        Resolve a command to its full path.
        If command is an absolute path, check if it exists and is executable.
        If command is a name, search for it in PATH.
        Returns the resolved path or None if not found.
        '''
        self.logger.debug(f"Attempting to resolve command: '{command}'")
        
        # Check if it's an absolute path
        if os.path.isabs(command):
            self.logger.debug(f"Command is absolute path: {command}")
            if os.path.isfile(command) and os.access(command, os.X_OK):
                self.logger.debug(f"\u2713 Command exists and is executable: {command}")
                return command
            else:
                self.logger.warning(f"\u2717 Command not found or not executable: {command}")
                return None
        
        # Build search path including configured paths
        search_path = os.environ.get('PATH', '')
        
        # Add system standard paths that might be missing in GUI bundled apps
        system_paths = []
        if sys.platform == 'darwin':
            system_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
        elif sys.platform == 'linux':
            system_paths = [str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin"]
            
        for p in system_paths:
            if Path(p).exists() and p not in search_path.split(':'):
                search_path = p + ':' + search_path
        
        # Add configured paths if they exist
        config_paths = data.configuration.get('paths', [])
        if config_paths:
            self.logger.debug(f"Adding configured paths to search: {config_paths}")
            expanded_paths = []
            for cp in config_paths:
                expanded = os.path.expanduser(str(cp))
                if Path(expanded).exists():
                    expanded_paths.append(expanded)
            additional_paths = ':'.join(expanded_paths)
            if additional_paths:
                search_path = additional_paths + ':' + search_path
        
        self.logger.debug(f"Searching in PATH: {search_path}")
        
        # Try to find the command in PATH
        resolved = which(command, path=search_path)
        
        if resolved:
            self.logger.info(f"\u2713 Resolved '{command}' to: {resolved}")
        else:
            self.logger.warning(f"\u2717 Could not resolve '{command}' in PATH")
            
        return resolved

    def checkTools(self)->bool:
        '''
        check if the required python packages are imported and available.
        '''
        self.logger.info("Checking in-process tools availability")
        try:
            import cwltool.main
            import sbpack.pack
            import cwlupgrader.main
            import cwlformat.explode
            self.logger.info("\u2713 All in-process tools (cwltool, sbpack, cwlupgrader, cwlformat) are available")
            # cwltool sets its own logger to INFO when it is imported, which
            # undoes the pin applied at startup.
            from logger import pinThirdPartyLoggers
            pinThirdPartyLoggers()
            return True
        except ImportError as e:
            self.logger.error(f"Failed to import required in-process package: {e}")
            return False

    def _loadingContext(self):
        '''
        Build a cwltool LoadingContext that uses the CWLed fetcher.

        Documents with a `$namespaces` prefix that does not end in `/` or `#`
        (e.g. `sbg: 'https://sevenbridges.com'`) make schema-salad link-check
        URIs such as `https://sevenbridges.comSaveLogs` over the network, once
        per extension tag. The CWLed fetcher answers those without a request.
        Everything else keeps cwltool's defaults, which match the CLI defaults
        for validation (strict, do_validate).
        '''
        from cwltool.context import LoadingContext
        from cwl_fetcher import CWLedFetcher

        return LoadingContext({'fetcher_constructor': CWLedFetcher})

    def _runCwltool(self, argsl: list, stdout_buf, stderr_buf) -> int:
        '''
        Run cwltool in-process and collect its log output in stderr_buf.

        Passing `logger_handler` stops cwltool from calling
        `coloredlogs.install()`, which resets the cwltool logger to INFO on
        every run - undoing the WARNING pin - and sends the log to stdout
        rather than stderr whenever `--validate` is used.

        Args:
            argsl: the cwltool command line, without the program name.
            stdout_buf: buffer receiving whatever cwltool prints (e.g. a template).
            stderr_buf: buffer receiving cwltool's log records.

        Returns:
            int: the cwltool exit code.
        '''
        import cwltool.main
        from cwltool.loghandler import _logger as cwltool_logger
        from logger import pinThirdPartyLoggers

        handler = logging.StreamHandler(stderr_buf)
        try:
            return cwltool.main.main(
                argsl=argsl,
                stdout=stdout_buf,
                stderr=stderr_buf,
                loadingContext=self._loadingContext(),
                logger_handler=handler
            )
        finally:
            # cwltool attaches the handler to its module-level logger and
            # shares that handler list with the salad logger, so it has to be
            # detached or every later run would also write into this buffer.
            cwltool_logger.removeHandler(handler)
            logging.getLogger('salad').removeHandler(handler)
            # cwltool's configure_logging() moves its own and salad's levels.
            pinThirdPartyLoggers()

    def validate( self , filename:str) -> bool:
        '''
        Validates a CWL file in-process and returns either True or False.
        If the tool does not pass validation it will preserve the output in self.stderr.
        '''
        import io

        self.logger.info(f"Starting in-process validation for file: {filename}")

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            exit_code = self._runCwltool(
                ['--disable-color', '--no-warnings', '--validate', filename],
                stdout_buf,
                stderr_buf
            )
            
            self.stdout = stdout_buf.getvalue()
            self.stderr = stderr_buf.getvalue()
            
            self.logger.info(f"Validation completed with exit code: {exit_code}")
            
            if exit_code == 0:
                self.logger.info("\u2705 Validation successful")
                return True
            else:
                self.logger.warning(f"Validation failed with exit code {exit_code}")
                self.logger.debug(f"STDOUT: {self.stdout}")
                self.logger.debug(f"STDERR: {self.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Unexpected error during validation: {e}")
            self.stderr = f"Unexpected error: {str(e)}"
            self.stdout = ""
            return False
        
    def upgrade( self, input_filename: str, output_filename=None, toversion:str ='v1.2') -> Path:
        '''
        UPgrade a CWL tool to a more recent version
        It stores the update file in the location the user provides
        under the same file as teh original
        '''
        
        if toversion == 'v1.0':
            version_cmd="--v1-only"
        elif toversion == 'v1.1':
            version_cmd="--v1.1-only"
        else:
            version_cmd=""

        
        output_directory=Path(output_filename).parent
        temp_output=False
        if output_directory == Path(input_filename).parent:
            # use a temp directory to store the upgraded file
            output_directory=Path(tempfile.mkdtemp(dir=output_directory.parent))
            temp_output=True
        
        import io
        import contextlib
        import cwlupgrader.main

        args = ['--dir', str(output_directory)]
        if version_cmd:
            args.append(version_cmd)
        args.append(input_filename)
        self.logger.debug(f"Upgrading CWL using programmatic upgrader with args: {args}")

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        
        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                exit_code = cwlupgrader.main.main(args=args)
                
            self.stdout = stdout_buf.getvalue()
            self.stderr = stderr_buf.getvalue()
            
            self.logger.debug(f"Upgrade returns exit code {exit_code}")
            if exit_code == 0:
                # copy the file in the output_directory to the output_filename
                shutil.copy(output_directory / Path(input_filename).name , output_filename)
                return output_filename
            else:
                raise Exception( f"Unable to upgrade the document: {self.stderr}")
        except Exception as e:
            self.stderr = str(e)
            self.stdout = ""
            raise Exception( f"Unable to upgrade the document: {e}")
        finally:
            # clean up the temp directory if we used one
            if temp_output:
                shutil.rmtree(output_directory, ignore_errors=True)

    def stageWorkflow(self, target_filename:str, existing_filename:str):
        """
        restructure the pipeline by caling the tools

        cwl-explode <packed pipeline> <output-file>
        Args:
            filename: the output filename with the packed workflow
            existing_filename: the CWL object (tool or workflow) to pack
        """
        import pathlib
        from cwlformat.explode import explode, CWLProcess

        # first we need to pack the pipeline
        # and store it in temp file
        tmp_cwl = tempfile.NamedTemporaryFile(delete=False, suffix='.cwl', mode='w')
        tmp_dir= Path(tmp_cwl.name).parent
        self.packWorkflow(
            existing_filename=existing_filename, 
            filename=tmp_cwl.name)
        
        self.logger.info("Programmatically exploding workflow")
        try:
            yaml = YAML()
            fp = pathlib.Path(tmp_cwl.name).absolute()
            as_dict = yaml.load(fp.read_text())
            fp_out = pathlib.Path(tmp_dir / Path(target_filename).name).absolute()
            
            # Execute the expansion programmatically
            for exploded in explode(CWLProcess(as_dict, fp_out)):
                exploded.save()
            
            self.stdout = ""
            self.stderr = ""
            shutil.move( str(tmp_dir / Path(target_filename).name) , target_filename)
            shutil.rmtree(target_filename + ".steps", ignore_errors=True)
            shutil.move( str(tmp_dir / Path(target_filename).name) + '.steps' , target_filename + ".steps")
            self.logger.info(f"\u2705 Explode completed successfully")
        except Exception as e:
            self.stderr = str(e)
            self.stdout = ""
            raise Exception( f"Unable to stage the pipeline: {e}")
        finally:
            Path(tmp_cwl.name).unlink()


    def packWorkflow(self, filename:str, existing_filename:str) :
        """
        pack a workflow by running the command 

        cwl-pack ... <workflow-file> > <output-file>

        Args:
            filename: the output filename with the packed workflow
            existing_filename: the CWL object (tool or workflow) to pack

        """
        import sbpack.pack
        import json
        
        self.logger.info(f"Programmatically packing workflow: {existing_filename}")
        try:
            # Resolves, links, and bundles all workflow steps in-process
            packed_cwl = sbpack.pack.pack(
                cwl_path=existing_filename,
                filter_non_sbg_tags=True, # equivalent to --filter-non-sbg-tags
                add_ids=True             # equivalent to --add-ids
            )
            
            self.stdout = json.dumps(packed_cwl, indent=4)
            self.stderr = ""
            self.logger.info("✓ Pack completed successfully")
            Path(filename).write_text(self.stdout)
        except Exception as e:
            self.stderr = str(e)
            self.stdout = ""
            self.logger.error(f"Failed to pack workflow: {e}")
            raise Exception(f"Failed to pack workflow: {e}")



    def makeTemplate(self, cwl_content: str, source_path: str | None = None) -> dict | None:
        """
        Generate a CWL template from a CWL tool definition.
        
        Args:
            cwl_content: CWL tool definition as string
            source_path: Optional original CWL file path. When provided,
                        temporary files are created in the same directory so
                        relative `run` references in workflows remain valid.
            
        Returns:
            dict: The parsed YAML template as a dictionary, or None if generation failed
        """
        import tempfile
        import yaml

        temp_dir = None
        if source_path:
            try:
                candidate_dir = Path(source_path).resolve().parent
                if candidate_dir.exists() and candidate_dir.is_dir():
                    temp_dir = str(candidate_dir)
            except Exception:
                temp_dir = None

        # Create a temporary file for the CWL content
        tmp_cwl = tempfile.NamedTemporaryFile(
            delete=False,
            suffix='.cwl',
            mode='w',
            dir=temp_dir,
            encoding='utf-8'
        )
        tmp_cwl_path = tmp_cwl.name
        
        try:
            # Write CWL content to temporary file
            tmp_cwl.write(cwl_content)
            tmp_cwl.close()
            
            # Validate the CWL file first
            self.logger.debug("Validating CWL file before generating template")
            if not self.validate(tmp_cwl_path):
                self.logger.warning("CWL validation failed")
                error_message = f"Stdout: {getattr(self, 'stdout', '')}\n"
                error_message += f"Stderr: {getattr(self, 'stderr', '')}"
                self.logger.warning(f"Validation errors: {error_message}")
                return None
            
            import io

            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()

            self.logger.debug(f"Generating template programmatically for {tmp_cwl_path}")

            exit_code = self._runCwltool(
                ['--make-template', tmp_cwl_path],
                stdout_buf,
                stderr_buf
            )
            
            self.stdout = stdout_buf.getvalue()
            self.stderr = stderr_buf.getvalue()
            
            if exit_code != 0:
                self.logger.warning(f"Failed to generate template: {self.stderr}")
                return None
                
            # Get the template YAML from stdout
            template_yaml = self.stdout
            self.logger.debug(f"Generated template YAML: {template_yaml}")
            
            # Parse the YAML into a dictionary
            try:
                yaml = YAML()
                template_dict = yaml.load(template_yaml)
                return template_dict
            except Exception as e:
                self.logger.warning(f"Failed to parse template YAML: {str(e)}")
                self.stderr = str(e)
                return None
                
        except Exception as e:
            self.logger.warning(f"Error generating template: {str(e)}")
            import traceback
            self.logger.warning(traceback.format_exc())
            self.stderr = str(e)
            return None
        finally:
            # Clean up temporary CWL file
            try:
                os.unlink(tmp_cwl_path)
            except Exception as e:
                self.logger.warning(f"Failed to remove temporary file: {e}")
                
        return None

    def runWorkflow(self, cwl_content: str, cwl_inputs: str) -> dict:
        """
        Execute a CWL workflow with the specified inputs, with a 3-second timeout.
        
        Args:
            cwl_content (str): The CWL tool/workflow definition
            cwl_inputs (str): The CWL inputs in YAML/JSON format
            
        Returns:
            dict: A dictionary with execution results including:
                - success: Boolean indicating if execution was successful
                - stdout: Standard output from the command
                - stderr: Standard error from the command
                - timed_out: Boolean indicating if the execution timed out
        """
        import tempfile
        import time
        import signal
        
        # Create temporary files for CWL content and inputs
        tmp_cwl = tempfile.NamedTemporaryFile(delete=False, suffix='.cwl', mode='w')
        tmp_cwl_path = tmp_cwl.name
        
        tmp_inputs = tempfile.NamedTemporaryFile(delete=False, suffix='.yml', mode='w')
        tmp_inputs_path = tmp_inputs.name
        
        result = {
            'command': '',
            'success': False,
            'stdout': '',
            'stderr': '',
            'timed_out': False
        }
        
        try:
            # Write content to temporary files
            tmp_cwl.write(cwl_content)
            tmp_cwl.close()
            
            tmp_inputs.write(cwl_inputs)
            tmp_inputs.close()
            
            # Build the command
            cmd = data.configuration.get('cwl_runner', {}).get('execute', '').split()
            if not cmd:
                self.logger.warning("Execute command not found in configuration")
                result['stderr'] = "Execute command not configured"
                return result
                
            cmd.append(tmp_cwl_path)
            cmd.append(tmp_inputs_path)
            self.logger.debug(f"Executing workflow with command: {' '.join(cmd)}")
            result['command']=' '.join(cmd)
            # Start the process
            env = os.environ.copy()
            env['PATH']=os.environ['PATH']
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Set a timer to kill the process after 3 seconds
            start_time = time.time()
            timeout = 10 # seconds
            
            stdout_chunks = []
            stderr_chunks = []
            
            # Poll the process with timeout
            while process.poll() is None:
                # Check if we've exceeded timeout
                if time.time() - start_time > timeout:
                    self.logger.warning(f"Process exceeded {timeout} seconds timeout, terminating")
                    process.terminate()
                    try:
                        # Wait a bit for graceful termination
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate gracefully
                        process.kill()
                    
                    result['timed_out'] = True
                    break
                
                # Use a more robust approach for non-blocking IO
                import select
                
                # Set up select to monitor stdout and stderr
                read_set = []
                if process.stdout:
                    read_set.append(process.stdout)
                if process.stderr:
                    read_set.append(process.stderr)
                
                if read_set:
                    # Wait for up to 0.1 seconds for output
                    readable, _, _ = select.select(read_set, [], [], 0.1)
                    
                    for fd in readable:
                        if fd == process.stdout:
                            line = process.stdout.readline()
                            if line:
                                stdout_chunks.append(line)
                                self.logger.debug(f"STDOUT: {line.strip()}")
                        
                        if fd == process.stderr:
                            line = process.stderr.readline()
                            if line:
                                stderr_chunks.append(line)
                                self.logger.debug(f"STDERR: {line.strip()}")
                
                # Short sleep to prevent CPU hogging
                time.sleep(0.1)
            
            # Capture any remaining output
            stdout, stderr = process.communicate()
            if stdout:
                stdout_chunks.append(stdout)
            if stderr:
                stderr_chunks.append(stderr)
            
            # Combine all output chunks
            result['stdout'] = ''.join(stdout_chunks)
            
            # Get the full stderr - ensure we have newlines properly maintained
            full_stderr = ''.join(stderr_chunks)
            
            # Debug print the entire stderr for troubleshooting
            self.logger.debug(f"Full stderr length: {len(full_stderr)} characters")
            
            # Special handling if stderr seems to be missing line breaks
            if full_stderr and '\n' not in full_stderr:
                self.logger.warning("No newlines found in stderr, attempting to format")
                # Try to add line breaks after periods or common delimiters
                import re
                full_stderr = re.sub(r'([.!?]) ', r'\1\n', full_stderr)
            
            # Limit stderr to the top 20 lines if it's long
            stderr_lines = full_stderr.splitlines()
            self.logger.debug(f"Found {len(stderr_lines)} stderr lines")
            
            if len(stderr_lines) > 20:
                self.logger.debug(f"Limiting stderr from {len(stderr_lines)} lines to top 20")
                result['stderr'] = '\n'.join(stderr_lines[:20]) + '\n[...truncated...]'
            else:
                result['stderr'] = full_stderr
            
            # Set instance attributes for consistency with other methods
            self.stdout = result['stdout']
            self.stderr = result['stderr']
                
            result['success'] = process.returncode == 0 and not result['timed_out']
            
            self.logger.debug(f"Process completed with return code: {process.returncode}")
            

            


            return result
            
        except Exception as e:
            self.logger.error(f"Error executing workflow: {str(e)}")
            import traceback
            error_traceback = traceback.format_exc()
            self.logger.error(error_traceback)
            
            # Include both the exception message and traceback in stderr (limited to 20 lines)
            error_message = f"Error: {str(e)}\n\n{error_traceback}"
            error_lines = error_message.splitlines()
            
            if len(error_lines) > 20:
                result['stderr'] = '\n'.join(error_lines[:20]) + '\n[...truncated...]'
            else:
                result['stderr'] = error_message
            
            # Set instance attributes for consistency
            self.stderr = result['stderr']
            self.stdout = result.get('stdout', '')
                
            return result
            
        finally:
            # Clean up temporary files
            try:
                os.unlink(tmp_cwl_path)
                os.unlink(tmp_inputs_path)
            except Exception as e:
                self.logger.warning(f"Failed to remove temporary files: {e}")
                
        return result






if __name__ == '__main__':

    from cwl_utils_handler import CWLType,get_cwl_module
    from cwl_utils.parser import save
    from CWLparser import Parser
    from CWLtoolFactory import CWLRunner as cr
    from configuration import Configuration
    import json, yaml
    # load the configuration
    conf=Configuration()
    conf.loadConfiguration( "config.yaml")#,"dataStructures.yaml"] )
    data.configuration=conf.getConfiguration()
    datatypes=Configuration()
    datatypes.loadConfiguration("dataStructures.yaml")
    data.datatypes=datatypes.getConfiguration()

    tests_dir=Path(__file__).resolve().parents[1] / "tests"
    cwl_dict=Parser( str(tests_dir / "12-tar-param.cwl")).getCWL()
    with open(tests_dir / '12-tar-param-inputs.yaml', 'r') as f:
        yaml = YAML()
        cwl_inputs=yaml.load(f)

    runner=cr()
    print(f"cwl_content={save( cwl_dict )}, cwl_inputs= {json.dumps( cwl_inputs)}")
    result=runner.runWorkflow(cwl_inputs=json.dumps( cwl_inputs),
                   cwl_content=json.dumps(save( cwl_dict )))
    

    print(f"Result\n{json.dumps(result)}")