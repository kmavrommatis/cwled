{
   "class": "CommandLineTool",
   "id": "12-tar-param.cwl",
   "doc": "",
   "inputs": [
      {
         "id": "extractfile",
         "type": "string",
         "inputBinding": {
            "position": 1
         }
      },
      {
         "id": "tarfile",
         "type": "File",
         "inputBinding": {
            "prefix": "--file"
         }
      }
   ],
   "outputs": [
      {
         "id": "extracted_file",
         "type": "File",
         "outputBinding": {
            "glob": "$(inputs.extractfile)"
         }
      }
   ],
   "requirements": [],
   "cwlVersion": "v1.2",
   "baseCommand": [
      "tar",
      "--extract"
   ],
   "arguments": [
      {
         "position": 4,
         "prefix": "--arg",
         "separate": false,
         "valueFrom": "test_arg",
         "shellQuote": false
      }
   ]
}