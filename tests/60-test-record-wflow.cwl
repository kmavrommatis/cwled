class: Workflow
id: Workflow_088f
label: ""
doc: ""
inputs:
- id: input_string
  default: input_string_wflow_default
  type: string
- id: dependent_parameters
  default:
    itemA: wflow_input_defA
    itemB: wflow_input_defB
  type:
  - 'null'
  - name: dependent_parameters_name
    fields:
    - name: itemA
      type: string
    - name: itemB
      type: "string"
    type: "record"
- id: input_integer
  default: 30
  type:
  - 'null'
  - float
- id: exclusive_parameters
  default:
    class: itemC_type
    itemC_type: wflow_input_defaultC
  type:
  - 'null'
  - name: itemC_type
    fields:
    - name: itemC
      type: "string"
    type: "record"
  - name: itemD_type
    fields:
    - name: itemD
      type: "string"
    type: "record"
outputs:
- id: example_out
  outputSource: records/example_out
  type: File
- id: example_out_9738
  outputSource: records_2/example_out
  type: File
requirements: []
hints: []
cwlVersion: v1.2
steps:
- id: records
  label: "Test records"
  doc: ""
  in:
  - id: input_string
    source: input_string
    default: input_string_wf_default
  - id: input_integer
    source: input_integer
    default: 20
  - id: dependent_parameters
    source: dependent_parameters
    default:
      itemA: wflow_step_defaultA
      itemB: wflow_step_defaultB
  - id: exclusive_parameters
    source: exclusive_parameters
    label: ""
    default:
      class: itemC
      itemC: wflow_defaultC
  out:
  - id: example_out
  run: 07-record.cwl
- id: records_2
  label: Test records (Copy)
  in:
  - id: input_string
    source: input_string
  - id: input_integer
    source: dependent_parameters
  - id: dependent_parameters
    source: input_integer
  - id: exclusive_parameters
    source: exclusive_parameters
  out:
  - id: example_out
  run: 07-record.cwl
