#!/bin/bash
#
# LeLamp Runtime Installation Script
# For Raspberry Pi 4 and Raspberry Pi 5
#
# This script performs a complete setup of LeLamp Runtime on a fresh RPi.
# Individual components can also be installed separately using scripts in install/
#
# Usage:
#   ./install.sh                    # Full interactive installation
#   ./install.sh --help             # Show help
#   ./install.sh --list             # List available install scripts
#   ./install.sh --component audio  # Run specific component installer
#

set -e

# Detect if running from curl | bash (stdin is a pipe, not a file)
# BASH_SOURCE[0] will be empty or "bash" when piped
if [ -z "${BASH_SOURCE[0]}" ] || [ "${BASH_SOURCE[0]}" = "bash" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
    RUNNING_FROM_REPO=false
    SCRIPT_DIR="$(pwd)"
    INSTALL_DIR="$SCRIPT_DIR/install"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    INSTALL_DIR="$SCRIPT_DIR/install"
    RUNNING_FROM_REPO=true
fi

# Source common functions if available
if [ -f "$INSTALL_DIR/common.sh" ] && [ "$RUNNING_FROM_REPO" = "true" ]; then
    source "$INSTALL_DIR/common.sh"
else
    # Fallback definitions if common.sh not found or running from curl | bash
    RUNNING_FROM_REPO=false

    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'

    print_header() { echo -e "\n${BLUE}============================================${NC}\n${BLUE}$1${NC}\n${BLUE}============================================${NC}\n"; }
    print_success() { echo -e "${GREEN}✓ $1${NC}"; }
    print_error() { echo -e "${RED}✗ $1${NC}"; }
    print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
    print_info() { echo -e "${BLUE}→ $1${NC}"; }

    setup_input_device() {
        if [ -t 0 ]; then
            export INPUT_DEVICE="/dev/stdin"
        elif [ -e /dev/tty ]; then
            export INPUT_DEVICE="/dev/tty"
        else
            export INPUT_DEVICE="/dev/stdin"
            print_warning "Running in non-interactive mode - using defaults where possible"
        fi
    }

    init_script() {
        setup_input_device
    }
fi

# Repository settings
REPO_URL="https://github.com/humancomputerlab/boxbots_lelampruntime.git"
REPO_BRANCH="12Vruntime-agent"
REPO_NAME="boxbots_lelampruntime"

# Script-specific variables
ACTION="install"
COMPONENT=""

show_help() {
    echo "LeLamp Runtime Installation Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --help               Show this help message"
    echo "  --list               List available component installers"
    echo "  --component <NAME>   Run specific component installer"
    echo "  -y, --yes            Skip confirmation prompts"
    echo ""
    echo "Components (can be installed individually):"
    echo "  audio          Audio hardware configuration (ReSpeaker/HaloX)"
    echo "  dependencies   System packages (portaudio, sox, git, etc.)"
    echo "  uv             UV package manager"
    echo "  livekit        LiveKit CLI"
    echo "  raspotify      Spotify Connect"
    echo "  piper          Piper TTS (local text-to-speech)"
    echo "  ollama         Ollama LLM (local language model)"
    echo "  python         Python dependencies"
    echo "  udev           Udev rules for USB devices"
    echo "  gpio           GPIO permissions"
    echo "  env            Environment configuration (.env)"
    echo "  motors         Motor setup and calibration"
    echo "  service        Systemd service"
    echo "  sudoers        Sudoers configuration (passwordless sudo)"
    echo "  frontend       WebUI frontend (optional Node.js for development)"
    echo ""
    echo "Examples:"
    echo "  $0                           # Full installation"
    echo "  $0 --component audio         # Only audio setup"
    echo "  $0 --component motors -y     # Install motors without prompts"
    echo ""
    echo "Individual scripts can be run directly from install/:"
    echo "  ./install/install_audio.sh --choice halox"
    echo "  ./install/install_motors.sh --skip --voltage 12"
    echo ""
}

list_components() {
    print_header "Available Component Installers"

    echo "Run individual components with: $0 --component <name>"
    echo "Or run directly from install/ directory"
    echo ""

    for script in "$INSTALL_DIR"/install_*.sh; do
        if [ -f "$script" ]; then
            local name
            name=$(basename "$script" .sh | sed 's/install_//')
            printf "  %-15s %s\n" "$name" "$script"
        fi
    done

    echo ""
    echo "Get help for any component: ./install/install_<name>.sh --help"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --list)
                list_components
                exit 0
                ;;
            --component)
                COMPONENT="$2"
                ACTION="component"
                shift 2
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

