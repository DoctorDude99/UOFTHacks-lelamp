#!/bin/bash
#
# oem_install.sh - LeLamp OEM Manufacturing Installation Script
#
# This script provisions a fresh Raspberry Pi for LeLamp manufacturing.
# It can be run via: curl -sSL http://your-server/oem_install.sh | bash
#
# Environment variables (passed via curl | bash):
#   TAILSCALE_AUTH_KEY - Tailscale authentication key (optional)
#   RPI_CONNECT_KEY    - Raspberry Pi Connect key (optional)
#   HUB_URL            - LeLamp Hub server URL (optional, for device registration)
#   SKIP_REBOOT        - Set to "true" to skip final reboot
#   SKIP_AP            - Set to "true" to skip WiFi AP setup
#   SKIP_USER          - Set to "true" to skip lelamp user creation/password setup
#   WIFI_COUNTRY       - WiFi regulatory country code (default: CA)
#   LOCAL_AI           - Set to "false" to skip Piper/Ollama installation (default: true)
#
# Features:
#   - Ensures script runs as 'lelamp' user (creates if needed)
#   - Reads RPi5 serial number from hardware
#   - Sets default credentials (lelamp/lelamp)
#   - Enables SSH
#   - Configures WiFi AP mode for first-time setup
#   - Sets hostname to lelamp-SERIAL
#   - Runs full component installation
#   - Installs Piper TTS and Ollama for local AI (default, set LOCAL_AI=false to skip)
#   - Registers device with Hub server
#
# Usage:
#   # Basic OEM install
#   curl -sSL https://raw.githubusercontent.com/humancomputerlab/lelampv2/main/oem_install.sh | bash
#
#   # With remote access keys
#   TAILSCALE_AUTH_KEY=tskey-xxx RPI_CONNECT_KEY=xxx curl -sSL https://raw.githubusercontent.com/humancomputerlab/lelampv2/main/oem_install.sh | bash
#

set -e

# =============================================================================
# Configuration
# =============================================================================

REPO_URL="${REPO_URL:-https://github.com/humancomputerlab/lelampv2.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
TARGET_DIR="${TARGET_DIR:-$HOME/lelampv2}"
HUB_URL="${HUB_URL:-https://hub.lelamp.com}"
LOG_FILE="/var/log/lelamp-oem-install.log"

# =============================================================================
# Colors and Output Helpers
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log() {
    local msg="$(date '+%Y-%m-%d %H:%M:%S') $1"
    echo -e "$msg"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
    log "=== $1 ==="
}

print_success() {
    echo -e "${GREEN}[OK] $1${NC}"
    log "[OK] $1"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
    log "[ERROR] $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
    log "[WARN] $1"
}

print_info() {
    echo -e "${BLUE}[INFO] $1${NC}"
    log "[INFO] $1"
}

print_step() {
    echo -e "${CYAN}[$1/$2]${NC} $3"
    log "[$1/$2] $3"
}

# =============================================================================
# Device Identity Functions
# =============================================================================

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

get_device_model() {
    local model_file="/proc/device-tree/model"
    if [ -f "$model_file" ]; then
        cat "$model_file" | tr -d '\0'
    else
        echo "Unknown"
    fi
}

# =============================================================================
# User Check - Must run as 'lelamp' user
# =============================================================================

