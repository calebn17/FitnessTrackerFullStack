#!/usr/bin/env bash
# Cursor preToolUse hook: stdin has .tool_input (object) with path fields.
set -euo pipefail
input=$(cat)
file=$(echo "$input" | jq -r '
  (.tool_input // {})
  | if type == "object" then (.file_path // .path // .target_file // "") else "" end
')

protected=(
  ".env*"
  ".git/*"
  "package-lock.json"
  "yarn.lock"
  "*.pem"
  "*.key"
  "secrets/*"
)

# Glob (only * wildcards) to ERE; then match as path segment or full path.
# Use a literal placeholder — do not use $$ here (bash expands it to PID).
glob_to_ere() {
  local g="$1"
  local dotstar='.*'
  g="${g//\*/__GLOBSTAR__}"
  g=$(printf '%s' "$g" | sed 's/\./\\./g')
  g="${g//__GLOBSTAR__/${dotstar}}"
  printf '%s' "$g"
}

if [[ -z "$file" ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

for pattern in "${protected[@]}"; do
  ere=$(glob_to_ere "$pattern")
  if echo "$file" | grep -qiE "(^|/)${ere}(/|$)"; then
    msg="Blocked: '${file}' is protected. Explain why this edit is necessary."
    jq -n --arg msg "$msg" '{permission: "deny", user_message: $msg, agent_message: $msg}'
    exit 0
  fi
done

echo '{"permission":"allow"}'
exit 0
