#!/bin/bash
#
# install_raspotify.sh - Install Raspotify (Spotify Connect)
#
# Makes your Raspberry Pi a Spotify Connect device.
# Requires Spotify Premium account.
#
# Usage:
#   ./install_raspotify.sh                      # Interactive
#   ./install_raspotify.sh -y                   # Install without prompting
#   ./install_raspotify.sh --check              # Check if installed
#   ./install_raspotify.sh --name "My Device"   # Set device name
#   ./install_raspotify.sh --uninstall          # Remove Raspotify
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
DEVICE_NAME=""
FORCE_INSTALL=false

show_help() {
    echo "LeLamp Raspotify (Spotify Connect) Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check              Check if Raspotify is installed"
    echo "  --name <NAME>        Set Spotify Connect device name"
    echo "  --force              Force reinstall even if already installed"
    echo "  --uninstall          Remove Raspotify"
    show_help_footer
    echo "Notes:"
    echo "  - Requires Spotify Premium account"
    echo "  - Uses dmix for audio sharing with LeLamp"
    echo ""
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check)
                ACTION="check"
                shift
                ;;
            --name)
                DEVICE_NAME="$2"
                shift 2
                ;;
            --force)
                FORCE_INSTALL=true
                shift
                ;;
            --uninstall|--remove)
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
}

# Check if Raspotify is installed
check_raspotify() {
    if command_exists raspotify || systemctl is-active --quiet raspotify 2>/dev/null; then
        print_success "Raspotify is installed"
        systemctl status raspotify --no-pager 2>/dev/null || true
        return 0
    else
        print_info "Raspotify is not installed"
        return 1
    fi
}

# Install Raspotify
install_raspotify() {
    print_header "Installing Raspotify (Spotify Connect)"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will install Raspotify to enable Spotify playback."
        echo "Your Raspberry Pi will become a Spotify Connect device."
        echo ""
        echo "Note: Requires Spotify Premium account."
        echo ""
        if ! ask_yes_no "Install Raspotify?" "y"; then
            print_info "Skipping Raspotify installation"
            print_info "You can install it later from: https://github.com/dtcooper/raspotify"
            return 0
        fi
    fi

    # Check if already installed
    if check_raspotify && [ "$FORCE_INSTALL" != "true" ]; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "Raspotify is already installed. Reinstall?"; then
                print_info "Keeping existing Raspotify installation"
                return 0
            fi
        else
            print_info "Keeping existing Raspotify installation"
            return 0
        fi
    fi

    print_info "Adding Raspotify repository..."

    # Install dependencies
    sudo apt-get install -y curl apt-transport-https

    # Add the raspotify GPG key and repository
    curl -sSL https://dtcooper.github.io/raspotify/key.asc | sudo tee /usr/share/keyrings/raspotify-archive-keyrings.asc > /dev/null
    echo "deb [signed-by=/usr/share/keyrings/raspotify-archive-keyrings.asc] https://dtcooper.github.io/raspotify raspotify main" | sudo tee /etc/apt/sources.list.d/raspotify.list

    # Install raspotify
    sudo apt-get update
    sudo apt-get install -y raspotify

    # Configure raspotify
    print_info "Configuring Raspotify..."

    # Get LELAMP_DIR
    LELAMP_DIR=$(get_lelamp_dir)

    # Copy LeLamp raspotify config (uses dmix for audio sharing with LiveKit)
    RASPOTIFY_CONFIG="$LELAMP_DIR/system/raspotify/conf"
    if [ -f "$RASPOTIFY_CONFIG" ]; then
        print_info "Installing LeLamp raspotify config (with dmix support)..."
        sudo mkdir -p /etc/raspotify
        sudo cp "$RASPOTIFY_CONFIG" /etc/raspotify/conf
        print_success "Raspotify config installed from $RASPOTIFY_CONFIG"
    else
        # Set device name
        if [ -z "$DEVICE_NAME" ]; then
            if [ "$SKIP_CONFIRM" != "true" ]; then
                read -p "Enter Spotify Connect device name [lelamp]: " DEVICE_NAME < "$INPUT_DEVICE"
            fi
            DEVICE_NAME=${DEVICE_NAME:-lelamp}
        fi

        if [ -f /etc/raspotify/conf ]; then
            sudo sed -i "s/^#*LIBRESPOT_NAME=.*/LIBRESPOT_NAME=\"$DEVICE_NAME\"/" /etc/raspotify/conf
            print_success "Device name set to: $DEVICE_NAME"
        fi
    fi

    # Enable and start service
    sudo systemctl enable raspotify
    sudo systemctl restart raspotify

    print_success "Raspotify installed and started"
    print_info "Your Pi is now a Spotify Connect device"
    print_info "Open Spotify on your phone/computer and select it as the output device"
}

# Uninstall Raspotify
uninstall_raspotify() {
    print_header "Uninstalling Raspotify"

    if ! check_raspotify; then
        print_info "Raspotify is not installed"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Are you sure you want to uninstall Raspotify?"; then
            print_info "Cancelled"
            return 0
        fi
    fi

    print_info "Stopping Raspotify service..."
    sudo systemctl stop raspotify 2>/dev/null || true
    sudo systemctl disable raspotify 2>/dev/null || true

    print_info "Removing Raspotify package..."
    sudo apt-get remove -y raspotify

    print_success "Raspotify uninstalled"
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            install_raspotify
            ;;
        check)
            check_raspotify
            ;;
        uninstall)
            uninstall_raspotify
            ;;
    esac
}

# Run main function
main "$@"
