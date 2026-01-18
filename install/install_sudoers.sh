#!/bin/bash
#
# install_sudoers.sh - Install LeLamp sudoers configuration
#
# Configures passwordless sudo access for LeLamp service operations:
#   - System shutdown command
#   - Service management (start/stop/restart/status)
#   - Port 80 binding capabilities
#   - GPIO access capabilities
#
# Usage:
#   ./install_sudoers.sh                    # Interactive
#   ./install_sudoers.sh -y                 # Install without prompting
#   ./install_sudoers.sh --uninstall        # Remove sudoers config
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
SUDOERS_SOURCE="$LELAMP_DIR/system/lelamp-sudoers"
SUDOERS_DEST="/etc/sudoers.d/lelamp"

show_help() {
    echo "LeLamp Sudoers Configuration Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --uninstall          Remove sudoers configuration"
    show_help_footer
    echo "What this configures:"
    echo "  - Passwordless sudo for 'shutdown' command"
    echo "  - Passwordless sudo for systemctl service management"
    echo "  - Passwordless sudo for setcap (port 80 and GPIO access)"
    echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --uninstall)
            ACTION="uninstall"
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

# Install sudoers configuration
install_sudoers() {
    print_header "Installing LeLamp Sudoers Configuration"

    # Get LeLamp directory
    LELAMP_DIR=$(get_lelamp_dir)
    SUDOERS_SOURCE="$LELAMP_DIR/system/lelamp-sudoers"

    # Check if source file exists
    if [ ! -f "$SUDOERS_SOURCE" ]; then
        print_error "Sudoers template not found at $SUDOERS_SOURCE"
        return 1
    fi

    # Get current user
    local current_user="$USER"
    print_info "Configuring sudoers for user: $current_user"
    print_warning "Note: The sudoers rules will apply to user '$current_user'"
    print_info "If you need to use a different user (e.g., 'lelamp'), edit the file manually after installation"

    # Create temporary file with user substitution
    local temp_sudoers=$(mktemp)
    sed "s/^lelamp /$current_user /" "$SUDOERS_SOURCE" > "$temp_sudoers"

    # Validate syntax
    print_info "Validating sudoers syntax..."
    if ! sudo visudo -c -f "$temp_sudoers"; then
        print_error "Sudoers file has invalid syntax"
        rm -f "$temp_sudoers"
        return 1
    fi

    # Install the file
    print_info "Installing to $SUDOERS_DEST..."
    if sudo cp "$temp_sudoers" "$SUDOERS_DEST"; then
        sudo chmod 440 "$SUDOERS_DEST"
        rm -f "$temp_sudoers"
        print_success "Sudoers configuration installed"
    else
        print_error "Failed to install sudoers configuration"
        rm -f "$temp_sudoers"
        return 1
    fi

    # Install wrapper scripts
    print_info "Installing helper scripts..."
    local script_source="$LELAMP_DIR/system/scripts/update-raspotify-name.sh"
    if [ -f "$script_source" ]; then
        if sudo cp "$script_source" /usr/local/bin/update-raspotify-name.sh; then
            sudo chmod 755 /usr/local/bin/update-raspotify-name.sh
            print_success "Helper scripts installed"
        else
            print_warning "Failed to install helper scripts"
        fi
    else
        print_warning "Helper script not found at $script_source"
    fi

    print_info ""
    print_info "The following commands can now run without password:"
    print_info "  - sudo shutdown now"
    print_info "  - sudo systemctl {start,stop,restart,status,enable,disable} lelamp.service"
    print_info "  - sudo systemctl {start,stop,restart,status,enable,disable} raspotify"
    print_info "  - sudo update-raspotify-name.sh (for changing Spotify device name)"
}

# Uninstall sudoers configuration
uninstall_sudoers() {
    print_header "Uninstalling LeLamp Sudoers Configuration"

    if [ ! -f "$SUDOERS_DEST" ]; then
        print_info "Sudoers configuration not installed"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Remove sudoers configuration?"; then
            print_info "Cancelled"
            return 0
        fi
    fi

    print_info "Removing $SUDOERS_DEST..."
    if sudo rm -f "$SUDOERS_DEST"; then
        print_success "Sudoers configuration removed"
    else
        print_error "Failed to remove sudoers configuration"
        return 1
    fi
}

# Main execution
case $ACTION in
    install)
        install_sudoers
        ;;
    uninstall)
        uninstall_sudoers
        ;;
    *)
        print_error "Unknown action: $ACTION"
        show_help
        exit 1
        ;;
esac
