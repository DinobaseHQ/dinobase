#!/bin/sh
# Dinobase installer — https://dinobase.ai
# Usage:
#   curl -fsSL https://dinobase.ai/install.sh | bash
#   curl -fsSL https://dinobase.ai/install.sh | bash -s -- claude-desktop
#   curl -fsSL https://dinobase.ai/install.sh | bash -s -- --no-setup
set -eu

PACKAGE="dinobase"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"

# --- Colors ---

setup_colors() {
    if [ -t 1 ]; then
        BOLD='\033[1m'
        GREEN='\033[0;32m'
        RED='\033[0;31m'
        YELLOW='\033[0;33m'
        RESET='\033[0m'
    else
        BOLD=''
        GREEN=''
        RED=''
        YELLOW=''
        RESET=''
    fi
}

info() {
    printf "${BOLD}%s${RESET}\n" "$1"
}

success() {
    printf "${GREEN}%s${RESET}\n" "$1"
}

warn() {
    printf "${YELLOW}%s${RESET}\n" "$1"
}

error() {
    printf "${RED}%s${RESET}\n" "$1" >&2
}

# --- OS detection ---

detect_os() {
    OS=$(uname -s)
    case "$OS" in
        Linux|Darwin) ;;
        MINGW*|MSYS*|CYGWIN*)
            error "Windows is not supported by this installer."
            printf "\n  Install directly with pip:\n    pip install %s\n\n" "$PACKAGE"
            exit 1
            ;;
        *)
            error "Unsupported operating system: $OS"
            printf "\n  Install directly with pip:\n    pip install %s\n\n" "$PACKAGE"
            exit 1
            ;;
    esac
}

# --- uv ---

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi

    # Check common install locations not yet on PATH
    for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -x "$dir/uv" ]; then
            export PATH="$dir:$PATH"
            return 0
        fi
    done

    info "Installing uv..."
    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required but not found."
        exit 1
    fi

    curl -LsSf "$UV_INSTALL_URL" | sh 2>&1

    # Add uv to PATH for this session
    for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -x "$dir/uv" ]; then
            export PATH="$dir:$PATH"
            break
        fi
    done

    if ! command -v uv >/dev/null 2>&1; then
        error "Failed to install uv."
        printf "\n  Install uv manually: https://docs.astral.sh/uv/getting-started/installation/\n"
        printf "  Then re-run this script.\n\n"
        exit 1
    fi

    success "uv installed."
}

# --- Install ---

install_dinobase() {
    info "Installing $PACKAGE..."
    if uv tool install "$PACKAGE" --force 2>&1; then
        return 0
    else
        error "Installation failed."
        printf "\n  Try installing manually:\n    uv tool install %s\n\n" "$PACKAGE"
        exit 1
    fi
}

# --- PATH check ---

ensure_on_path() {
    if command -v "$PACKAGE" >/dev/null 2>&1; then
        return 0
    fi

    # uv tool bin directory
    UV_TOOL_BIN=$(uv tool dir 2>/dev/null | head -1)/bin 2>/dev/null || true
    for dir in "$HOME/.local/bin" "$UV_TOOL_BIN"; do
        if [ -n "$dir" ] && [ -x "$dir/$PACKAGE" ]; then
            export PATH="$dir:$PATH"
            return 0
        fi
    done

    warn "$PACKAGE was installed but is not on your PATH."
    printf "\n  Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):\n"
    printf "    export PATH=\"\$HOME/.local/bin:\$PATH\"\n"
    printf "\n  Then restart your shell or run:\n"
    printf "    source ~/.bashrc\n\n"
}

# --- Verify ---

verify() {
    if command -v "$PACKAGE" >/dev/null 2>&1; then
        VERSION=$("$PACKAGE" --version 2>/dev/null || echo "unknown")
        printf "\n"
        success "$VERSION installed successfully."
    else
        printf "\n"
        warn "Installation completed but $PACKAGE is not on PATH yet."
        printf "  Restart your shell, then run: $PACKAGE --version\n"
    fi
}

# --- Main ---

main() {
    setup_colors

    printf "\n"
    info "Dinobase Installer"
    printf "\n"

    detect_os
    ensure_uv
    install_dinobase
    ensure_on_path
    verify

    # Parse arguments: agent names and flags.
    AGENT_CLIENT=""
    RUN_SETUP=1
    for arg in "$@"; do
        case "$arg" in
            --no-setup|--skip-setup) RUN_SETUP=0 ;;
            claude-desktop|claude-code|cursor|codex) AGENT_CLIENT="$arg" ;;
        esac
    done

    if [ -n "$AGENT_CLIENT" ] && command -v "$PACKAGE" >/dev/null 2>&1; then
        printf "\n"
        info "Setting up $AGENT_CLIENT..."
        echo 5 | "$PACKAGE" init 2>/dev/null || true
        "$PACKAGE" install "$AGENT_CLIENT" || true
        printf "\n"
        info "Launching Dinobase setup..."
        printf "  Opens a browser window to connect sources and finish setup.\n"
        printf "  Press Ctrl+C to quit the setup server.\n\n"
        "$PACKAGE" setup || true
    elif [ "$RUN_SETUP" -eq 1 ] && command -v "$PACKAGE" >/dev/null 2>&1; then
        printf "\n"
        info "Launching Dinobase setup..."
        printf "  Opens a browser window to connect sources and finish setup.\n"
        printf "  Press Ctrl+C to quit the setup server.\n\n"
        "$PACKAGE" setup || true
    else
        printf "\n  Next: run ${BOLD}%s setup${RESET} to connect your data sources.\n" "$PACKAGE"
    fi

    printf "\n  Docs: https://dinobase.ai/docs\n\n"
}

main "$@"