check_or_create_lelamp_user() {
    local current_user=$(whoami)

    # If already running as lelamp, we're good
    if [ "$current_user" = "lelamp" ]; then
        return 0
    fi

    # If SKIP_USER is set, continue as current user
    if [ "$SKIP_USER" = "true" ]; then
        echo -e "${YELLOW}[WARN] SKIP_USER=true - continuing as '$current_user' instead of 'lelamp'${NC}"
        return 0
    fi

    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}LeLamp User Check${NC}"
    echo -e "${BLUE}============================================${NC}\n"

    echo -e "${YELLOW}[WARN] This script must be run as the 'lelamp' user${NC}"
    echo -e "${BLUE}[INFO] Current user: $current_user${NC}"

    # Check if lelamp user exists
    if id "lelamp" &>/dev/null; then
        echo -e "${GREEN}[OK] User 'lelamp' already exists${NC}"
    else
        echo -e "${BLUE}[INFO] Creating user 'lelamp'...${NC}"

        # Create lelamp user with home directory
        sudo useradd -m -s /bin/bash lelamp

        # Set password to 'lelamp'
        echo "lelamp:lelamp" | sudo chpasswd

        # Add to sudo group
        sudo usermod -aG sudo lelamp

        echo -e "${GREEN}[OK] User 'lelamp' created with password 'lelamp'${NC}"
    fi

    # Always ensure passwordless sudo for OEM install (use separate file to avoid conflicts)
    # This file takes precedence and won't be overwritten by install_sudoers.sh
    echo -e "${BLUE}[INFO] Configuring passwordless sudo for OEM install...${NC}"
    echo "lelamp ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/00-lelamp-oem > /dev/null
    sudo chmod 440 /etc/sudoers.d/00-lelamp-oem

    # Re-run this script as lelamp user
    echo -e "${BLUE}[INFO] Switching to 'lelamp' user and continuing...${NC}"
    echo ""

    # Build environment variable exports
    local env_exports=""
    [ -n "$TAILSCALE_AUTH_KEY" ] && env_exports="${env_exports}export TAILSCALE_AUTH_KEY='$TAILSCALE_AUTH_KEY'; "
    [ -n "$RPI_CONNECT_KEY" ] && env_exports="${env_exports}export RPI_CONNECT_KEY='$RPI_CONNECT_KEY'; "
    [ -n "$HUB_URL" ] && env_exports="${env_exports}export HUB_URL='$HUB_URL'; "
    [ -n "$SKIP_REBOOT" ] && env_exports="${env_exports}export SKIP_REBOOT='$SKIP_REBOOT'; "
    [ -n "$SKIP_AP" ] && env_exports="${env_exports}export SKIP_AP='$SKIP_AP'; "
    [ -n "$SKIP_USER" ] && env_exports="${env_exports}export SKIP_USER='$SKIP_USER'; "
    [ -n "$WIFI_COUNTRY" ] && env_exports="${env_exports}export WIFI_COUNTRY='$WIFI_COUNTRY'; "
    [ -n "$REPO_URL" ] && env_exports="${env_exports}export REPO_URL='$REPO_URL'; "
    [ -n "$REPO_BRANCH" ] && env_exports="${env_exports}export REPO_BRANCH='$REPO_BRANCH'; "
    [ -n "$LOCAL_AI" ] && env_exports="${env_exports}export LOCAL_AI='$LOCAL_AI'; "

    # Check if script exists as a file (e.g., cloned repo) vs piped from curl
    local script_path="${BASH_SOURCE[0]}"
    if [ -f "$script_path" ] && [ -r "$script_path" ]; then
        # Script exists as a file - run it directly
        exec sudo -u lelamp bash -c "${env_exports}bash '$script_path'"
    else
        # Script was piped (curl | bash) - re-fetch it
        exec sudo -u lelamp bash -c "${env_exports}bash <(curl -sSL https://raw.githubusercontent.com/humancomputerlab/lelampv2/main/oem_install.sh)"
    fi
}

# =============================================================================
# Installation Steps
# =============================================================================

# Step 1: Initialize logging and environment
init_oem_install() {
    print_header "LeLamp OEM Installation"

    # Create log directory
    sudo mkdir -p "$(dirname "$LOG_FILE")"
    sudo touch "$LOG_FILE"
    sudo chmod 666 "$LOG_FILE"

    log "=== OEM Installation Started ==="
    log "User: $(whoami)"
    log "Home: $HOME"
    log "Date: $(date)"

    # Read device info
    DEVICE_SERIAL=$(get_device_serial)
    DEVICE_SERIAL_SHORT=$(get_device_serial_short)
    DEVICE_MODEL=$(get_device_model)

    echo ""
    echo "Device Information:"
    echo "  Serial: $DEVICE_SERIAL"
    echo "  Model:  $DEVICE_MODEL"
    echo ""

    if [ "$DEVICE_SERIAL" = "unknown" ]; then
        print_warning "Could not read device serial - using fallback"
        DEVICE_SERIAL="unknown-$(date +%s)"
        DEVICE_SERIAL_SHORT="${DEVICE_SERIAL: -8}"
    fi
}

