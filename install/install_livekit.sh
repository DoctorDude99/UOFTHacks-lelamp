#!/bin/bash
#
# install_livekit.sh - Install LiveKit CLI
#
# LiveKit CLI is used for generating credentials and managing rooms.
#
# Usage:
#   ./install_livekit.sh              # Interactive
#   ./install_livekit.sh -y           # Install without prompting
#   ./install_livekit.sh --check      # Check if installed
#   ./install_livekit.sh --force      # Force reinstall
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
FORCE_INSTALL=false

show_help() {
    echo "LeLamp LiveKit CLI Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check              Check if LiveKit CLI is installed"
    echo "  --force              Force reinstall even if already installed"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check)
                ACTION="check"
                shift
                ;;
            --force)
                FORCE_INSTALL=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            -y|--yes|--skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
}

# Check if LiveKit CLI is installed
check_livekit() {
    if command_exists lk; then
        local version
        version=$(lk --version 2>/dev/null | head -1)
        print_success "LiveKit CLI is installed: $version"
        return 0
    else
        print_info "LiveKit CLI is not installed"
        return 1
    fi
}

# Install LiveKit CLI
install_livekit() {
    print_header "Installing LiveKit CLI"

    # Check if already installed
    if check_livekit && [ "$FORCE_INSTALL" != "true" ]; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "LiveKit CLI is already installed. Reinstall?"; then
                print_info "Keeping existing LiveKit CLI installation"
                return 0
            fi
        else
            print_info "Keeping existing LiveKit CLI installation"
            return 0
        fi
    fi

    print_info "Downloading and installing LiveKit CLI..."

    # Try the official URL, fall back to direct GitHub URL if it fails
    if ! curl -sSL https://get.livekit.io/cli -o /tmp/lk-install.sh 2>/dev/null; then
        print_warning "Primary URL failed, trying direct GitHub URL..."
        if ! curl -sSL https://raw.githubusercontent.com/livekit/livekit-cli/main/install-cli.sh -o /tmp/lk-install.sh; then
            print_error "Failed to download LiveKit CLI installer"
            return 1
        fi
    fi

    # Run the installer
    bash /tmp/lk-install.sh
    rm -f /tmp/lk-install.sh

    print_success "LiveKit CLI installed successfully"
    lk --version
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            install_livekit
            ;;
        check)
            check_livekit
            ;;
    esac
}

# Run main function
main "$@"
