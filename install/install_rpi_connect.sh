#!/bin/bash
# =============================================================================
# LeLamp - Raspberry Pi Connect Installation Script
# =============================================================================
# Installs and configures rpi-connect for remote access to the device.
#
# Usage:
#   ./install_rpi_connect.sh install [--auth-key KEY]
#   ./install_rpi_connect.sh status
#   ./install_rpi_connect.sh enable
#   ./install_rpi_connect.sh disable
#   ./install_rpi_connect.sh remove
#
# Environment Variables:
#   RPI_CONNECT_KEY - Authentication key for automatic sign-in
#
# =============================================================================

set -e

# Source common functions if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/common.sh" ]]; then
    source "$SCRIPT_DIR/common.sh"
    # Alias log_* to print_* for compatibility
    log_info() { print_info "$1"; }
    log_success() { print_success "$1"; }
    log_warning() { print_warning "$1"; }
    log_error() { print_error "$1"; }
else
    # Fallback definitions
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'

    log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
    log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
    log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
    log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
fi

# =============================================================================
# Configuration
# =============================================================================

RPI_CONNECT_SERVICE="rpi-connect"
RPI_CONNECT_USER_SERVICE="rpi-connect-wayvnc.service"

# =============================================================================
# Helper Functions
# =============================================================================

check_raspberry_pi() {
    if [[ ! -f /proc/device-tree/model ]]; then
        log_error "This script is intended for Raspberry Pi devices only"
        return 1
    fi

    local model
    model=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')

    if [[ ! "$model" =~ "Raspberry Pi" ]]; then
        log_error "Not a Raspberry Pi device: $model"
        return 1
    fi

    log_info "Detected: $model"
    return 0
}

is_installed() {
    dpkg -l rpi-connect 2>/dev/null | grep -q "^ii" && return 0
    dpkg -l rpi-connect-lite 2>/dev/null | grep -q "^ii" && return 0
    return 1
}

is_service_running() {
    systemctl --user is-active --quiet "$RPI_CONNECT_SERVICE" 2>/dev/null && return 0
    systemctl is-active --quiet "$RPI_CONNECT_SERVICE" 2>/dev/null && return 0
    return 1
}

is_service_enabled() {
    systemctl --user is-enabled --quiet "$RPI_CONNECT_SERVICE" 2>/dev/null && return 0
    systemctl is-enabled --quiet "$RPI_CONNECT_SERVICE" 2>/dev/null && return 0
    return 1
}

# =============================================================================
# Installation
# =============================================================================

install_rpi_connect() {
    local auth_key="${1:-$RPI_CONNECT_KEY}"
    local lite_mode="${2:-false}"

    log_info "Installing Raspberry Pi Connect..."

    # Check if this is a Raspberry Pi
    check_raspberry_pi || return 1

    # Check if already installed
    if is_installed; then
        log_warning "rpi-connect is already installed"
    else
        # Update package list
        log_info "Updating package list..."
        sudo apt-get update -qq

        # Install rpi-connect or rpi-connect-lite
        if [[ "$lite_mode" == "true" ]]; then
            log_info "Installing rpi-connect-lite (no VNC/screen sharing)..."
            sudo apt-get install -y rpi-connect-lite
        else
            log_info "Installing rpi-connect (full version with VNC)..."
            sudo apt-get install -y rpi-connect
        fi

        log_success "rpi-connect installed"
    fi

    # Enable lingering for the current user (allows user services to run without login)
    log_info "Enabling user lingering for $(whoami)..."
    sudo loginctl enable-linger "$(whoami)"

    # Start and enable the service
    log_info "Enabling rpi-connect service..."
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable "$RPI_CONNECT_SERVICE" 2>/dev/null || \
        sudo systemctl enable "$RPI_CONNECT_SERVICE" 2>/dev/null || true

    systemctl --user start "$RPI_CONNECT_SERVICE" 2>/dev/null || \
        sudo systemctl start "$RPI_CONNECT_SERVICE" 2>/dev/null || true

    # Authenticate if key provided
    if [[ -n "$auth_key" ]]; then
        log_info "Authenticating with provided key..."

        # Wait for service to be ready
        sleep 2

        # Sign in with the auth key
        if rpi-connect signin --key "$auth_key" 2>/dev/null; then
            log_success "Authenticated successfully"
        else
            log_warning "Authentication failed or key invalid"
            log_info "You can manually authenticate later with: rpi-connect signin"
        fi
    else
        log_warning "No authentication key provided"
        log_info "Run 'rpi-connect signin' to authenticate manually"
        log_info "Or use: rpi-connect signin --key YOUR_KEY"
    fi

    # Show status
    show_status

    log_success "rpi-connect installation complete"

    if [[ -z "$auth_key" ]]; then
        echo ""
        echo "To complete setup:"
        echo "  1. Run: rpi-connect signin"
        echo "  2. Visit the URL shown and sign in with your Raspberry Pi ID"
        echo "  3. Access your device at: https://connect.raspberrypi.com"
    fi
}

# =============================================================================
# Status
# =============================================================================

