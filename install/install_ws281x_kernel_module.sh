#!/bin/bash
#
# install_ws281x_kernel_module.sh - Build and install ws2811 kernel module for Pi 5
#
# Raspberry Pi 5 requires a kernel module for WS2812/NeoPixel LED control.
# This script builds and installs the module from the rpi_ws281x repository.
#
# ALTERNATIVE: If using SPI method (GPIO 10/MOSI), you may not need this module.
# The SPI method uses the SPI hardware for timing instead of PWM.
#
# Usage:
#   ./install_ws281x_kernel_module.sh           # Full install
#   ./install_ws281x_kernel_module.sh --check   # Check if module is loaded
#   ./install_ws281x_kernel_module.sh --load    # Just load the module
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/common.sh" ]]; then
    source "$SCRIPT_DIR/common.sh"
else
    # Minimal fallback if common.sh not available
    log_info() { echo "[INFO] $1"; }
    log_warn() { echo "[WARN] $1"; }
    log_error() { echo "[ERROR] $1"; }
    log_success() { echo "[OK] $1"; }
fi

BUILD_DIR="/tmp/rpi_ws281x_build"
REPO_URL="https://github.com/jgarff/rpi_ws281x.git"

show_help() {
    echo "WS2811 Kernel Module Installer for Raspberry Pi 5"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check      Check if kernel module is loaded"
    echo "  --load       Load the kernel module (requires prior install)"
    echo "  --unload     Unload the kernel module"
    echo "  --deps       Install build dependencies only"
    echo "  -y, --yes    Non-interactive mode"
    echo "  -h, --help   Show this help"
    echo ""
    echo "This script builds the ws2811 kernel module required for WS2812/NeoPixel"
    echo "LED control on Raspberry Pi 5. Earlier Pi models don't need this."
    echo ""
    echo "Alternative: Use SPI method (GPIO 10) which doesn't require the kernel module."
}

check_pi5() {
    if [[ -f /proc/device-tree/model ]]; then
        model=$(cat /proc/device-tree/model | tr '[:upper:]' '[:lower:]')
        if [[ "$model" == *"raspberry pi 5"* ]]; then
            return 0
        fi
    fi
    return 1
}

check_module_loaded() {
    if lsmod | grep -q "ws2811"; then
        return 0
    fi
    return 1
}

check_dependencies() {
    local missing=()

    for cmd in git cmake make gcc; do
        if ! command -v $cmd &> /dev/null; then
            missing+=("$cmd")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        return 1
    fi
    return 0
}

install_dependencies() {
    log_info "Installing build dependencies..."
    sudo apt update
    sudo apt install -y \
        git \
        cmake \
        build-essential \
        pkg-config \
        libsystemd-dev
    log_success "Dependencies installed"
}

clone_repo() {
    log_info "Cloning rpi_ws281x repository..."

    # Clean up any previous build
    if [[ -d "$BUILD_DIR" ]]; then
        rm -rf "$BUILD_DIR"
    fi

    git clone "$REPO_URL" "$BUILD_DIR"
    log_success "Repository cloned to $BUILD_DIR"
}

build_module() {
    log_info "Building ws2811 kernel module..."

    cd "$BUILD_DIR"
    mkdir -p build
    cd build

    cmake ..
    make -j$(nproc)

    log_success "Build complete"
}

install_module() {
    log_info "Installing ws2811 kernel module..."

    cd "$BUILD_DIR/build"
    sudo make install

    # Update library cache
    sudo ldconfig

    log_success "Module installed"
}

load_module() {
    log_info "Loading ws2811 kernel module..."

    if check_module_loaded; then
        log_info "Module already loaded"
        return 0
    fi

    sudo modprobe ws2811 || {
        log_warn "modprobe failed, trying insmod..."
        # Find the module file
        local module_path=$(find /lib/modules -name "ws2811.ko*" 2>/dev/null | head -1)
        if [[ -n "$module_path" ]]; then
            sudo insmod "$module_path"
        else
            log_error "Could not find ws2811.ko module file"
            return 1
        fi
    }

    if check_module_loaded; then
        log_success "Module loaded successfully"
        return 0
    else
        log_error "Failed to load module"
        return 1
    fi
}

