#!/bin/bash
#
# install_uv.sh - Install UV package manager
#
# UV is a fast Python package manager used for LeLamp dependency management.
#
# Usage:
#   ./install_uv.sh              # Interactive
#   ./install_uv.sh -y           # Install without prompting
#   ./install_uv.sh --check      # Check if UV is installed
#   ./install_uv.sh --force      # Force reinstall
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
FORCE_INSTALL=false

show_help() {
    echo "LeLamp UV Package Manager Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check              Check if UV is installed"
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

# Check if UV is installed
check_uv() {
    if command_exists uv; then
        local version
        version=$(uv --version 2>/dev/null | head -1)
        print_success "UV is installed: $version"
        return 0
    else
        print_info "UV is not installed"
        return 1
    fi
}

# Install UV
install_uv() {
    print_header "Installing UV Package Manager"

    # Check if already installed
    if check_uv && [ "$FORCE_INSTALL" != "true" ]; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "UV is already installed. Reinstall?"; then
                print_info "Keeping existing UV installation"
                return 0
            fi
        else
            print_info "Keeping existing UV installation"
            return 0
        fi
    fi

    print_info "Downloading and installing UV..."

    # Try the official URL, fall back to direct GitHub URL if it fails
    if ! curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh 2>/dev/null; then
        print_warning "Primary URL failed, trying direct GitHub URL..."
        if ! curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-installer.sh -o /tmp/uv-install.sh; then
            print_error "Failed to download UV installer"
            return 1
        fi
    fi

    # Install UV to /usr/local/bin for system-wide access
    print_info "Installing UV to /usr/local/bin..."
    sudo UV_INSTALL_DIR=/usr/local/bin sh /tmp/uv-install.sh
    rm -f /tmp/uv-install.sh

    if [ ! -f "/usr/local/bin/uv" ]; then
        print_error "UV installation failed"
        return 1
    fi

    print_success "UV installed successfully"
    uv --version
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            if [ "$SKIP_CONFIRM" != "true" ]; then
                if check_uv && [ "$FORCE_INSTALL" != "true" ]; then
                    return 0
                fi
            fi
            install_uv
            ;;
        check)
            check_uv
            ;;
    esac
}

# Run main function
main "$@"