show_status() {
    echo ""
    echo "=== Raspberry Pi Connect Status ==="
    echo ""

    # Check installation
    if is_installed; then
        local version
        version=$(dpkg -l rpi-connect 2>/dev/null | grep "^ii" | awk '{print $3}' || \
                  dpkg -l rpi-connect-lite 2>/dev/null | grep "^ii" | awk '{print $3}')
        echo "Installed: Yes (version: ${version:-unknown})"
    else
        echo "Installed: No"
        return 0
    fi

    # Check service status
    if is_service_running; then
        echo "Service: Running"
    else
        echo "Service: Stopped"
    fi

    if is_service_enabled; then
        echo "Auto-start: Enabled"
    else
        echo "Auto-start: Disabled"
    fi

    # Check sign-in status
    echo ""
    if command -v rpi-connect &>/dev/null; then
        log_info "Connection status:"
        rpi-connect status 2>/dev/null || echo "  Unable to get status"
    fi

    echo ""
}

# =============================================================================
# Service Control
# =============================================================================

enable_service() {
    log_info "Enabling rpi-connect service..."

    systemctl --user enable "$RPI_CONNECT_SERVICE" 2>/dev/null || \
        sudo systemctl enable "$RPI_CONNECT_SERVICE" 2>/dev/null

    systemctl --user start "$RPI_CONNECT_SERVICE" 2>/dev/null || \
        sudo systemctl start "$RPI_CONNECT_SERVICE" 2>/dev/null

    log_success "rpi-connect enabled and started"
}

disable_service() {
    log_info "Disabling rpi-connect service..."

    systemctl --user stop "$RPI_CONNECT_SERVICE" 2>/dev/null || \
        sudo systemctl stop "$RPI_CONNECT_SERVICE" 2>/dev/null || true

    systemctl --user disable "$RPI_CONNECT_SERVICE" 2>/dev/null || \
        sudo systemctl disable "$RPI_CONNECT_SERVICE" 2>/dev/null || true

    log_success "rpi-connect disabled"
}

# =============================================================================
# Removal
# =============================================================================

remove_rpi_connect() {
    log_info "Removing rpi-connect..."

    # Sign out first
    if command -v rpi-connect &>/dev/null; then
        log_info "Signing out..."
        rpi-connect signout 2>/dev/null || true
    fi

    # Stop and disable service
    disable_service 2>/dev/null || true

    # Remove packages
    sudo apt-get remove -y rpi-connect rpi-connect-lite 2>/dev/null || true
    sudo apt-get autoremove -y

    log_success "rpi-connect removed"
}

# =============================================================================
# Sign-in Helper
# =============================================================================

signin() {
    local auth_key="${1:-$RPI_CONNECT_KEY}"

    if ! is_installed; then
        log_error "rpi-connect is not installed"
        return 1
    fi

    if [[ -n "$auth_key" ]]; then
        log_info "Signing in with provided key..."
        rpi-connect signin --key "$auth_key"
    else
        log_info "Starting interactive sign-in..."
        rpi-connect signin
    fi
}

signout() {
    if ! is_installed; then
        log_error "rpi-connect is not installed"
        return 1
    fi

    log_info "Signing out..."
    rpi-connect signout
    log_success "Signed out"
}

# =============================================================================
# Main
# =============================================================================

usage() {
    cat << EOF
LeLamp - Raspberry Pi Connect Installation Script

Usage: $(basename "$0") <action> [options]

Actions:
  install [--auth-key KEY] [--lite]   Install rpi-connect
  status                              Show current status
  enable                              Enable and start service
  disable                             Disable and stop service
  signin [--key KEY]                  Sign in to Raspberry Pi Connect
  signout                             Sign out
  remove                              Remove rpi-connect

Options:
  --auth-key KEY    Authentication key for automatic sign-in
  --lite            Install lite version (no VNC/screen sharing)
  --key KEY         Same as --auth-key (for signin action)

Environment Variables:
  RPI_CONNECT_KEY   Authentication key (alternative to --auth-key)

Examples:
  $(basename "$0") install
  $(basename "$0") install --auth-key rpi-xxxx
  RPI_CONNECT_KEY=rpi-xxxx $(basename "$0") install
  $(basename "$0") signin
  $(basename "$0") status
EOF
}

main() {
    local action="${1:-}"
    shift || true

    # Parse arguments
    local auth_key=""
    local lite_mode="false"

    # Handle -y as shortcut for install (for consistency with other install scripts)
    if [[ "$action" == "-y" || "$action" == "--yes" ]]; then
        action="install"
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --auth-key|--key)
                auth_key="$2"
                shift 2
                ;;
            --lite)
                lite_mode="true"
                shift
                ;;
            -y|--yes)
                # Already handled, just skip
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Use RPI_CONNECT_KEY env var if no auth key provided
    if [[ -z "$auth_key" && -n "$RPI_CONNECT_KEY" ]]; then
        auth_key="$RPI_CONNECT_KEY"
    fi

    case "$action" in
        install)
            install_rpi_connect "$auth_key" "$lite_mode"
            ;;
        status|check)
            show_status
            ;;
        enable|start)
            enable_service
            ;;
        disable|stop)
            disable_service
            ;;
        signin|login)
            signin "$auth_key"
            ;;
        signout|logout)
            signout
            ;;
        remove|uninstall)
            remove_rpi_connect
            ;;
        -h|--help|help)
            usage
            exit 0
            ;;
        "")
            # Default to install if no action specified
            install_rpi_connect "$auth_key" "$lite_mode"
            ;;
        *)
            log_error "Unknown action: $action"
            usage
            exit 1
            ;;
    esac
}

# Run main if not sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