# Run a specific component installer
run_component() {
    local component="$1"
    shift

    local script="$INSTALL_DIR/install_${component}.sh"

    if [ ! -f "$script" ]; then
        print_error "Component installer not found: $script"
        print_info "Run '$0 --list' to see available components"
        exit 1
    fi

    # Pass remaining args to the component script
    if [ "$SKIP_CONFIRM" = "true" ]; then
        bash "$script" -y "$@"
    else
        bash "$script" "$@"
    fi
}

# Detect Raspberry Pi model
detect_rpi_model() {
    if [ ! -f /proc/device-tree/model ]; then
        print_warning "This doesn't appear to be a Raspberry Pi"
        print_warning "Continuing anyway, but hardware features may not work correctly"
        RPI_MODEL="Unknown"
        return
    fi

    MODEL=$(cat /proc/device-tree/model)

    if echo "$MODEL" | grep -q "Raspberry Pi 5"; then
        RPI_MODEL="5"
        print_success "Detected Raspberry Pi 5"
    elif echo "$MODEL" | grep -q "Raspberry Pi 4"; then
        RPI_MODEL="4"
        print_success "Detected Raspberry Pi 4"
    else
        print_warning "Detected: $MODEL"
        print_warning "This script is designed for RPi 4 or 5, but will continue"
        RPI_MODEL="Other"
    fi
}

# Check platform
check_platform() {
    print_header "Checking Platform"

    # Auto-detect from /proc/device-tree/model
    local detected=""

    if [ -f /proc/device-tree/model ]; then
        local model_str
        model_str=$(tr -d '\0' < /proc/device-tree/model)
        if echo "$model_str" | grep -q "Raspberry Pi 5"; then
            detected="5"
        elif echo "$model_str" | grep -q "Raspberry Pi 4"; then
            detected="4"
        fi
    fi

    # If detected, use it automatically
    if [ "$detected" = "5" ]; then
        RPI_MODEL="5"
        print_success "Detected Raspberry Pi 5"
        return
    elif [ "$detected" = "4" ]; then
        RPI_MODEL="4"
        print_success "Detected Raspberry Pi 4"
        return
    fi

    # Detection failed - prompt user
    print_warning "Could not auto-detect Raspberry Pi model"
    echo "Select your Raspberry Pi model:"
    echo "  1) Raspberry Pi 4"
    echo "  2) Raspberry Pi 5"

    read -p "Enter choice [1-2]: " model_choice < "$INPUT_DEVICE"

    case $model_choice in
        1)
            RPI_MODEL="4"
            print_success "Using Raspberry Pi 4 configuration"
            ;;
        2)
            RPI_MODEL="5"
            print_success "Using Raspberry Pi 5 configuration"
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
}

# Update system
update_system() {
    print_header "Updating System Packages"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Update system packages?" "y"; then
            print_info "Skipping system update"
            return
        fi
    fi

    print_info "This may take a few minutes..."
    sudo apt-get update
    sudo apt-get upgrade -y
    print_success "System updated"
}

# Fix locale issues
fix_locale() {
    print_header "Fixing Locale Settings"

    if locale 2>&1 | grep -q "Cannot set LC_"; then
        print_info "Locale issues detected, fixing..."
        sudo apt-get install -y locales
        sudo sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen
        sudo locale-gen en_US.UTF-8
        sudo update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
        export LANG=en_US.UTF-8
        export LC_ALL=en_US.UTF-8
        print_success "Locale fixed (en_US.UTF-8)"
    else
        print_success "Locale is already configured correctly"
    fi
}

