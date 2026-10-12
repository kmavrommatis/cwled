import json
import os
from ruamel.yaml import YAML
from typing import List, Tuple, Union
from pathlib import Path, PosixPath
import logging
import sys
import shutil
from platformdirs import user_config_path
from helperFunctions import getResourcePath
'''
class to handle the configuration files.
'''

class Configuration(object):

    def __init__(
            self, 
            configuration_directory=Path(__file__).resolve().parent.parent / 'config' # default configuration.
            ):
        """
        Docstring for __init__
        
        :param self: Description
        :param configuration_directory: The configuration directory of the application. This is the source of the configuration BUT NOT the config file it reads.
          """


        self.configuration={}
        self.default_directory=None
        self.logger=logging.getLogger(self.__class__.__name__)
        self.logger.setLevel('WARN')
    
        self.setConfigurationDirectory(configuration_directory)
        self.setUserConfigurationDirectory()

        



    def loadConfiguration(self, file:str|list='cwled.yaml'):
        '''
        load configuration options from a configuration file
        this function can be called multiple times
        to load configuration from many files
        If a key is present in more than one files then
        only the last instance is kept
        If the file does not exist in the self.user_directory it will
        copy it from the self.directory and load it afterwards
        '''
        yaml=YAML()
        if not type(file) is list:
            file=[file]
            if not hasattr(self.configuration, 'conf_file'):
                self.configuration['conf_file']=[]
        for k in file:
            self.logger.debug(f"Loading configuration from {k}")
            dot_file=self._stageConfigurationFile(k)
            with open( dot_file ) as f:
                self.logger.info(f"Loading configuration from {dot_file}")
                yaml = YAML()
                d=yaml.load( f )
                self.configuration={**self.configuration, **d}
            self.configuration['conf_file'].append(str(dot_file))
        e=self.checkConfiguration()

        if e:
            raise LookupError(f"The configuration file {file} does not contain proper information\b{e}")
        self.logger.setLevel(self.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG'))
        
    
    def resetConfigurationFile(self, file:Union[str,Path,PosixPath]) -> Path:
        """
        Docstring for resetConfigurationFile
        
        :param file: resets the configuration file in the user directory by copying it from the default configuration directory
        :returns : the update filename.
        """
        return self._stageConfigurationFile(file, reset=True)
    

    def _stageConfigurationFile(self, file:Union[str,Path,PosixPath] , reset=False) -> Path:
        """
        Docstring for _stageConfigurationFile
        
        :param file: checks if the config file exists in the user directory, and if not it creates it
        :param reset: if True it resets the configuration file in the user directory by copying it from the default configuration directory
        :returns : the update filename.
        """
        dot_file=str(file)
        # if not file.startswith("."):
        #     dot_file=f".{file}"
       
        if Path( self.user_directory).joinpath(dot_file).exists() and reset is False:
            pass
        else:
            if Path(self.default_directory).joinpath(file):
                shutil.copyfile( 
                    str(Path(self.default_directory).joinpath(file)),
                    str(Path( self.user_directory).joinpath(dot_file))
                )
                self.logger.info(f"Copied default configuration file {file} to user directory {self.user_directory}")
            else:
                self.logger.critical(f"Cannot find configuration file {file}")
        
        return Path( self.user_directory).joinpath(dot_file)

        
    
    def saveConfiguration(self, file:str='cwled.yaml'):
        '''
        save the current configuration to a file
        '''
        if self.configuration is None:
            raise ValueError("No configuration to save")
        yaml=YAML()

        dot_file=self._stageConfigurationFile(file)
        # print(" ######### Saving configuration to ", Path(self.user_directory).joinpath(dot_file))
        with open( dot_file, 'w') as f:
            yaml.dump( self.configuration, f )
            self.logger.info(f"Saved configuration to {dot_file}")
        return dot_file
    


    def getConfiguration(self)->dict:
        # In a frozen environment, rewrite cwl_runner commands to execute internally via --run-module
        if getattr(sys, 'frozen', False):
            runner_config = self.configuration.get('cwl_runner', {})
            for key, value in list(runner_config.items()):
                if not isinstance(value, str):
                    continue
                parts = value.split()
                if not parts:
                    continue
                cmd_name = parts[0]
                if cmd_name in ['cwltool', 'cwlpack', 'cwl-upgrader', 'cwl-explode']:
                    # Reconstruct the command using sys.executable --run-module <cmd_name>
                    new_value = f"{sys.executable} --run-module {cmd_name} " + " ".join(parts[1:])
                    runner_config[key] = new_value.strip()
        return self.configuration

    def setConfiguration(self, configuration:dict):
        self.configuration = configuration
        self.checkConfiguration()



    def setConfigurationDirectory( self, directory:str=None) -> str:
        '''
        set the directory where the configuration files are found
        '''
        if directory:
            self.default_directory=directory
    
    def setUserConfigurationDirectory (self) -> str:
        """
        Sets the directory where the user configuration files are stored.
        It uses platformdirs to find the appropriate user config directory for 'cwled'
        and creates it if it doesn't exist.
        For MacOS: ~/Library/Application Support/cwled
        For Linux: ~/.config/cwled/
        """

        self.user_directory=user_config_path( 
            appname='cwled',
            ensure_exists=True
        )
        # self.user_directory=Path.home() / 'config'/ 'cwled'
        # os.makedirs(self.user_directory, exist_ok=True)


    def checkConfiguration(self) -> str:
        '''
        empty function
        checks if the configuration contains
        the proper information
        To be implememnted in each subclass

        returns a string with the description of the problem
        '''
        self.configuration['conf_file']=list(set(self.configuration.get('conf_file', [])))
        for k in self.configuration.get('icons', {}) :
            p=self.configuration['icons'][k]
            if Path(p).exists() and Path(p).is_absolute():
                continue
            else:
                p=str(getResourcePath().parent / p)
                self.configuration['icons'][k]=p
            if not Path(p).exists():
                raise FileNotFoundError(f"Icon file {p} not found")
        for p in self.configuration.get('paths',[])  :
            if Path(p).exists():
                os.environ['PATH']+=os.pathsep+str(Path(p).resolve())
        # self.configuration['custom_path']=os.environ['PATH']
            
        if self.configuration.get('workspace') :
            if not Path(self.configuration['workspace']).exists():
                self.logger.warning(f"\u26A0Workspace path {self.configuration['workspace']} not found")
                self.configuration['workspace']=None
        return None
    
    def addRecentFile(self, file_path:Union[str,Path,PosixPath]):
        """
        Add a file to the list of recently opened files.
        Files are appended to the end of the list.
        If the list exceeds 10 files, the oldest one (first in list) is removed.
        
        :param file_path: The full path to the file to add to recent files
        """
        file_path = str(Path(file_path).resolve())
        
        # Initialize recents section if it doesn't exist
        if 'recents' not in self.configuration:
            self.configuration['recents'] = []
        
        # Remove the file if it already exists in the list (to avoid duplicates)
        if file_path in self.configuration['recents']:
            self.configuration['recents'].remove(file_path)
        
        # Append the file to the end of the list
        self.configuration['recents'].append(file_path)
        
        # Keep only the last 10 files (remove oldest ones from the beginning)
        if len(self.configuration['recents']) > 10:
            self.configuration['recents'] = self.configuration['recents'][-10:]
        
        # Save the configuration
        self.saveConfiguration()
        self.logger.info(f"Added {file_path} to recent files")    