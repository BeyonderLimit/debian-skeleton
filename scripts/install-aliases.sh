#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# Bash Alias Installer
# ============================================================

SOURCE_FILE="${1:-$HOME/.bash_aliases_custom}"
BASHRC="$HOME/.bashrc"
MARKER="# >>> custom bash aliases >>>"

echo "Installing custom Bash aliases..."

# ------------------------------------------------------------
# Check source file
# ------------------------------------------------------------

if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR: Alias file not found:"
    echo "  $SOURCE_FILE"
    echo
    echo "Create the alias file first, then run this script again."
    exit 1
fi

# ------------------------------------------------------------
# Backup .bashrc
# ------------------------------------------------------------

if [ -f "$BASHRC" ]; then
    BACKUP="${BASHRC}.backup.$(date +%Y%m%d-%H%M%S)"

    cp "$BASHRC" "$BACKUP"

    echo "Backed up .bashrc to:"
    echo "  $BACKUP"
else
    touch "$BASHRC"
    echo "Created $BASHRC"
fi

# ------------------------------------------------------------
# Install alias file
# ------------------------------------------------------------

if [ "$SOURCE_FILE" != "$HOME/.bash_aliases_custom" ]; then
    cp "$SOURCE_FILE" "$HOME/.bash_aliases_custom"
    SOURCE_FILE="$HOME/.bash_aliases_custom"

    echo "Copied aliases to:"
    echo "  $SOURCE_FILE"
fi

# ------------------------------------------------------------
# Remove old installer block if present
# ------------------------------------------------------------

if grep -qF "$MARKER" "$BASHRC"; then
    echo "Existing alias loader found; leaving it in place."
else
    cat >> "$BASHRC" <<'EOF'

# >>> custom bash aliases >>>
if [ -f "$HOME/.bash_aliases_custom" ]; then
    source "$HOME/.bash_aliases_custom"
fi
# <<< custom bash aliases <<<
EOF

    echo "Added alias loader to $BASHRC"
fi

# ------------------------------------------------------------
# Load aliases into current shell
# ------------------------------------------------------------

# shellcheck disable=SC1090
source "$SOURCE_FILE"

echo
echo "Done."
echo
echo "Aliases are installed in:"
echo "  $SOURCE_FILE"
echo
echo "They will automatically load in new Bash sessions."
echo
echo "To load them right now:"
echo "  source ~/.bash_aliases_custom"
