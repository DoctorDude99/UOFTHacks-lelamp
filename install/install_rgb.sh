#!/bin/bash
#
# LeLamp - RGB LED Installation Script
#
# Installs the appropriate rpi-ws281x library and dependencies
# based on the detected Raspberry Pi model.
#
# Usage:
#   ./install_rgb.sh                    # Auto-detect and install
#   ./install_rgb.sh --check            # Check current status
#   ./install_rgb.sh --pi4              # Force Pi 4 installation
#   ./install_rgb.sh --pi5              # Force Pi 5 installation
#   ./install_rgb.sh --test             # Test RGB LEDs
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common functions
if [ -f "$SCRIPT_DIR/common.sh" ]; then
    source "$SCRIPT_DIR/common.sh"
else
    # Fallback definitions
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
fi

# =============================================================================
# Helper Functions
# =============================================================================

detect_pi_version() {
    if [ ! -f /proc/device-tree/model ]; then
        echo "0"
        return
    fi

    local model=$(cat /proc/device-tree/model)

    if echo "$model" | grep -q "Pi 5"; then
        echo "5"
    elif echo "$model" | grep -q "Pi 4"; then
        echo "4"
    elif echo "$model" | grep -q "Pi 3"; then
        echo "3"
    elif echo "$model" | grep -q "Pi"; then
        echo "4"  # Assume Pi 4 compatibility for older models
    else
        echo "0"
    fi
}

get_memory_mb() {
    local mem_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    echo $((mem_kb / 1024))
}

check_rpi_ws281x_version() {
    # Check installed version of rpi-ws281x
    if command -v python3 &> /dev/null; then
        python3 -c "import rpi_ws281x; print(rpi_ws281x.__version__ if hasattr(rpi_ws281x, '__version__') else 'unknown')" 2>/dev/null || echo "not_installed"
    else
        echo "no_python"
    fi
}

check_kernel_module() {
    # Check if ws2811 kernel module is loaded (Pi 5 requirement)
    if lsmod | grep -q "ws2811"; then
        return 0
    fi
    return 1
}

check_dtoverlay() {
    # Check if ws2811-pwm overlay is loaded
    if [ -f /proc/device-tree/ws2811@* ] 2>/dev/null; then
        return 0
    fi
    # Alternative check via dtoverlay command
    if command -v dtoverlay &> /dev/null; then
        if dtoverlay -l 2>/dev/null | grep -q "ws2811"; then
            return 0
        fi
    fi
    return 1
}

# =============================================================================
# Installation Functions
# =============================================================================

install_pi4() {
    print_header "Installing RGB Support for Raspberry Pi 4"

    print_info "Installing rpi-ws281x (PWM/DMA driver)..."

    # Check if we're in a virtual environment
    if [ -n "$VIRTUAL_ENV" ] || [ -f ".venv/bin/python" ]; then
        print_info "Using virtual environment..."
        if [ -f ".venv/bin/pip" ]; then
            .venv/bin/pip install "rpi-ws281x>=5.0.0"
        else
            pip install "rpi-ws281x>=5.0.0"
        fi
    else
        pip3 install "rpi-ws281x>=5.0.0"
    fi

    print_success "rpi-ws281x installed for Pi 4"

    # Check if user is in gpio group
    if ! groups | grep -q gpio; then
        print_warning "Adding user to gpio group..."
        sudo usermod -aG gpio "$USER"
        print_info "You may need to log out and back in for group changes to take effect"
    fi

    print_success "Pi 4 RGB installation complete"
    print_info "Note: Run with sudo for DMA access"
}

install_pi5() {
    print_header "Installing RGB Support for Raspberry Pi 5"

    print_info "Using lgpio driver (no kernel module required)"
    echo ""

    # Install lgpio - simple bitbanging driver that works without kernel modules
    print_info "Installing lgpio..."

    if [ -n "$VIRTUAL_ENV" ] || [ -f ".venv/bin/python" ]; then
        print_info "Using virtual environment..."
        if [ -f ".venv/bin/pip" ]; then
            .venv/bin/pip install lgpio
        else
            pip install lgpio
        fi
    else
        pip3 install lgpio
    fi

    print_success "lgpio installed"

    # Check if user is in gpio group
    if ! groups | grep -q gpio; then
        print_warning "Adding user to gpio group..."
        sudo usermod -aG gpio "$USER"
        print_info "You may need to log out and back in for group changes to take effect"
    fi

    print_success "Pi 5 RGB installation complete"
    echo ""
    print_info "Configuration:"
    echo "  - LED pin: GPIO 10 (default in config.yaml)"
    echo "  - Driver: lgpio (auto-selected for Pi 5)"
    echo "  - No kernel module or reboot required"
}

