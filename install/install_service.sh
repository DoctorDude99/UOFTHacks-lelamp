#!/bin/bash
#
# install_service.sh - Install LeLamp systemd service
#
# Configures LeLamp to run as a systemd service, enabling:
#   - Automatic startup on boot
#   - Service management (start/stop/restart)
#   - Log access via journalctl
#
# Usage:
#   ./install_service.sh                    # Interactive
#   ./install_service.sh -y                 # Install without prompting
#   ./install_service.sh --enable           # Install and enable
#   ./install_service.sh --start            # Install, enable, and start
#   ./install_service.sh --uninstall        # Remove service
#   ./install_service.sh --status           # Show service status
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
ENABLE_SERVICE=true   # Default to enabling service on boot
START_SERVICE=false

show_help() {
    echo "LeLamp Systemd Service Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --enable             Enable service to start on boot"
    echo "  --start              Start service after installation"
    echo "  --uninstall          Remove the service"
    echo "  --status             Show service status"
    echo "  --logs               Show service logs"
    show_help_footer
    echo "Service management:"
    echo "  sudo systemctl start lelamp.service"
    echo "  sudo systemctl stop lelamp.service"
    echo "  sudo systemctl restart lelamp.service"
    echo "  sudo systemctl status lelamp.service"
    echo "  sudo journalctl -u lelamp.service -f"
    echo ""
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --enable)
                ENABLE_SERVICE=true
                shift
                ;;
            --start)
                ENABLE_SERVICE=true
                START_SERVICE=true
                shift
                ;;
            --uninstall|--remove)
                ACTION="uninstall"
                shift
                ;;
            --status)
                ACTION="status"
                shift
                ;;
            --logs)
                ACTION="logs"
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

# Install systemd service
install_service() {
    print_header "Systemd Service Installation"

    LELAMP_DIR=$(get_lelamp_dir)

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will install LeLamp as a systemd service."
        echo "The service can start automatically on boot."
        echo ""
        if ! ask_yes_no "Install systemd service?" "y"; then
            print_info "Skipping service installation"
            return 0
        fi
    fi

    # Detect UV path (prefer /usr/local/bin for system-wide install)
    local uv_path
    if [ -f "/usr/local/bin/uv" ]; then
        uv_path="/usr/local/bin/uv"
    elif command -v uv &>/dev/null; then
        uv_path=$(which uv)
    elif [ -f "$HOME/.local/bin/uv" ]; then
        uv_path="$HOME/.local/bin/uv"
    else
        print_error "Could not find UV installation"
        print_info "Please ensure UV is installed first"
        return 1
    fi

    print_info "Using UV at: $uv_path"
    print_info "Using LeLamp at: $LELAMP_DIR"

    # Create service file
    local temp_service="/tmp/lelamp.service"
    cat > "$temp_service" << EOF
[Unit]
Description=LeLamp Runtime Service
After=network.target sound.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$LELAMP_DIR
ExecStart=$uv_path run main.py console
Restart=always
RestartSec=30
Environment=HOME=$HOME

[Install]
WantedBy=multi-user.target
EOF

    print_info "Installing service to /etc/systemd/system/..."

    if sudo cp "$temp_service" /etc/systemd/system/lelamp.service; then
        print_success "Service file installed"
        rm -f "$temp_service"
    else
        print_error "Failed to install service file"
        rm -f "$temp_service"
        return 1
    fi

    # Reload systemd
    print_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    # Ask about enabling if not specified via args
    # Default to enabling when running with -y (SKIP_CONFIRM)
    if [ "$ENABLE_SERVICE" != "true" ] && [ "$ENABLE_SERVICE" != "false" ]; then
        if [ "$SKIP_CONFIRM" = "true" ]; then
            ENABLE_SERVICE=true
        elif ask_yes_no "Enable LeLamp to start on boot?" "y"; then
            ENABLE_SERVICE=true
        fi
    fi

    if [ "$ENABLE_SERVICE" = "true" ]; then
        if sudo systemctl enable lelamp.service; then
            print_success "LeLamp service enabled (will start on boot)"
        else
            print_error "Failed to enable service"
        fi
    else
        print_info "Service installed but not enabled"
        print_info "Enable later with: sudo systemctl enable lelamp.service"
    fi

    # Ask about starting if not specified via args
    if [ "$START_SERVICE" != "true" ] && [ "$SKIP_CONFIRM" != "true" ]; then
        if ask_yes_no "Start the LeLamp service now?" "y"; then
            START_SERVICE=true
        fi
    fi

    if [ "$START_SERVICE" = "true" ]; then
        if sudo systemctl start lelamp.service; then
            print_success "LeLamp service started"
            print_info "Check status with: sudo systemctl status lelamp.service"
            print_info "View logs with: sudo journalctl -u lelamp.service -f"
        else
            print_error "Failed to start service"
            print_info "Check logs with: sudo journalctl -u lelamp.service"
        fi
    else
        print_info "Service not started"
        print_info "Start later with: sudo systemctl start lelamp.service"
    fi

    print_success "Systemd service setup complete"

    # Configure port 80 binding without sudo
    configure_port80
}

# Configure port 80 access without sudo
configure_port80() {
    print_header "Configuring Port 80 Access"

    local python_bin="$LELAMP_DIR/.venv/bin/python"

    if [ ! -f "$python_bin" ] && [ ! -L "$python_bin" ]; then
        print_warning "Virtual environment not found at $python_bin"
        print_info "Run this after installing Python dependencies"
        return 1
    fi

    # Resolve symlink to actual binary (setcap doesn't work on symlinks)
    local python_real=$(readlink -f "$python_bin")

    if [ ! -f "$python_real" ]; then
        print_error "Failed to resolve Python binary path"
        return 1
    fi

    print_info "Allowing Python to bind to port 80 without sudo..."

    if sudo setcap 'cap_net_bind_service=+ep' "$python_real"; then
        print_success "Port 80 access configured"
        print_info "WebUI can now run on port 80 without sudo"
    else
        print_error "Failed to set capabilities"
        print_warning "You may need to run WebUI with sudo or use a different port"
        return 1
    fi
}

# Uninstall service
uninstall_service() {
    print_header "Uninstalling LeLamp Service"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Are you sure you want to remove the LeLamp service?"; then
            print_info "Cancelled"
            return 0
        fi
    fi

    print_info "Stopping service..."
    sudo systemctl stop lelamp.service 2>/dev/null || true

    print_info "Disabling service..."
    sudo systemctl disable lelamp.service 2>/dev/null || true

    print_info "Removing service file..."
    sudo rm -f /etc/systemd/system/lelamp.service

    print_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    print_success "LeLamp service removed"
}

# Show service status
show_status() {
    print_header "LeLamp Service Status"
    sudo systemctl status lelamp.service --no-pager || true
}

# Show service logs
show_logs() {
    print_info "Showing LeLamp service logs (Ctrl+C to exit)..."
    sudo journalctl -u lelamp.service -f
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            install_service
            ;;
        uninstall)
            uninstall_service
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
    esac
}

# Run main function
main "$@"
