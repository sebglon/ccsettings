#!/bin/bash
# Claude Code PostToolUse hook for Go files.
# Runs go vet on the package containing the edited file.
# Input: $TOOL_INPUT JSON with file_path field.

FILE=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_path',''))" 2>/dev/null)

[[ "$FILE" != *.go ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

# Find the Go module root (directory with go.mod)
DIR=$(dirname "$FILE")
while [[ "$DIR" != "/" ]]; do
    [[ -f "$DIR/go.mod" ]] && break
    DIR=$(dirname "$DIR")
done
[[ ! -f "$DIR/go.mod" ]] && exit 0

# Get the relative package path
PKG_DIR=$(dirname "$FILE")
REL=$(python3 -c "import os.path; print(os.path.relpath('$PKG_DIR', '$DIR'))")

cd "$DIR"

# If go.mod or go.sum changed, run go mod tidy
if [[ "$(basename "$FILE")" == "go.mod" || "$(basename "$FILE")" == "go.sum" ]]; then
    ~/.local/go/bin/go mod tidy 2>&1
    exit $?
fi

# Run go vet on the specific package (fast, catches real issues)
~/.local/go/bin/go vet "./$REL" 2>&1