# Print final instructions
print_final_instructions() {
    print_header "Installation Complete!"

    print_success "LeLamp Runtime has been installed successfully"

    echo -e "\n${GREEN}Installation Summary:${NC}"
    echo "  - Raspberry Pi Model: $RPI_MODEL"
    echo "  - Installation Directory: $TARGET_DIR"

    echo -e "\n${YELLOW}Next Steps:${NC}"
    echo "  1. Reload your shell or run: source ~/.bashrc"
    echo "  2. Navigate to: cd $TARGET_DIR"
    echo "  3. Configure .env file if not done (see .env.example)"
    echo "  4. Start the voice agent: uv run python main.py"

    echo -e "\n${BLUE}Useful Commands:${NC}"
    echo "  (run from $TARGET_DIR)"
    echo "  - Find motor port: uv run lerobot-find-port"
    echo "  - Setup motors: ./install/install_motors.sh"
    echo "  - Calibrate motors: uv run -m lelamp.calibrate"
    echo "  - Test motors: uv run -m lelamp.test.test_motors"
    echo "  - Test audio: uv run -m lelamp.test.test_audio"
    echo "  - Test RGB: uv run -m lelamp.test.test_rgb"
    echo "  - Run voice agent: uv run python main.py"

    echo -e "\n${BLUE}Systemd Service:${NC}"
    echo "  - Start:   sudo systemctl start lelamp.service"
    echo "  - Stop:    sudo systemctl stop lelamp.service"
    echo "  - Status:  sudo systemctl status lelamp.service"
    echo "  - Logs:    sudo journalctl -u lelamp.service -f"

    echo -e "\n${BLUE}Individual Installers:${NC}"
    echo "  Re-run any component: ./install.sh --component <name>"
    echo "  Or directly: ./install/install_<name>.sh"
    echo ""
    echo "  Available: audio, dependencies, uv, livekit, raspotify, piper,"
    echo "             ollama, python, udev, gpio, env, motors, service"

    echo -e "\n${BLUE}Audio Hardware Reconfiguration:${NC}"
    echo "  ./install/install_audio.sh --choice respeaker-v1"
    echo "  ./install/install_audio.sh --choice respeaker-v2"
    echo "  ./install/install_audio.sh --choice halox"
    echo "  ./install/install_audio.sh --choice auto"

    echo -e "\n${YELLOW}Troubleshooting:${NC}"
    echo "  - If UV commands don't work: source ~/.bashrc"
    echo "  - Audio not working: ./install/install_audio.sh"
    echo "  - GPIO errors: ./install/install_gpio.sh --check"
    echo "  - Serial port errors: ./install/install_udev.sh"

    echo ""
}

# Prompt for reboot
prompt_reboot() {
    # Skip if SKIP_REBOOT is set (used by oem_install.sh)
    if [ "$SKIP_REBOOT" = "true" ]; then
        print_info "Skipping reboot (SKIP_REBOOT=true)"
        return 0
    fi

    print_header "Installation Complete - Reboot Required"

    echo -e "${YELLOW}Important: A reboot is required for the following changes to take effect:${NC}"
    echo "  - User group changes (dialout, gpio, video)"
    echo "  - Udev rules for USB devices and GPIO"
    echo "  - Audio hardware configuration (ReSpeaker/HaloX overlays)"
    echo "  - System updates and new packages"
    echo ""

    read -p "Do you want to reboot now? [Y/n]: " reboot_now < "$INPUT_DEVICE"

    if [[ ! $reboot_now =~ ^[Nn]$ ]]; then
        print_info "Rebooting in 5 seconds... (Ctrl+C to cancel)"
        sleep 5
        sudo reboot
    else
        print_warning "Please reboot your system manually before running LeLamp"
        print_info "Run: sudo reboot"
    fi
}

