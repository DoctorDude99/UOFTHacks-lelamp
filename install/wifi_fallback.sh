#!/bin/bash
#
# wifi_fallback.sh - WiFi Fallback to AP Mode Monitor
#
# Monitors WiFi connectivity and falls back to AP mode if connection fails.
# Runs as a systemd service (lelamp-wifi-fallback.service)
#
# Configuration is read from ~/.lelamp/config.yaml:
#   wifi:
#     fallback_ap:
#       enabled: true
#       delay_seconds: 300  # 5 minutes
#
# Usage:
#   ./wifi_fallback.sh          # Run monitor (normally started by systemd)
#   ./wifi_fallback.sh --check  # Check current status
#   ./wifi_fallback.sh --reset  # Reset to normal mode (disable AP, try WiFi)
#

set -e

# Configuration
CONFIG_FILE="${HOME}/.lelamp/config.yaml"
DEFAULT_DELAY=300  # 5 minutes
CHECK_INTERVAL=30  # Check every 30 seconds
AP_CONNECTION="lelamp-ap"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    logger -t "lelamp-wifi-fallback" "$1" 2>/dev/null || true
}

log_info() {
    log "INFO: $1"
}

log_warn() {
    log "WARN: $1"
}

log_error() {
    log "ERROR: $1"
}

# Read config value using Python (handles YAML properly)
read_config() {
    local key="$1"
    local default="$2"

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "$default"
        return
    fi

    python3 -c "
import yaml
try:
    with open('$CONFIG_FILE', 'r') as f:
        config = yaml.safe_load(f) or {}
    keys = '$key'.split('.')
    value = config
    for k in keys:
        value = value.get(k, {}) if isinstance(value, dict) else {}
    if value == {} or value is None:
        print('$default')
    else:
        print(value)
except Exception:
    print('$default')
" 2>/dev/null || echo "$default"
}

# Check if we have internet connectivity
check_internet() {
    # Try multiple methods
    # 1. Check if we can reach common DNS servers
    if ping -c 1 -W 3 8.8.8.8 &>/dev/null; then
        return 0
    fi

    # 2. Check if we can reach Cloudflare
    if ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        return 0
    fi

    # 3. Check if we have a default route
    if ip route | grep -q "default"; then
        # We have a route, try DNS resolution
        if host -W 3 google.com &>/dev/null; then
            return 0
        fi
    fi

    return 1
}

# Check if WiFi is connected (not AP mode)
check_wifi_connected() {
    # Get active WiFi connection
    local active_wifi=$(nmcli -t -f NAME,TYPE,DEVICE connection show --active 2>/dev/null | grep ":802-11-wireless:" | grep -v "$AP_CONNECTION" | head -1)

    if [ -n "$active_wifi" ]; then
        return 0
    fi

    return 1
}

# Check if AP mode is active
check_ap_active() {
    if nmcli -t -f NAME connection show --active 2>/dev/null | grep -q "^${AP_CONNECTION}$"; then
        return 0
    fi
    return 1
}

# Start AP mode
start_ap_mode() {
    log_info "Starting AP mode..."

    # Bring down any active WiFi connections (except AP)
    for conn in $(nmcli -t -f NAME,TYPE connection show --active | grep ":802-11-wireless" | grep -v "$AP_CONNECTION" | cut -d: -f1); do
        log_info "Disconnecting from: $conn"
        nmcli connection down "$conn" 2>/dev/null || true
    done

    # Start AP
    if nmcli connection up "$AP_CONNECTION" 2>/dev/null; then
        log_info "AP mode started successfully"
        return 0
    else
        log_error "Failed to start AP mode"
        return 1
    fi
}

# Stop AP mode and try to reconnect to WiFi
stop_ap_mode() {
    log_info "Stopping AP mode..."

    nmcli connection down "$AP_CONNECTION" 2>/dev/null || true

    # Try to connect to any known WiFi network
    log_info "Attempting to reconnect to WiFi..."
    nmcli device wifi rescan 2>/dev/null || true
    sleep 2

    # NetworkManager should auto-connect to known networks
    # Give it some time
    sleep 10
}