# Step 2: Store device serial in .env
store_device_serial() {
    print_header "Storing Device Serial"

    # Create .lelamp directory
    mkdir -p "$HOME/.lelamp"

    # Create or update .env file
    local env_file="$HOME/.lelamp/.env"

    if [ -f "$env_file" ]; then
        # Remove existing DEVICE_SERIAL line
        sed -i '/^DEVICE_SERIAL=/d' "$env_file"
    fi

    # Append device serial
    echo "DEVICE_SERIAL=$DEVICE_SERIAL" >> "$env_file"

    # Secure permissions
    chmod 600 "$env_file"

    print_success "Device serial stored in ~/.lelamp/.env"
}

# Step 3: Set default credentials
set_default_credentials() {
    print_header "Setting Default Credentials"

    if [ "$SKIP_USER" = "true" ]; then
        print_info "SKIP_USER=true - skipping password setup"
        return 0
    fi

    local current_user=$(whoami)

    if [ "$current_user" = "root" ]; then
        print_warning "Running as root - skipping password change"
        return 0
    fi

    print_info "Setting password for $current_user to 'lelamp'"
    echo "$current_user:lelamp" | sudo chpasswd

    print_success "Password set to 'lelamp'"
}

# Step 4: Enable SSH
enable_ssh() {
    print_header "Enabling SSH"

    # Enable and start SSH service
    sudo systemctl enable ssh 2>/dev/null || sudo systemctl enable sshd 2>/dev/null || true
    sudo systemctl start ssh 2>/dev/null || sudo systemctl start sshd 2>/dev/null || true

    # Create SSH marker file (for headless boot)
    sudo touch /boot/ssh 2>/dev/null || sudo touch /boot/firmware/ssh 2>/dev/null || true

    print_success "SSH enabled and started"
}

# Step 5: Configure WiFi country
configure_wifi_country() {
    print_header "Configuring WiFi Country"

    local country=""

    # If WIFI_COUNTRY is set via environment, use it
    if [ -n "$WIFI_COUNTRY" ]; then
        country="$WIFI_COUNTRY"
        print_info "Using WiFi country from environment: $country"
    elif [ "$SKIP_CONFIRM" != "true" ]; then
        # Interactive mode - show selection menu
        echo ""
        echo "Select your WiFi regulatory country:"
        echo ""
        echo "  1) CA - Canada (default)"
        echo "  2) US - United States"
        echo "  3) GB - United Kingdom"
        echo "  4) AU - Australia"
        echo "  5) DE - Germany"
        echo "  6) FR - France"
        echo "  7) JP - Japan"
        echo "  8) Other (enter code manually)"
        echo ""
        read -p "Enter choice [1-8] (default: 1): " country_choice < /dev/tty || country_choice="1"
        country_choice=${country_choice:-1}

        case $country_choice in
            1) country="CA" ;;
            2) country="US" ;;
            3) country="GB" ;;
            4) country="AU" ;;
            5) country="DE" ;;
            6) country="FR" ;;
            7) country="JP" ;;
            8)
                read -p "Enter 2-letter country code: " country < /dev/tty
                country=$(echo "$country" | tr '[:lower:]' '[:upper:]')
                ;;
            *) country="CA" ;;
        esac
    else
        # Non-interactive mode - default to Canada
        country="CA"
    fi

    print_info "Setting WiFi regulatory country to: $country"

    # Check if rfkill shows WiFi as blocked
    if command -v rfkill &> /dev/null; then
        if rfkill list wifi 2>/dev/null | grep -q "Soft blocked: yes"; then
            print_info "WiFi is currently blocked by rfkill"
        fi
    fi

    # Set country using raspi-config (most reliable method)
    if command -v raspi-config &> /dev/null; then
        sudo raspi-config nonint do_wifi_country "$country" 2>/dev/null || true
        print_success "WiFi country set to $country"
    else
        # Fallback: directly set regulatory domain
        if command -v iw &> /dev/null; then
            sudo iw reg set "$country" 2>/dev/null || true
        fi
        # Also update wpa_supplicant.conf
        if [ -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
            if ! grep -q "country=" /etc/wpa_supplicant/wpa_supplicant.conf; then
                echo "country=$country" | sudo tee -a /etc/wpa_supplicant/wpa_supplicant.conf > /dev/null
            else
                sudo sed -i "s/^country=.*/country=$country/" /etc/wpa_supplicant/wpa_supplicant.conf
            fi
        fi
        print_success "WiFi regulatory domain set to $country"
    fi

    # Unblock WiFi if blocked
    if command -v rfkill &> /dev/null; then
        sudo rfkill unblock wifi 2>/dev/null || true
        print_success "WiFi unblocked"
    fi
}