unload_module() {
    log_info "Unloading ws2811 kernel module..."

    if ! check_module_loaded; then
        log_info "Module not loaded"
        return 0
    fi

    sudo rmmod ws2811
    log_success "Module unloaded"
}

setup_autoload() {
    log_info "Setting up module to load on boot..."

    # Add to modules-load.d
    echo "ws2811" | sudo tee /etc/modules-load.d/ws2811.conf > /dev/null

    # Add device tree overlay to config.txt
    local config_file="/boot/firmware/config.txt"
    if [[ ! -f "$config_file" ]]; then
        config_file="/boot/config.txt"
    fi

    if [[ -f "$config_file" ]]; then
        if ! grep -q "dtoverlay=ws2811-pwm" "$config_file"; then
            log_info "Adding dtoverlay to $config_file..."
            echo "" | sudo tee -a "$config_file" > /dev/null
            echo "# WS2811/WS2812 LED support for Pi 5" | sudo tee -a "$config_file" > /dev/null
            echo "dtoverlay=ws2811-pwm" | sudo tee -a "$config_file" > /dev/null
            log_success "Device tree overlay added"
        else
            log_info "Device tree overlay already configured"
        fi
    else
        log_warn "Could not find config.txt - manual configuration may be needed"
    fi

    log_success "Autoload configured - module will load on next boot"
}

cleanup() {
    log_info "Cleaning up build files..."
    if [[ -d "$BUILD_DIR" ]]; then
        rm -rf "$BUILD_DIR"
    fi
    log_success "Cleanup complete"
}

# Main
main() {
    local action="install"
    local auto_yes=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check)
                action="check"
                shift
                ;;
            --load)
                action="load"
                shift
                ;;
            --unload)
                action="unload"
                shift
                ;;
            --deps)
                action="deps"
                shift
                ;;
            -y|--yes)
                auto_yes=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Handle quick actions
    case $action in
        check)
            echo "Raspberry Pi 5: $(check_pi5 && echo 'Yes' || echo 'No')"
            echo "Module loaded:  $(check_module_loaded && echo 'Yes' || echo 'No')"
            exit 0
            ;;
        load)
            load_module
            exit $?
            ;;
        unload)
            unload_module
            exit $?
            ;;
        deps)
            install_dependencies
            exit $?
            ;;
    esac

    # Full install
    echo "========================================"
    echo "WS2811 Kernel Module Installer"
    echo "========================================"
    echo ""

    # Check if Pi 5
    if ! check_pi5; then
        log_warn "This doesn't appear to be a Raspberry Pi 5"
        log_info "Earlier Pi models don't need the kernel module"
        if [[ "$auto_yes" != true ]]; then
            read -p "Continue anyway? [y/N] " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 0
            fi
        fi
    fi

    # Check if already loaded
    if check_module_loaded; then
        log_success "ws2811 kernel module is already loaded!"
        exit 0
    fi

    # Confirm installation
    if [[ "$auto_yes" != true ]]; then
        echo "This will:"
        echo "  1. Install build dependencies (git, cmake, build-essential)"
        echo "  2. Clone and build the rpi_ws281x repository"
        echo "  3. Install the ws2811 kernel module"
        echo "  4. Configure the module to load on boot"
        echo ""
        read -p "Continue? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi
    fi

    # Run installation steps
    if ! check_dependencies; then
        install_dependencies
    fi

    clone_repo
    build_module
    install_module
    load_module
    setup_autoload
    cleanup

    echo ""
    log_success "Installation complete!"
    echo ""
    echo "The ws2811 kernel module is now loaded and will load automatically on boot."
    echo ""
    echo "You can verify with:"
    echo "  lsmod | grep ws2811"
    echo ""
    echo "If using PWM pins (GPIO 12, 13, 18, 19), LEDs should work now."
    echo "If using SPI (GPIO 10), make sure SPI is enabled in raspi-config."
}

main "$@"