show_status() {
    print_header "RGB LED Status"

    # Detect Pi version
    local pi_version=$(detect_pi_version)
    local memory_mb=$(get_memory_mb)

    echo "Hardware:"
    if [ "$pi_version" = "5" ]; then
        print_success "  Raspberry Pi 5 detected"
    elif [ "$pi_version" = "4" ]; then
        print_success "  Raspberry Pi 4 detected"
    elif [ "$pi_version" = "3" ]; then
        print_info "  Raspberry Pi 3 detected"
    else
        print_warning "  Unknown platform (Pi version: $pi_version)"
    fi
    echo "  Memory: ${memory_mb}MB"
    echo ""

    echo "Software:"

    # Check lgpio for Pi 5
    if [ "$pi_version" = "5" ]; then
        local lgpio_installed=$(python3 -c "import lgpio; print('yes')" 2>/dev/null || echo "no")
        if [ "$lgpio_installed" = "yes" ]; then
            print_success "  lgpio: Installed"
        else
            print_error "  lgpio: NOT INSTALLED"
            print_info "  Run: pip install lgpio"
        fi
    fi

    # Check rpi-ws281x (for Pi 4 or fallback)
    local ws281x_version=$(check_rpi_ws281x_version)
    if [ "$ws281x_version" = "not_installed" ]; then
        if [ "$pi_version" != "5" ]; then
            print_error "  rpi-ws281x: NOT INSTALLED"
        else
            print_info "  rpi-ws281x: Not installed (not needed with lgpio)"
        fi
    elif [ "$ws281x_version" != "no_python" ]; then
        print_success "  rpi-ws281x: v$ws281x_version"
    fi
    echo ""

    # Pi 5 specific info
    if [ "$pi_version" = "5" ]; then
        echo "Pi 5 Configuration:"
        print_info "  Driver: lgpio (GPIO bitbanging)"
        print_info "  LED Pin: GPIO 10 (configured in config.yaml)"
        print_info "  No kernel module required"
    fi
}

test_rgb() {
    print_header "Testing RGB LEDs"

    print_info "Running RGB test..."

    # Find the project root
    local project_root="$SCRIPT_DIR/.."

    if [ -f "$project_root/.venv/bin/python" ]; then
        cd "$project_root"
        sudo .venv/bin/python -m lelamp.test.test_rgb
    elif [ -f "$project_root/lelamp/test/test_rgb.py" ]; then
        cd "$project_root"
        sudo python3 -m lelamp.test.test_rgb
    else
        print_error "Could not find test_rgb.py"
        print_info "Make sure you're running from the LeLamp project directory"
        return 1
    fi
}

show_help() {
    echo "LeLamp RGB LED Installation Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --help, -h      Show this help message"
    echo "  --check         Check current RGB status (no changes)"
    echo "  --pi4           Force Pi 4 installation"
    echo "  --pi5           Force Pi 5 installation"
    echo "  --test          Run RGB LED test"
    echo "  -y, --yes       Skip confirmation prompts"
    echo ""
    echo "Auto-detection:"
    echo "  If no --pi4 or --pi5 flag is provided, the script will"
    echo "  auto-detect your Raspberry Pi model and install the"
    echo "  appropriate driver."
    echo ""
    echo "Drivers:"
    echo "  Pi 4: rpi-ws281x (PWM/DMA)"
    echo "  Pi 5: lgpio (GPIO bitbanging on pin 10, no kernel module needed)"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    local action="auto"
    local force_pi=""
    local skip_confirm=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --check)
                action="check"
                shift
                ;;
            --pi4)
                force_pi="4"
                shift
                ;;
            --pi5)
                force_pi="5"
                shift
                ;;
            --test)
                action="test"
                shift
                ;;
            -y|--yes)
                skip_confirm=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Handle actions
    case $action in
        check)
            show_status
            exit 0
            ;;
        test)
            test_rgb
            exit $?
            ;;
        auto)
            # Determine Pi version
            local pi_version
            if [ -n "$force_pi" ]; then
                pi_version="$force_pi"
                print_info "Forcing Pi $pi_version installation"
            else
                pi_version=$(detect_pi_version)
                if [ "$pi_version" = "0" ]; then
                    print_error "Could not detect Raspberry Pi version"
                    print_info "Use --pi4 or --pi5 to force installation"
                    exit 1
                fi
                print_success "Detected Raspberry Pi $pi_version"
            fi

            # Confirm installation
            if [ "$skip_confirm" != "true" ]; then
                echo ""
                read -p "Install RGB support for Pi $pi_version? [Y/n]: " confirm
                if [[ $confirm =~ ^[Nn]$ ]]; then
                    print_info "Installation cancelled"
                    exit 0
                fi
            fi

            # Install based on Pi version
            if [ "$pi_version" = "5" ]; then
                install_pi5
            else
                install_pi4
            fi

            echo ""
            show_status
            ;;
    esac
}

main "$@"
