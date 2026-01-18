#!/bin/bash
#
# install_wifi_ap.sh - Configure WiFi AP mode for first-time setup
#
# Sets up NetworkManager for AP mode:
#   - Creates AP with SSID lelamp_SERIAL
#   - Password: lelamp123
#   - IP: 192.168.4.1
#   - DHCP via NetworkManager shared mode
#
# Usage:
#   ./install_wifi_ap.sh                     # Configure AP mode
#   ./install_wifi_ap.sh --serial XXXXXXXX   # Use specific serial suffix
#   ./install_wifi_ap.sh --check             # Check AP status
#   ./install_wifi_ap.sh --disable           # Disable AP mode
#   ./install_wifi_ap.sh --enable            # Enable AP mode
#   ./install_wifi_ap.sh --start             # Start AP now
#   ./install_wifi_ap.sh --stop              # Stop AP now
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
DEVICE_SERIAL=""
AP_PASSWORD="lelamp123"
AP_IP="192.168.4.1"
AP_INTERFACE="wlan0"
CONNECTION_NAME="lelamp-ap"

show_help() {
    echo "LeLamp WiFi AP Mode Configuration"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --serial SERIAL    Use specific serial suffix for SSID"
    echo "  --check            Check current AP status"
    echo "  --disable          Disable AP auto-start service"
    echo "  --enable           Enable AP auto-start service"
    echo "  --start            Start AP now"
    echo "  --stop             Stop AP now"
    echo "  --remove           Remove AP configuration completely"
    echo "  --status           Show detailed status"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --serial)
                DEVICE_SERIAL="$2"
                shift 2
                ;;
            --check|--status)
                ACTION="check"
                shift
                ;;
            --disable)
                ACTION="disable"
                shift
                ;;
            --enable)
                ACTION="enable"
                shift
                ;;
            --start)
                ACTION="start"
                shift
                ;;
            --stop)
                ACTION="stop"
                shift
                ;;
            --remove)
                ACTION="remove"
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

# Get device serial from hardware
get_device_serial() {
    local serial_file="/sys/firmware/devicetree/base/serial-number"
    if [ -f "$serial_file" ]; then
        tr -d '\0' < "$serial_file"
    else
        echo "unknown"
    fi
}

get_device_serial_short() {
    local serial=$(get_device_serial)
    if [ "$serial" = "unknown" ]; then
        echo "unknown"
    else
        echo "${serial: -8}"
    fi
}

# Check if NetworkManager is available
check_network_manager() {
    if ! command -v nmcli &> /dev/null; then
        print_error "NetworkManager (nmcli) is not installed"
        print_info "Install with: sudo apt-get install network-manager"
        return 1
    fi

    if ! systemctl is-active --quiet NetworkManager; then
        print_warning "NetworkManager is not running"
        print_info "Start with: sudo systemctl start NetworkManager"
        return 1
    fi

    return 0
}

