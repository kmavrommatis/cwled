#What is the structure of dependent records:

```
from cwl_utils_handler import CWLType,get_cwl_module
from cwl_utils.parser import save
from CWLparser import Parser

cwl_dict=Parser( "tests/09-arguments.cwl").getCWL()

cwl_dict.arguments
['-d', '$(runtime.outdir)']
 
i=cwl_dict.inputs[0]

i.type_
<cwl_utils.parser.cwl_v1_0.CommandInputRecordSchema object at 0x10575c2b0>

i.inputBinding
NULL

i.type_.type_)
'record'

i.type_.fields
[<cwl_utils.parser.cwl_v1_0.CommandInputRecordField object at 0x10575c430>, 
 <cwl_utils.parser.cwl_v1_0.CommandInputRecordField object at 0x10575c550>]
```


get_type(i) 
['record', 'string']


=====


#What is the structure of exclusive records:

```
from cwl_utils_handler import CWLType,get_cwl_module
from cwl_utils.parser import save
from CWLparser import Parser

cwl_dict=Parser( "tests/enum_inputs.cwl").getCWL()

cwl_dict.inputs
[<cwl_utils.parser.cwl_v1_0.CommandInputParameter object at 0x10575c250>, 
 <cwl_utils.parser.cwl_v1_0.CommandInputParameter object at 0x10575c610>]
 
e=cwl_dict.inputs[1]

e.type_
[<cwl_utils.parser.cwl_v1_0.CommandInputRecordSchema object at 0x10575c190>, 
 <cwl_utils.parser.cwl_v1_0.CommandInputRecordSchema object at 0x10575c6d0>]

e.inputBinding
NULL

e.type_[0].type_
'record'

e.type_[0].fields
[<cwl_utils.parser.cwl_v1_0.CommandInputRecordField object at 0x10575c220>]
```

get_type(e)
['record', 'string']