# Step 6: Set hostname
set_hostname() {
    print_header "Setting Hostname"

    local hostname="lelamp-${DEVICE_SERIAL_SHORT}"

    print_info "Setting hostname to: $hostname"

    # Set hostname
    echo "$hostname" | sudo tee /etc/hostname > /dev/null
    sudo hostname "$hostname"

    # Update /etc/hosts
    if grep -q "127.0.1.1" /etc/hosts; then
        sudo sed -i "s/127.0.1.1.*/127.0.1.1\t$hostname/" /etc/hosts
    else
        echo "127.0.1.1	$hostname" | sudo tee -a /etc/hosts > /dev/null
    fi

    print_success "Hostname set to $hostname"
}

# Step 6: Install git and clone repository
clone_repository() {
    print_header "Cloning Repository"

    # Install git if needed
    if ! command -v git &> /dev/null; then
        print_info "Installing git..."
        sudo apt-get update
        sudo apt-get install -y git
    fi

    # Clone or update repository
    if [ -d "$TARGET_DIR" ]; then
        print_info "Updating existing repository..."
        cd "$TARGET_DIR"
        if git fetch origin 2>/dev/null; then
            git checkout "$REPO_BRANCH" 2>/dev/null || git checkout -b "$REPO_BRANCH" "origin/$REPO_BRANCH" 2>/dev/null || true
            git pull origin "$REPO_BRANCH" 2>/dev/null || true
            print_success "Repository updated"
        else
            print_warning "Could not fetch updates (network unavailable?) - using existing files"
        fi
    else
        print_info "Cloning repository from $REPO_URL..."
        if git clone -b "$REPO_BRANCH" "$REPO_URL" "$TARGET_DIR" 2>/dev/null; then
            print_success "Repository cloned to $TARGET_DIR"
        else
            print_warning "Could not clone repository (network unavailable or private repo?)"
            # Check if there's an existing install we can use
            if [ -d "$HOME/lelampv2" ]; then
                TARGET_DIR="$HOME/lelampv2"
                print_info "Using existing directory: $TARGET_DIR"
            else
                print_error "No repository available and cannot clone"
                print_info "Please ensure network connectivity or copy lelampv2 manually"
                return 1
            fi
        fi
    fi

    cd "$TARGET_DIR"
}

# Step 7: Run WiFi AP setup
setup_wifi_ap() {
    print_header "Configuring WiFi AP Mode"

    if [ "$SKIP_AP" = "true" ]; then
        print_info "SKIP_AP=true - skipping WiFi AP setup"
        return 0
    fi

    local ap_ssid="lelamp_${DEVICE_SERIAL_SHORT}"
    local ap_password="lelamp123"

    print_info "AP SSID: $ap_ssid"
    print_info "AP Password: $ap_password"

    # Check if install script exists
    if [ -f "$TARGET_DIR/install/install_wifi_ap.sh" ]; then
        bash "$TARGET_DIR/install/install_wifi_ap.sh" --serial "$DEVICE_SERIAL_SHORT" -y
    else
        print_warning "WiFi AP installer not found - will be configured later"

        # Basic NetworkManager setup
        if command -v nmcli &> /dev/null; then
            # Remove existing AP connection
            sudo nmcli connection delete lelamp-ap 2>/dev/null || true

            # Create AP connection
            sudo nmcli connection add type wifi ifname wlan0 con-name lelamp-ap \
                autoconnect no ssid "$ap_ssid" \
                802-11-wireless.mode ap \
                802-11-wireless.band bg \
                802-11-wireless-security.key-mgmt wpa-psk \
                802-11-wireless-security.psk "$ap_password" \
                ipv4.method shared \
                ipv4.addresses "192.168.4.1/24" 2>/dev/null || true

            print_success "WiFi AP configured via NetworkManager"
        else
            print_warning "NetworkManager not available - skipping AP setup"
        fi
    fi
}

