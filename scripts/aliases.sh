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
