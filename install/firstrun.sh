#!/bin/bash
#
# firstrun.sh - LeLamp First Boot Setup Script
#
# This script runs on first boot when configured via RPi Imager.
# It launches the WebUI setup wizard and waits for setup completion.
#
# RPi Imager Configuration:
# In the "custom" field under Advanced Options, add this path to firstrun.
# Or add to /boot/firstrun.sh before first boot.
#
# What it does:
#   1. Ensures LeLamp services are available
#   2. Starts the WebUI on port 80
#   3. Sets hostname to lelamp-setup.local for easy access
#   4. Waits for setup wizard completion
#   5. Removes itself after successful setup
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LELAMP_DIR="${LELAMP_DIR:-$HOME/lelamp}"

# Log file for debugging
LOG_FILE="/var/log/lelamp-firstrun.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

log "=== LeLamp First Boot Setup Starting ==="

# Check if running as root (needed for some operations)
if [ "$EUID" -ne 0 ]; then
    log "Not running as root, will use sudo where needed"
fi

# Set hostname for easy discovery
setup_hostname() {
    log "Setting up hostname for discovery..."

    # Set temporary hostname for setup mode
    if [ -f /etc/hostname ]; then
        ORIGINAL_HOSTNAME=$(cat /etc/hostname)
        if [ "$ORIGINAL_HOSTNAME" != "lelamp" ]; then
            echo "lelamp" | sudo tee /etc/hostname > /dev/null
            sudo hostname lelamp
            log "Hostname set to 'lelamp' (was: $ORIGINAL_HOSTNAME)"
        fi
    fi
}

# Ensure LeLamp directory exists
check_lelamp_dir() {
    if [ ! -d "$LELAMP_DIR" ]; then
        log "LeLamp directory not found at $LELAMP_DIR"

        # Try common locations
        for dir in "$HOME/lelamp" "/opt/lelamp" "/home/pi/lelamp"; do
            if [ -d "$dir" ]; then
                LELAMP_DIR="$dir"
                log "Found LeLamp at: $LELAMP_DIR"
                break
            fi
        done

        if [ ! -d "$LELAMP_DIR" ]; then
            log "ERROR: Cannot find LeLamp installation"
            log "Please install LeLamp first: ./install.sh"
            exit 1
        fi
    fi
}

# Mark first boot mode in config
set_firstboot_mode() {
    log "Setting first boot mode in config..."

    CONFIG_FILE="$LELAMP_DIR/config.yaml"

    if [ -f "$CONFIG_FILE" ]; then
        # Use Python to safely update YAML
        cd "$LELAMP_DIR"
        uv run python -c "
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f) or {}
config.setdefault('setup', {})
config['setup']['first_boot'] = True
config['setup']['setup_complete'] = False
config['setup']['current_step'] = 'welcome'
with open('config.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
print('Config updated for first boot')
"
        log "First boot mode enabled in config"
    else
        log "WARNING: Config file not found at $CONFIG_FILE"
    fi
}

# Start WebUI in setup mode
start_webui() {
    log "Starting LeLamp WebUI in setup mode..."

    cd "$LELAMP_DIR"

    # Kill any existing lelamp processes
    pkill -f "python.*lelamp" 2>/dev/null || true
    pkill -f "uvicorn.*app:app" 2>/dev/null || true

    sleep 2

    # Start WebUI on port 80 (setup mode)
    log "Starting WebUI on port 80..."
    sudo -E uv run python -m uvicorn web.app:app --host 0.0.0.0 --port 80 &
    WEBUI_PID=$!

    sleep 5

    if kill -0 $WEBUI_PID 2>/dev/null; then
        log "WebUI started successfully (PID: $WEBUI_PID)"
    else
        log "ERROR: WebUI failed to start"
        exit 1
    fi
}

# Display setup instructions
show_instructions() {
    log ""
    log "================================================"
    log "      LeLamp Setup Wizard Ready!"
    log "================================================"
    log ""
    log "Connect to the setup wizard:"
    log ""
    log "  1. Connect to the same WiFi network as this Pi"
    log "  2. Open a browser and go to:"
    log ""
    log "     http://lelamp.local"
    log "     or http://$(hostname -I | awk '{print $1}')"
    log ""
    log "  3. Follow the on-screen instructions"
    log ""
    log "================================================"
    log ""
}

# Wait for setup completion
wait_for_setup() {
    log "Waiting for setup wizard completion..."

    CONFIG_FILE="$LELAMP_DIR/config.yaml"

    while true; do
        # Check if setup is complete
        if [ -f "$CONFIG_FILE" ]; then
            SETUP_COMPLETE=$(cd "$LELAMP_DIR" && uv run python -c "
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f) or {}
print(config.get('setup', {}).get('setup_complete', False))
" 2>/dev/null || echo "False")

            if [ "$SETUP_COMPLETE" = "True" ]; then
                log "Setup completed!"
                return 0
            fi
        fi

        sleep 10
    done
}

# Cleanup after setup
cleanup_firstrun() {
    log "Cleaning up first run setup..."

    # Clear first_boot flag
    cd "$LELAMP_DIR"
    uv run python -c "
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f) or {}
config.setdefault('setup', {})
config['setup']['first_boot'] = False
with open('config.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
print('First boot flag cleared')
"

    # Remove this script from firstrun.d if present
    if [ -f "/boot/firstrun.d/lelamp.sh" ]; then
        sudo rm -f "/boot/firstrun.d/lelamp.sh"
        log "Removed firstrun script"
    fi

    log "First run setup complete!"
}

# Main execution
main() {
    log "Starting LeLamp first boot setup..."

    setup_hostname
    check_lelamp_dir
    set_firstboot_mode
    start_webui
    show_instructions
    wait_for_setup
    cleanup_firstrun

    log "LeLamp is ready! Rebooting to start normal operation..."

    # Reboot to start normal services
    sudo reboot
}

# Run main
main "$@"