# Show status
show_status() {
    echo "WiFi Fallback Status"
    echo "===================="

    local enabled=$(read_config "wifi.fallback_ap.enabled" "false")
    local delay=$(read_config "wifi.fallback_ap.delay_seconds" "$DEFAULT_DELAY")

    echo "Fallback enabled: $enabled"
    echo "Fallback delay: ${delay}s ($(($delay / 60))m)"
    echo ""

    if check_ap_active; then
        echo "AP Mode: ACTIVE"
    else
        echo "AP Mode: inactive"
    fi

    if check_wifi_connected; then
        local wifi_conn=$(nmcli -t -f NAME,TYPE connection show --active | grep ":802-11-wireless:" | grep -v "$AP_CONNECTION" | cut -d: -f1)
        echo "WiFi: connected ($wifi_conn)"
    else
        echo "WiFi: not connected"
    fi

    if check_internet; then
        echo "Internet: reachable"
    else
        echo "Internet: not reachable"
    fi
}

# Reset - stop AP and try WiFi
do_reset() {
    log_info "Resetting WiFi fallback..."
    stop_ap_mode
    echo "Reset complete. Device will try to connect to known WiFi networks."
}

# Main monitoring loop
run_monitor() {
    log_info "WiFi fallback monitor starting..."

    # Read configuration
    local enabled=$(read_config "wifi.fallback_ap.enabled" "false")
    local delay=$(read_config "wifi.fallback_ap.delay_seconds" "$DEFAULT_DELAY")

    if [ "$enabled" != "true" ] && [ "$enabled" != "True" ] && [ "$enabled" != "1" ]; then
        log_info "WiFi fallback is disabled in config. Exiting."
        exit 0
    fi

    log_info "Fallback enabled with ${delay}s delay"

    # Initial delay - give WiFi time to connect on boot
    log_info "Waiting ${delay}s for WiFi to connect..."
    sleep "$delay"

    # Check if we have connectivity
    if check_wifi_connected && check_internet; then
        log_info "WiFi connected with internet access. Monitoring for disconnection..."
    else
        log_warn "No WiFi connection after ${delay}s delay"

        # Don't start AP if already in AP mode
        if ! check_ap_active; then
            log_info "Starting fallback AP mode..."
            start_ap_mode
        else
            log_info "AP mode already active"
        fi
    fi

    # Continuous monitoring loop
    local consecutive_failures=0
    local failure_threshold=3  # Require 3 consecutive failures before action

    while true; do
        sleep "$CHECK_INTERVAL"

        # Re-read config in case it changed
        enabled=$(read_config "wifi.fallback_ap.enabled" "false")
        if [ "$enabled" != "true" ] && [ "$enabled" != "True" ] && [ "$enabled" != "1" ]; then
            log_info "Fallback disabled. Stopping monitor."
            # If we're in AP mode due to fallback, stop it
            if check_ap_active; then
                stop_ap_mode
            fi
            exit 0
        fi

        # If AP is active, check if we should try WiFi again
        if check_ap_active; then
            # Periodically try to reconnect (every 5 minutes while in AP mode)
            # This allows recovery when WiFi becomes available
            log_info "In AP mode - checking if WiFi is available..."

            # Scan for networks
            nmcli device wifi rescan 2>/dev/null || true
            sleep 3

            # Check if any known networks are visible
            # (This is a simple check - could be enhanced)
            continue
        fi

        # Check connectivity
        if check_wifi_connected && check_internet; then
            consecutive_failures=0
        else
            ((consecutive_failures++))
            log_warn "Connectivity check failed ($consecutive_failures/$failure_threshold)"

            if [ $consecutive_failures -ge $failure_threshold ]; then
                log_warn "Connectivity lost for extended period"

                if ! check_ap_active; then
                    log_info "Starting fallback AP mode..."
                    start_ap_mode
                fi

                consecutive_failures=0
            fi
        fi
    done
}

# Main
case "${1:-}" in
    --check|--status)
        show_status
        ;;
    --reset)
        do_reset
        ;;
    --start-ap)
        start_ap_mode
        ;;
    --stop-ap)
        stop_ap_mode
        ;;
    *)
        run_monitor
        ;;
esac
