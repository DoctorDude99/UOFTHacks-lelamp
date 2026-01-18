#!/bin/bash
#
# install_tailscale.sh - Install and configure Tailscale VPN
#
# Tailscale provides secure remote access to your LeLamp from anywhere.
#
# Usage:
#   ./install_tailscale.sh                           # Interactive install
#   ./install_tailscale.sh -y                        # Non-interactive (requires TAILSCALE_AUTH_KEY)
#   TAILSCALE_AUTH_KEY=tskey-xxx ./install_tailscale.sh -y  # With auth key
#   ./install_tailscale.sh --uninstall               # Remove Tailscale
#   ./install_tailscale.sh --status                  # Show status
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ACTION="install"

show_help() {
    echo "Tailscale VPN Installation for LeLamp"
    echo ""
    echo "Tailscale provides secure remote access to your LeLamp from anywhere."
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -y, --yes          Non-interactive mode (requires TAILSCALE_AUTH_KEY env var)"
    echo "  --status           Show Tailscale status"
    echo "  --uninstall        Remove Tailscale"
    echo "  -h, --help         Show this help"
    echo ""
    echo "Environment variables:"
    echo "  TAILSCALE_AUTH_KEY  Auth key from https://login.tailscale.com/admin/settings/keys"
    echo ""
    echo "Examples:"
    echo "  # Interactive install (will open browser for auth)"
    echo "  $0"
    echo ""
    echo "  # Non-interactive with auth key"
    echo "  TAILSCALE_AUTH_KEY=tskey-auth-xxx $0 -y"
    echo ""
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --status)
                ACTION="status"
                shift
                ;;
            --uninstall|--remove)
                ACTION="uninstall"
                shift
                ;;
            -y|--yes|--skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                shift
                ;;
        esac
    done
}

show_status() {
    print_header "Tailscale Status"

    if ! command -v tailscale &> /dev/null; then
        print_warning "Tailscale is not installed"
        return 0
    fi

    print_success "Tailscale is installed"
    echo ""

    # Show status
    echo "Status:"
    sudo tailscale status 2>/dev/null || echo "  Not connected"
    echo ""

    # Show IP
    local ip=$(sudo tailscale ip -4 2>/dev/null || true)
    if [ -n "$ip" ]; then
        echo "Tailscale IP: $ip"
    fi
}

uninstall_tailscale() {
    print_header "Uninstalling Tailscale"

    if ! command -v tailscale &> /dev/null; then
        print_info "Tailscale is not installed"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Remove Tailscale?" "n"; then
            print_info "Uninstall cancelled"
            return 0
        fi
    fi

    # Disconnect first
    sudo tailscale down 2>/dev/null || true

    # Remove package
    sudo apt-get remove -y tailscale || true
    sudo apt-get autoremove -y || true

    print_success "Tailscale uninstalled"
}

install_tailscale() {
    print_header "Tailscale VPN Installation"

    echo "Tailscale provides secure remote access to your LeLamp."
    echo ""
    echo "After installation, you can access your LeLamp from anywhere"
    echo "using its Tailscale hostname or IP address."
    echo ""

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Install Tailscale?" "y"; then
            print_info "Installation cancelled"
            return 0
        fi
    fi

    # Install Tailscale
    if ! command -v tailscale &> /dev/null; then
        print_info "Installing Tailscale..."
        curl -fsSL https://tailscale.com/install.sh | sh
        print_success "Tailscale installed"
    else
        print_success "Tailscale already installed"
    fi

    # Check for auth key
    if [ -n "$TAILSCALE_AUTH_KEY" ]; then
        # Validate auth key format
        if [[ ! "$TAILSCALE_AUTH_KEY" =~ ^tskey- ]]; then
            print_error "Invalid Tailscale auth key format (should start with 'tskey-')"
            return 1
        fi

        print_info "Authenticating with auth key..."
        sudo tailscale up --authkey="$TAILSCALE_AUTH_KEY" --accept-routes
        print_success "Tailscale connected with auth key"
    else
        # Interactive auth
        echo ""
        print_info "Starting Tailscale authentication..."
        echo ""
        echo "A browser window will open (or a URL will be shown)."
        echo "Log in to connect this device to your Tailnet."
        echo ""

        sudo tailscale up --accept-routes

        print_success "Tailscale connected"
    fi

    # Show status
    echo ""
    local ip=$(sudo tailscale ip -4 2>/dev/null || true)
    if [ -n "$ip" ]; then
        print_success "Tailscale IP: $ip"
        echo ""
        echo "You can now access this device remotely via:"
        echo "  ssh $(whoami)@$ip"
        echo "  http://$ip"
    fi
}

main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            install_tailscale
            ;;
        status)
            show_status
            ;;
        uninstall)
            uninstall_tailscale
            ;;
    esac
}

main "$@"