# Step 8: Setup Tailscale (optional)
setup_tailscale() {
    print_header "Setting Up Tailscale"

    if [ -z "$TAILSCALE_AUTH_KEY" ]; then
        print_info "TAILSCALE_AUTH_KEY not provided - skipping"
        return 0
    fi

    # Use the dedicated install script
    if [ -f "$TARGET_DIR/install/install_tailscale.sh" ]; then
        TAILSCALE_AUTH_KEY="$TAILSCALE_AUTH_KEY" bash "$TARGET_DIR/install/install_tailscale.sh" -y
    else
        # Fallback if script doesn't exist
        if ! command -v tailscale &> /dev/null; then
            print_info "Installing Tailscale..."
            curl -fsSL https://tailscale.com/install.sh | sh
        fi
        print_info "Authenticating with Tailscale..."
        sudo tailscale up --authkey="$TAILSCALE_AUTH_KEY" --accept-routes
        print_success "Tailscale configured"
    fi
}

# Step 9: Setup rpi-connect (optional)
setup_rpi_connect() {
    print_header "Setting Up Raspberry Pi Connect"

    if [ -z "$RPI_CONNECT_KEY" ]; then
        print_info "RPI_CONNECT_KEY not provided - skipping"
        return 0
    fi

    # Use the dedicated install script
    if [ -f "$TARGET_DIR/install/install_rpi_connect.sh" ]; then
        RPI_CONNECT_KEY="$RPI_CONNECT_KEY" bash "$TARGET_DIR/install/install_rpi_connect.sh" -y
    else
        print_warning "install_rpi_connect.sh not found - skipping"
    fi
}

# Step 10: Collect system info
collect_system_info() {
    print_header "Collecting System Information"

    local info_file="$HOME/.lelamp/system_info.json"

    # Get system info
    local os_version=$(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)
    local kernel=$(uname -r)
    local memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local memory_mb=$((memory_kb / 1024))
    local cpu_cores=$(nproc)
    local arch=$(uname -m)

    # Create JSON
    cat > "$info_file" << EOF
{
    "serial": "$DEVICE_SERIAL",
    "serial_short": "$DEVICE_SERIAL_SHORT",
    "model": "$DEVICE_MODEL",
    "os_version": "$os_version",
    "kernel": "$kernel",
    "memory_mb": $memory_mb,
    "cpu_cores": $cpu_cores,
    "architecture": "$arch",
    "hostname": "lelamp-${DEVICE_SERIAL_SHORT}",
    "provisioned_at": "$(date -Iseconds)",
    "oem_install_version": "1.0.0"
}
EOF

    print_success "System info saved to $info_file"
    cat "$info_file"
}

# Step 11: Run main LeLamp installer
run_main_installer() {
    print_header "Running LeLamp Installation"

    if [ ! -f "$TARGET_DIR/install.sh" ]; then
        print_error "install.sh not found in $TARGET_DIR"
        return 1
    fi

    cd "$TARGET_DIR"

    # Export LELAMP_DIR for installer
    export LELAMP_DIR="$TARGET_DIR"
    export LAMP_ID="lelamp"
    export SKIP_REBOOT=true  # Don't reboot yet - oem_install has more steps

    # Run installer with auto-confirm
    bash install.sh -y

    print_success "LeLamp installation complete"
}

# Step 12: Install Piper TTS (for local AI)
install_piper() {
    print_header "Installing Piper TTS"

    # Default to true if not set
    LOCAL_AI="${LOCAL_AI:-true}"

    if [ "$LOCAL_AI" = "false" ]; then
        print_info "LOCAL_AI=false - skipping Piper installation"
        return 0
    fi

    if [ -f "$TARGET_DIR/install/install_piper.sh" ]; then
        print_info "Installing Piper TTS for local voice synthesis..."
        bash "$TARGET_DIR/install/install_piper.sh" -y
        print_success "Piper TTS installed"
    else
        print_warning "Piper installer not found - skipping"
    fi
}

