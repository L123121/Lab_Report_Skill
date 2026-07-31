#!/usr/bin/env bash
# Install screenshot dependencies for the Computer Lab Report Skill.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$SCRIPT_DIR"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

.venv/bin/pip install -r requirements.txt

echo ""
echo "Screenshot and terminal-capture dependencies installed."
echo ""
echo "Recommended usage:"
echo "  $SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/scripts/code_shot.py --help"
echo "  $SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/scripts/term_shot.py --help"
echo "  $SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/scripts/docx_format_guard.py --help"
echo ""
echo "DOCX editing is provided by the host Agent environment; format verification is bundled."