# Check current AP status
check_ap_status() {
    print_header "WiFi AP Status"

    # Check NetworkManager
    if ! check_network_manager; then
        return 1
    fi

    # Check if AP connection exists
    if nmcli connection show "$CONNECTION_NAME" &> /dev/null; then
        print_success "AP connection '$CONNECTION_NAME' exists"

        # Get connection details
        local ssid=$(nmcli -g 802-11-wireless.ssid connection show "$CONNECTION_NAME")
        local mode=$(nmcli -g 802-11-wireless.mode connection show "$CONNECTION_NAME")
        local autoconnect=$(nmcli -g connection.autoconnect connection show "$CONNECTION_NAME")

        echo ""
        echo "  SSID: $ssid"
        echo "  Mode: $mode"
        echo "  Autoconnect: $autoconnect"
    else
        print_warning "AP connection '$CONNECTION_NAME' not found"
    fi

    # Check if AP is active
    if nmcli connection show --active | grep -q "$CONNECTION_NAME"; then
        print_success "AP is currently ACTIVE"

        # Get IP address
        local ip=$(ip -4 addr show "$AP_INTERFACE" 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
        echo "  IP: $ip"
    else
        print_info "AP is currently INACTIVE"
    fi

    # Check systemd service
    echo ""
    if systemctl is-enabled lelamp-ap.service &> /dev/null; then
        print_success "AP service is enabled (will start on boot)"
    else
        print_info "AP service is disabled"
    fi

    # Check if wifi_configured marker exists
    local config_marker="$HOME/.lelamp/.wifi_configured"
    if [ -f "$config_marker" ]; then
        print_info "WiFi configured marker exists - AP will not auto-start"
    else
        print_info "WiFi not configured - AP will auto-start on boot"
    fi
}

# Setup WiFi AP mode
setup_wifi_ap() {
    print_header "WiFi AP Mode Configuration"

    # Check NetworkManager
    if ! check_network_manager; then
        print_error "NetworkManager is required for AP mode"
        return 1
    fi

    # Get or use provided serial
    if [ -z "$DEVICE_SERIAL" ]; then
        DEVICE_SERIAL=$(get_device_serial_short)
    fi

    local ap_ssid="lelamp_${DEVICE_SERIAL}"

    print_info "AP SSID: $ap_ssid"
    print_info "AP Password: $AP_PASSWORD"
    print_info "AP IP: $AP_IP"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Configure WiFi AP mode?" "y"; then
            print_info "Skipping AP configuration"
            return 0
        fi
    fi

    # Remove existing AP connection
    print_info "Removing existing AP connection (if any)..."
    sudo nmcli connection delete "$CONNECTION_NAME" 2>/dev/null || true

    # Create AP connection
    print_info "Creating AP connection..."
    sudo nmcli connection add type wifi ifname "$AP_INTERFACE" con-name "$CONNECTION_NAME" \
        autoconnect no ssid "$ap_ssid" \
        802-11-wireless.mode ap \
        802-11-wireless.band bg \
        802-11-wireless.channel 7 \
        802-11-wireless-security.key-mgmt wpa-psk \
        802-11-wireless-security.psk "$AP_PASSWORD" \
        ipv4.method shared \
        ipv4.addresses "$AP_IP/24"

    print_success "AP connection created: $ap_ssid"

    # Create systemd service
    create_ap_service

    print_success "WiFi AP mode configured"
    echo ""
    echo "To start AP now: $0 --start"
    echo "To check status: $0 --check"
}

# Create systemd service for auto-starting AP
create_ap_service() {
    print_info "Creating AP auto-start service..."

    local user_home="$HOME"
    local config_marker="$user_home/.lelamp/.wifi_configured"

    sudo tee /etc/systemd/system/lelamp-ap.service > /dev/null << EOF
[Unit]
Description=LeLamp WiFi AP Mode
After=NetworkManager.service
Wants=NetworkManager.service
ConditionPathExists=!$config_marker

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/nmcli connection up $CONNECTION_NAME
ExecStop=/usr/bin/nmcli connection down $CONNECTION_NAME

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable lelamp-ap.service

    print_success "AP service created and enabled"
    print_info "AP will auto-start on boot until WiFi is configured"

    # Also create the fallback service
    create_fallback_service
}

# Create systemd service for WiFi fallback monitoring
create_fallback_service() {
    print_info "Creating WiFi fallback service..."

    local user_home="$HOME"
    local script_path="$SCRIPT_DIR/wifi_fallback.sh"

    # Copy the fallback script to a system location
    sudo cp "$script_path" /usr/local/bin/lelamp-wifi-fallback
    sudo chmod +x /usr/local/bin/lelamp-wifi-fallback

    sudo tee /etc/systemd/system/lelamp-wifi-fallback.service > /dev/null << EOF
[Unit]
Description=LeLamp WiFi Fallback to AP Mode Monitor
After=NetworkManager.service network-online.target
Wants=NetworkManager.service

[Service]
Type=simple
User=$USER
Environment=HOME=$user_home
ExecStart=/usr/local/bin/lelamp-wifi-fallback
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable lelamp-wifi-fallback.service

    print_success "WiFi fallback service created and enabled"
    print_info "Configure via config.yaml: wifi.fallback_ap.enabled and wifi.fallback_ap.delay_seconds"
}

# Start AP now
start_ap() {
    print_header "Starting WiFi AP"

    if ! check_network_manager; then
        return 1
    fi

    if ! nmcli connection show "$CONNECTION_NAME" &> /dev/null; then
        print_error "AP connection not found - run setup first"
        return 1
    fi

    print_info "Starting AP..."

    # Disconnect from any existing WiFi first
    sudo nmcli device disconnect "$AP_INTERFACE" 2>/dev/null || true

    # Start AP
    if sudo nmcli connection up "$CONNECTION_NAME"; then
        print_success "AP started successfully"

        # Get IP
        sleep 2
        local ip=$(ip -4 addr show "$AP_INTERFACE" 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
        echo ""
        echo "Connect to WiFi: $(nmcli -g 802-11-wireless.ssid connection show "$CONNECTION_NAME")"
        echo "Password: $AP_PASSWORD"
        echo "Access WebUI at: http://$ip"
    else
        print_error "Failed to start AP"
        return 1
    fi
}

# Stop AP
stop_ap() {
    print_header "Stopping WiFi AP"

    if ! check_network_manager; then
        return 1
    fi

    if nmcli connection show --active | grep -q "$CONNECTION_NAME"; then
        print_info "Stopping AP..."
        if sudo nmcli connection down "$CONNECTION_NAME"; then
            print_success "AP stopped"
        else
            print_error "Failed to stop AP"
            return 1
        fi
    else
        print_info "AP is not running"
    fi
}

# Enable AP auto-start
enable_ap_service() {
    print_header "Enabling AP Auto-Start"

    if [ ! -f /etc/systemd/system/lelamp-ap.service ]; then
        print_error "AP service not found - run setup first"
        return 1
    fi

    sudo systemctl enable lelamp-ap.service
    print_success "AP service enabled"

    # Remove wifi_configured marker to allow AP to start
    local config_marker="$HOME/.lelamp/.wifi_configured"
    if [ -f "$config_marker" ]; then
        if [ "$SKIP_CONFIRM" = "true" ] || ask_yes_no "Remove WiFi configured marker?" "n"; then
            rm -f "$config_marker"
            print_success "WiFi configured marker removed"
        fi
    fi
}

# Disable AP auto-start
disable_ap_service() {
    print_header "Disabling AP Auto-Start"

    if systemctl is-enabled lelamp-ap.service &> /dev/null; then
        sudo systemctl disable lelamp-ap.service
        print_success "AP service disabled"
    else
        print_info "AP service was not enabled"
    fi

    # Stop AP if running
    if nmcli connection show --active | grep -q "$CONNECTION_NAME"; then
        print_info "Stopping running AP..."
        sudo nmcli connection down "$CONNECTION_NAME" 2>/dev/null || true
    fi
}

# Remove AP configuration completely
remove_ap() {
    print_header "Removing WiFi AP Configuration"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Remove all AP configuration?" "n"; then
            print_info "Cancelled"
            return 0
        fi
    fi

    # Stop and disable service
    sudo systemctl stop lelamp-ap.service 2>/dev/null || true
    sudo systemctl disable lelamp-ap.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/lelamp-ap.service
    sudo systemctl daemon-reload

    # Remove connection
    sudo nmcli connection delete "$CONNECTION_NAME" 2>/dev/null || true

    print_success "AP configuration removed"
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            setup_wifi_ap
            ;;
        check)
            check_ap_status
            ;;
        start)
            start_ap
            ;;
        stop)
            stop_ap
            ;;
        enable)
            enable_ap_service
            ;;
        disable)
            disable_ap_service
            ;;
        remove)
            remove_ap
            ;;
    esac
}

# Run main function
main "$@"
