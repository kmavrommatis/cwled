# uppercase.cwl
cwlVersion: v1.2
class: ExpressionTool
requirements:
  InlineJavascriptRequirement: {} # This is needed since the expression uses JavaScript.
inputs:
  message: string
outputs:
  uppercase_message: string
expression: |
  ${
    return {"uppercase_message": inputs.message.toUpperCase()};
  }