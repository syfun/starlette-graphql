curl localhost:8080/graphql/ \
  -F operations='{ "query": "mutation ($files: [Upload!]!) { multiUpload(files: $files) { filename } }", "variables": { "files": [null, null] } }' \
  -F map='{ "0": ["variables.files.0"], "1": ["variables.files.1"] }' \
  -F 0=@single.sh \
  -F 1=@multi.sh | jq