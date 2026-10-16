class: CommandLineTool
id: 02-echo-network.cwl
inputs:
- id: message
  type: string
  inputBinding: {}
outputs:
- id: out
  type: string
  outputBinding:
    loadContents: true
    glob: output.txt
    outputEval: $(self[0].contents)
requirements:
- class: NetworkAccess
  networkAccess: true
cwlVersion: v1.2
baseCommand:
- echo
stdout: output.txt
