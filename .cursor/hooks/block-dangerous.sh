#!/usr/bin/env bash
# Cursor beforeShellExecution hook: stdin is JSON with .command, .cwd, .sandbox
set -euo pipefail
input=$(cat)
cmd=$(echo "$input" | jq -r '.command // ""')

dangerous_patterns=(
  "rm -rf"
  "git reset --hard"
  "git push.*--force"
  "DROP TABLE"
  "DROP DATABASE"
  # Pipe download to shell (not arbitrary paths ending in .sh)
  "\\bcurl\\b[^|]*\\|[^|]*\\bsh\\b"
  "\\bwget\\b[^|]*\\|[^|]*\\bbash\\b"
)

for pattern in "${dangerous_patterns[@]}"; do
  if echo "$cmd" | grep -qiE "$pattern"; then
    msg="Blocked: command matches dangerous pattern '${pattern}'. Propose a safer alternative."
    jq -n \
      --arg msg "$msg" \
      '{permission: "deny", user_message: $msg, agent_message: $msg}'
    exit 0
  fi
done

echo '{"permission":"allow"}'
exit 0
