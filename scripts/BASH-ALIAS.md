 ## 1\. Clean `aliases.sh`

 Save this as `~/.bash_aliases_custom` or, if you prefer, `~/aliases.sh`.

 Clean Bash aliases file

```
#!/usr/bin/env bash

# ============================================================
# Bash Aliases & Functions
# ============================================================
# Load with:
#   source ~/.bash_aliases_custom
#
# Or automatically load it from ~/.bashrc.
# ============================================================

# ============================================================
# General
# ============================================================

# Clear terminal
alias c='clear'

# Command history
alias h='history'

# Show aliases
alias al='alias'

# Safer file operations
alias rm='rm -i'
alias cp='cp -i'

# Colorized grep
alias grep='grep --color=auto'

# Continue downloads
alias wg='wget -c'

# ============================================================
# Internet / System Information
# ============================================================

# Show public IP address
alias myip='curl -s https://ipinfo.io/ip; echo'

# Show weather based on current public IP location
alias weather='curl -s wttr.in'

# Show mounted filesystems in a readable format
alias mnt="mount | awk '{ printf \"%s\\t%s\\n\", \$1, \$3 }' | column -t | grep '^/dev/' | sort"

# Disk usage
alias df='df -Tha --total'

# Show directory sizes
alias lu='du -sh ./* 2>/dev/null | sort -h'

# ============================================================
# Debian / Ubuntu Package Management
# ============================================================

# Update package lists and upgrade installed packages
alias update='sudo apt update && sudo apt upgrade -y'

# Install a package
yep() {
    if [ -z "$1" ]; then
        echo "Usage: yep <package>"
        return 1
    fi

    sudo apt install "$@"
}

# Remove a package
nop() {
    if [ -z "$1" ]; then
        echo "Usage: nop <package>"
        return 1
    fi

    sudo apt remove "$@"
}

# ============================================================
# Navigation
# ============================================================

# Go up one directory
alias ..='cd ..'

# Go up two directories
alias ....='cd ../..'

# Open current directory in Nautilus
alias exp='nautilus .'

# List directories only
alias ld='ls -d */ 2>/dev/null'

# ============================================================
# Files / Directories
# ============================================================

# Detailed directory listing
alias ll='ls -la'

# Detailed listing with file type indicators
alias lf='ls -alF'

# Show hidden files
alias la='ls -A'

# Default ls format
alias ls='ls -CF'

# Largest files/directories first
alias lt='ls -lahS'

# Most recently modified first
alias ltr='ls -latr'

# Count files recursively
alias lc='find . -type f | wc -l'

# Find a file by name
fh() {
    if [ -z "$1" ]; then
        echo "Usage: fh <filename>"
        return 1
    fi

    find . -name "$1"
}

# Show file modification times
alias std="stat -c '%y - %n' -- * 2>/dev/null | sort -r"

# ============================================================
# Archive / Extraction
# ============================================================

# Extract many common archive formats
extract() {
    if [ -z "$1" ]; then
        echo "Usage: extract <archive>"
        return 1
    fi

    if [ ! -f "$1" ]; then
        echo "'$1' is not a valid file"
        return 1
    fi

    case "$1" in
        *.tar.bz2) tar xvjf "$1" ;;
        *.tar.gz)  tar xvzf "$1" ;;
        *.tar.xz)  tar xvJf "$1" ;;
        *.bz2)     bunzip2 "$1" ;;
        *.rar)     unrar x "$1" ;;
        *.gz)      gunzip "$1" ;;
        *.tar)     tar xvf "$1" ;;
        *.tbz2)    tar xvjf "$1" ;;
        *.tgz)     tar xvzf "$1" ;;
        *.zip)     unzip "$1" ;;
        *.Z)       uncompress "$1" ;;
        *.xz)      unxz "$1" ;;
        *.7z)      7z x "$1" ;;
        *)
            echo "'$1' cannot be extracted via extract()"
            return 1
            ;;
    esac
}

# ============================================================
# Directory Helpers
# ============================================================

# Make directory and enter it
mkcd() {
    if [ -z "$1" ]; then
        echo "Usage: mkcd <directory>"
        return 1
    fi

    mkdir -p -- "$1" && cd -P -- "$1"
}

# ============================================================
# History Helpers
# ============================================================

# Search command history
hg() {
    if [ -z "$1" ]; then
        history
        return 0
    fi

    history | grep -- "$1"
}

# ============================================================
# Git
# ============================================================

# Git status
alias gs='git status'

# Git branches
alias gb='git branch'

# Create a new branch and switch to it
alias gbn='git checkout -b'

# Git remotes
alias gr='git remote -v'

# Add a file
alias ga='git add'

# Add everything
alias gaa='git add --all'

# Commit
alias gc='git commit'

# Git diff
alias gd='git diff'

# Short log
alias gl='git log --oneline'

# Graphical log
alias gld='git log --oneline --decorate --graph --all'

# Files changed most frequently in the last 12 months
alias glc="git log --format=format: --name-only --since='12 months ago' | grep -v '^$' | sort | uniq -c | sort -nr | head -50"

# Search Git reflog for PHP-related commits
alias glp="git log -g --grep='PHP' -10 --pretty='%h - %s - %cn - %cd'"

# List Git refs sorted by latest commit
alias glf='git for-each-ref --sort=-committerdate'

# Push to master
alias gpom='git push origin master'

# Push to develop
alias gpod='git push origin develop'

# ============================================================
# Miscellaneous
# ============================================================

# Show a nicer directory tree.
# Requires: tree
alias tree='tree --dirsfirst -F'

# ============================================================
# Command Completion / Notification
# ============================================================

# Notify when a long-running command finishes.
#
# Usage:
#   sleep 5; alert
#
# The notification indicates whether the previous command
# succeeded or failed.
alias alert='notify-send --urgency=low -i "$([ $? = 0 ] && echo terminal || echo error)" "$(history | tail -n 1 | sed -e '\''s/^[[:space:]]*[0-9]\+[[:space:]]*//;s/[;&|][[:space:]]*alert$//'\'')"'
```

 ### 2\. Installer / injector script

 This script creates a backup of your `.bashrc`, installs the alias file into `~/.bash_aliases_custom`, and adds a guarded `source` line to `.bashrc`.

 Bash alias installer

```
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
```

 ## 3\. How to install it

 If you save the first block as `aliases.sh` and the second as `install-aliases.sh`:

```
chmod +x install-aliases.sh
./install-aliases.sh aliases.sh
```

 Or, if you put the alias file directly at `~/.bash_aliases_custom`:

```
chmod +x install-aliases.sh
./install-aliases.sh
```

 Then either open a new terminal or run:

```
source ~/.bashrc
```

 You can verify everything with:

```
alias
```
