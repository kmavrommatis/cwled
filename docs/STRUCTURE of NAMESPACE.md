#What is the structure of workflows:

```
from cwl_utils_handler import CWLType,get_cwl_module
from cwl_utils.parser import save
from CWLparser import Parser

#cwl_dict=Parser( "tests/sort.cwl").getCWL()
# Load your test file with namespaces
parser = Parser("tests/sort.cwl")
cwl_tool = parser.getCWL()

# Check all attributes
print("All attributes:")
print([attr for attr in dir(cwl_tool) if not attr.startswith('_')])

print("\nExtension fields:")
print(cwl_tool.extension_fields if hasattr(cwl_tool, 'extension_fields') else "No extension_fields")

# Check the loaded document dictionary before parsing
print("\nRaw loaded data (if available):")
print(parser.cwl_dict if hasattr(parser, 'cwl_dict') else "Not available")

# Try to access via loadingOptions
if hasattr(cwl_tool, 'loadingOptions'):
    print("\nLoading options:")
    print(cwl_tool.loadingOptions)
    if hasattr(cwl_tool.loadingOptions, 'namespaces'):
        print("\nNamespaces in loadingOptions:")
        print(cwl_tool.loadingOptions.namespaces)


```
The $namespaces attribute is typically found within the loadingOptions of the CWL document.

To add a namespace, you would typically do something like this:

```
newspacename='sc:'
newspaceurl='http://schema.org/'
if newspacename not in cwl_tool.loadingOptions.namespaces:
    cwl_tool.loadingOptions.namespaces[newspacename]=newspaceurl

cwl_tool.extension_fields['sc:customField']='customValue'
```







Testing envVar
parser = Parser("tests/05-input.cwl")
cwl_tool = parser.getCWL()

for req in cwl_tool.requirements:
    if req.class_ == 'EnvVarRequirement' and hasattr(req, 'envDef'):
        for env in req.envDef:
            if env.envValue is None or env.envValue == "":
                req.envDef.remove(env)
        if len(req.envDef) == 0:
            cwl_tool.requirements.remove(req)