# Clone repository and re-run installer from there
clone_and_rerun() {
    print_header "Cloning Repository"

    TARGET_DIR="$HOME/$REPO_NAME"

    # Install git if not available (must be first!)
    if ! command -v git &> /dev/null; then
        print_info "Installing git..."
        sudo apt-get update
        sudo apt-get install -y git
    fi

    # Check if directory already exists
    if [ -d "$TARGET_DIR" ]; then
        print_warning "Directory $TARGET_DIR already exists"
        # Use /dev/tty directly for curl | bash compatibility
        read -p "Remove and re-clone? [y/N]: " remove_existing < /dev/tty
        if [[ $remove_existing =~ ^[Yy]$ ]]; then
            print_info "Removing existing directory..."
            rm -rf "$TARGET_DIR"
        else
            print_info "Using existing repository"
            cd "$TARGET_DIR"
            print_info "Pulling latest changes..."
            git fetch origin
            git checkout "$REPO_BRANCH"
            git pull origin "$REPO_BRANCH"
            print_success "Repository updated"

            # Re-run the installer from the cloned repo
            print_info "Running installer from cloned repository..."
            exec bash "$TARGET_DIR/install.sh" "$@"
        fi
    fi

    # Clone the repository
    print_info "Cloning $REPO_URL (branch: $REPO_BRANCH)..."
    git clone -b "$REPO_BRANCH" "$REPO_URL" "$TARGET_DIR"
    print_success "Repository cloned to $TARGET_DIR"

    # Re-run the installer from the cloned repo
    print_info "Running installer from cloned repository..."
    exec bash "$TARGET_DIR/install.sh" "$@"
}

# Main installation flow
main() {
    print_header "LeLamp Runtime Installation"
    echo "This script will set up LeLamp Runtime on your Raspberry Pi"
    echo ""
    echo "Individual components can also be installed separately."
    echo "Run '$0 --list' to see available component installers."
    echo ""

    # Initialize input device
    init_script

    # If running from curl | bash, we need to clone the repo first
    if [ "$RUNNING_FROM_REPO" = "false" ]; then
        print_info "Cloning repository first..."
        clone_and_rerun "$@"
        exit 0  # Should not reach here due to exec
    fi

    # Store target directory globally (use the repo directory name)
    TARGET_DIR="$SCRIPT_DIR"
    export LELAMP_DIR="$TARGET_DIR"

    # Step 1: Platform detection
    check_platform

    # Set lamp ID (always "lelamp")
    export LAMP_ID="lelamp"

    # Step 2: Sudoers configuration (early - enables passwordless sudo for rest of install)
    print_header "Step 2: Sudoers Configuration"
    run_component "sudoers"

    # Step 3: System update
    update_system

    # Step 4: Fix locale
    fix_locale

    # Step 5: System dependencies
    print_header "Step 5: System Dependencies"
    run_component "dependencies"

    # Step 6: UV package manager
    print_header "Step 6: UV Package Manager"
    run_component "uv"

    # Step 7: LiveKit CLI
    print_header "Step 7: LiveKit CLI"
    run_component "livekit"

    # Step 8: Python dependencies
    print_header "Step 8: Python Dependencies"
    run_component "python"

    # Step 9: Audio hardware configuration
    print_header "Step 9: Audio Hardware"
    run_component "audio"

    # Step 10: GPIO permissions (udev rules for GPIO)
    print_header "Step 10: GPIO Permissions"
    run_component "gpio"

    # Step 11: Udev rules (camera, motor - reloads all udev rules)
    print_header "Step 11: Udev Rules"
    run_component "udev"

    # Step 12: Motor setup (optional)
    print_header "Step 12: Motor Setup (Optional)"
    run_component "motors"

    # Step 13: Raspotify (optional) - after audio so we know which device to use
    print_header "Step 13: Raspotify (Spotify Connect)"
    run_component "raspotify"

    # Step 14: Systemd service (optional)
    print_header "Step 14: Systemd Service"
    run_component "service"

    # Step 15: Frontend check (optional Node.js for development)
    print_header "Step 15: Frontend WebUI"
    run_component "frontend"

    # Step 16: Environment configuration (last - needs API keys)
    print_header "Step 16: Environment Configuration"
    run_component "env"

    # Final instructions
    print_final_instructions

    # Prompt for reboot
    prompt_reboot
}

# Parse command line arguments
parse_args "$@"

# Execute based on action
case $ACTION in
    install)
        main
        ;;
    component)
        run_component "$COMPONENT"
        ;;
esac