# Step 13: Install Ollama (for local AI)
install_ollama() {
    print_header "Installing Ollama"

    # Default to true if not set
    LOCAL_AI="${LOCAL_AI:-true}"

    if [ "$LOCAL_AI" = "false" ]; then
        print_info "LOCAL_AI=false - skipping Ollama installation"
        return 0
    fi

    if [ -f "$TARGET_DIR/install/install_ollama.sh" ]; then
        print_info "Installing Ollama for local LLM..."
        bash "$TARGET_DIR/install/install_ollama.sh" -y
        print_success "Ollama installed"
    else
        print_warning "Ollama installer not found - skipping"
    fi
}

# Step 14: Create first-boot marker
create_first_boot_marker() {
    print_header "Creating First Boot Configuration"

    # Mark setup as incomplete (will trigger setup wizard)
    local config_file="$HOME/.lelamp/config.yaml"

    # Use venv Python which has PyYAML installed
    local venv_python="$TARGET_DIR/.venv/bin/python"

    if [ -f "$config_file" ]; then
        # Update existing config using venv Python (has PyYAML)
        if [ -x "$venv_python" ]; then
            "$venv_python" << EOF
import yaml
config_path = "$config_file"
with open(config_path, 'r') as f:
    config = yaml.safe_load(f) or {}

config.setdefault('setup', {})
config['setup']['first_boot'] = True
config['setup']['setup_complete'] = False
config['setup']['current_step'] = 'welcome'
config['setup']['oem_provisioned'] = True
config['setup']['oem_serial'] = "$DEVICE_SERIAL"

with open(config_path, 'w') as f:
    yaml.safe_dump(config, f, default_flow_style=False)

print("Config updated for first boot")
EOF
        else
            print_warning "Venv Python not found, using fallback config creation"
            # Fallback: create minimal config without PyYAML
            cat > "$config_file" << EOF
setup:
  first_boot: true
  setup_complete: false
  current_step: welcome
  oem_provisioned: true
  oem_serial: "$DEVICE_SERIAL"
EOF
        fi
    fi

    print_success "First boot configuration created"
}

# Step 15: Register with Hub server
register_with_hub() {
    print_header "Registering with LeLamp Hub"

    if [ -z "$HUB_URL" ]; then
        print_info "HUB_URL not set - skipping registration"
        return 0
    fi

    # Read system info
    local system_info=$(cat "$HOME/.lelamp/system_info.json" 2>/dev/null || echo '{}')

    # Try to register
    print_info "Attempting to register with Hub at $HUB_URL..."

    response=$(curl -s -X POST "$HUB_URL/api/v1/devices/register" \
        -H "Content-Type: application/json" \
        -d "{
            \"serial\": \"$DEVICE_SERIAL\",
            \"hardware_info\": $system_info
        }" --connect-timeout 10 2>/dev/null || echo '{"error": "Hub unreachable"}')

    if echo "$response" | grep -q "device_id\|api_key"; then
        # Extract and store API key
        api_key=$(echo "$response" | grep -o '"api_key":"[^"]*"' | cut -d'"' -f4 || true)
        if [ -n "$api_key" ]; then
            echo "HUB_API_KEY=$api_key" >> "$HOME/.lelamp/.env"
            chmod 600 "$HOME/.lelamp/.env"
            print_success "Device registered with Hub"
        else
            print_success "Device registered (no API key returned)"
        fi
    else
        print_warning "Could not register with Hub (will retry on first boot)"
        print_info "Response: $response"
    fi
}

# Step 16: Create lelamp-ap systemd service
create_ap_service() {
    print_header "Creating AP Auto-Start Service"

    if [ "$SKIP_AP" = "true" ]; then
        print_info "SKIP_AP=true - skipping AP service creation"
        return 0
    fi

    # Create systemd service that starts AP on first boot
    sudo tee /etc/systemd/system/lelamp-ap.service > /dev/null << EOF
[Unit]
Description=LeLamp WiFi AP Mode
After=NetworkManager.service
Wants=NetworkManager.service
ConditionPathExists=!$HOME/.lelamp/.wifi_configured

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/nmcli connection up lelamp-ap
ExecStop=/usr/bin/nmcli connection down lelamp-ap

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable lelamp-ap 2>/dev/null || true

    print_success "AP service created and enabled"
}

