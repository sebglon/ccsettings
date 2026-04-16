#!/bin/bash
# Claude Code PostToolUse hook for Python files.
# Runs ruff check on the edited file.
# Input: $TOOL_INPUT JSON with file_path field.

FILE=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_path',''))" 2>/dev/null)

[[ "$FILE" != *.py ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

# Find project root (directory with pyproject.toml or setup.py)
DIR=$(dirname "$FILE")
while [[ "$DIR" != "/" ]]; do
    [[ -f "$DIR/pyproject.toml" || -f "$DIR/setup.py" ]] && break
    DIR=$(dirname "$DIR")
done
[[ ! -f "$DIR/pyproject.toml" && ! -f "$DIR/setup.py" ]] && exit 0

cd "$DIR"

# Prefer project venv ruff, fallback to global
if [[ -x "$DIR/.venv/bin/ruff" ]]; then
    RUFF="$DIR/.venv/bin/ruff"
elif command -v ruff &>/dev/null; then
    RUFF="ruff"
else
    exit 0  # no ruff available, skip silently
fi

$RUFF check "$FILE" 2>&1