# Step 17: Print summary and reboot
print_summary_and_reboot() {
    print_header "OEM Installation Complete!"

    echo ""
    echo "Device Information:"
    echo "  Serial:       $DEVICE_SERIAL"
    echo "  Hostname:     lelamp-${DEVICE_SERIAL_SHORT}"
    echo "  Web UI:       http://lelamp-${DEVICE_SERIAL_SHORT}.local"

    # Only show AP info if AP was configured
    if [ "$SKIP_AP" != "true" ]; then
        echo "  WiFi AP SSID: lelamp_${DEVICE_SERIAL_SHORT}"
        echo "  WiFi AP Pass: lelamp123"
    fi

    # Only show user/password if user was configured
    if [ "$SKIP_USER" != "true" ]; then
        echo "  SSH User:     $(whoami)"
        echo "  SSH Password: lelamp"
    fi

    echo ""
    echo "Installation Directory: $TARGET_DIR"
    echo ""

    # Check WiFi connectivity
    local wifi_connected=false
    local wifi_ssid=""
    if command -v nmcli &> /dev/null; then
        wifi_ssid=$(nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2 2>/dev/null || true)
        if [ -n "$wifi_ssid" ]; then
            wifi_connected=true
        fi
    fi

    echo "Next Steps:"

    if [ "$SKIP_AP" = "true" ]; then
        # No AP mode - check if WiFi is connected
        if [ "$wifi_connected" = "true" ]; then
            echo "  1. Device will reboot"
            echo "  2. Access via: http://lelamp-${DEVICE_SERIAL_SHORT}.local"
            echo "  3. Or SSH: ssh $(whoami)@lelamp-${DEVICE_SERIAL_SHORT}.local"
        else
            echo ""
            echo -e "  ${YELLOW}⚠ WARNING: No WiFi network connected!${NC}"
            echo ""
            echo "  Before rebooting, configure WiFi:"
            echo -e "  ${CYAN}sudo nmtui${NC}"
            echo ""
            echo "  Or connect via Ethernet after reboot."
        fi
    else
        # AP mode configured
        echo "  1. Device will reboot into AP mode"
        echo "  2. Connect to WiFi: lelamp_${DEVICE_SERIAL_SHORT}"
        echo "  3. Open http://192.168.4.1 in browser"
        echo "  4. Complete setup wizard"
    fi
    echo ""

    log "=== OEM Installation Complete ==="
    log "Serial: $DEVICE_SERIAL"
    log "Hostname: lelamp-${DEVICE_SERIAL_SHORT}"

    if [ "$SKIP_REBOOT" = "true" ]; then
        print_warning "SKIP_REBOOT=true - not rebooting"
        print_info "Run 'sudo reboot' when ready"
    else
        print_info "Rebooting in 10 seconds... (Ctrl+C to cancel)"
        sleep 10
        sudo reboot
    fi
}

# =============================================================================
# Main Installation Flow
# =============================================================================

main() {
    # First, ensure we're running as the 'lelamp' user
    # This will create the user if needed and exit with instructions
    check_or_create_lelamp_user

    local total_steps=18

    print_step 1 $total_steps "Initializing OEM installation"
    init_oem_install

    print_step 2 $total_steps "Storing device serial"
    store_device_serial

    print_step 3 $total_steps "Setting default credentials"
    set_default_credentials

    print_step 4 $total_steps "Enabling SSH"
    enable_ssh

    print_step 5 $total_steps "Configuring WiFi country"
    configure_wifi_country

    print_step 6 $total_steps "Setting hostname"
    set_hostname

    print_step 7 $total_steps "Cloning repository"
    clone_repository

    print_step 8 $total_steps "Configuring WiFi AP"
    setup_wifi_ap

    print_step 9 $total_steps "Setting up Tailscale"
    setup_tailscale

    print_step 10 $total_steps "Setting up rpi-connect"
    setup_rpi_connect

    print_step 11 $total_steps "Collecting system info"
    collect_system_info

    print_step 12 $total_steps "Running main installer"
    run_main_installer

    print_step 13 $total_steps "Installing Piper TTS"
    install_piper

    print_step 14 $total_steps "Installing Ollama"
    install_ollama

    print_step 15 $total_steps "Creating first boot config"
    create_first_boot_marker

    print_step 16 $total_steps "Registering with Hub"
    register_with_hub

    print_step 17 $total_steps "Creating AP service"
    create_ap_service

    print_step 18 $total_steps "Finalizing"
    print_summary_and_reboot
}

# Run main function
main "$@"
