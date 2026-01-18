#!/bin/bash
#
# install_python.sh - Install Python dependencies for LeLamp
#
# Uses UV package manager to install dependencies from pyproject.toml
#
# Usage:
#   ./install_python.sh                     # Interactive
#   ./install_python.sh -y                  # Install without prompting
#   ./install_python.sh --mode hardware     # Install with hardware deps
#   ./install_python.sh --mode minimal      # Install minimal deps
#   ./install_python.sh --check             # Check installation status
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
INSTALL_MODE=""

show_help() {
    echo "LeLamp Python Dependencies Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --mode <MODE>        Installation mode:"
    echo "                         hardware - Include Raspberry Pi hardware deps"
    echo "                         minimal  - Core dependencies only"
    echo "  --check              Check if dependencies are installed"
    echo "  --fix-opencv         Fix OpenCV (ensure headless version)"
    echo "  --set-caps           Set Python capabilities (port 80, RGB LEDs)"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --mode)
                INSTALL_MODE="$2"
                shift 2
                ;;
            --check)
                ACTION="check"
                shift
                ;;
            --fix-opencv)
                ACTION="fix-opencv"
                shift
                ;;
            --set-caps)
                ACTION="set-caps"
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

# Check if dependencies are installed
check_deps() {
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Checking Python dependencies..."

    if [ ! -d ".venv" ]; then
        print_warning "Virtual environment not found at $LELAMP_DIR/.venv"
        return 1
    fi

    # Check a few key packages
    local missing=0

    if .venv/bin/python3 -c "import livekit" 2>/dev/null; then
        print_success "livekit is installed"
    else
        print_warning "livekit is not installed"
        missing=1
    fi

    if .venv/bin/python3 -c "import openai" 2>/dev/null; then
        print_success "openai is installed"
    else
        print_warning "openai is not installed"
        missing=1
    fi

    if .venv/bin/python3 -c "import cv2" 2>/dev/null; then
        print_success "opencv is installed"
    else
        print_warning "opencv is not installed"
        missing=1
    fi

    return $missing
}

# Fix OpenCV installation
fix_opencv() {
    print_header "Fixing OpenCV Installation"

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    if [ ! -d ".venv" ]; then
        print_error "Virtual environment not found"
        return 1
    fi

    print_info "Ensuring headless OpenCV (removing GUI version if present)..."
    uv pip uninstall opencv-python 2>/dev/null || true
    uv pip install --force-reinstall opencv-python-headless

    print_success "OpenCV headless version installed"
}

# Set Python capabilities for privileged operations
set_python_capabilities() {
    print_header "Setting Python Capabilities"

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    if [ ! -d ".venv" ]; then
        print_error "Virtual environment not found"
        return 1
    fi

    # Find the real Python binary (resolve symlinks)
    PYTHON_BIN=$(readlink -f .venv/bin/python3)

    if [ ! -f "$PYTHON_BIN" ]; then
        print_error "Python binary not found: $PYTHON_BIN"
        return 1
    fi

    print_info "Setting capabilities on: $PYTHON_BIN"
    print_info "  - cap_net_bind_service: Allows binding to port 80 without root"
    print_info "  - cap_sys_rawio: Allows access to /dev/mem for RGB LEDs"

    # Set capabilities (requires sudo)
    if sudo setcap 'cap_net_bind_service,cap_sys_rawio=+ep' "$PYTHON_BIN"; then
        print_success "Capabilities set successfully"

        # Verify
        local caps=$(getcap "$PYTHON_BIN" 2>/dev/null)
        if [ -n "$caps" ]; then
            print_info "Verified: $caps"
        fi
    else
        print_warning "Failed to set capabilities (may require manual setup)"
        print_info "Run manually: sudo setcap 'cap_net_bind_service,cap_sys_rawio=+ep' $PYTHON_BIN"
    fi
}

# Install Python dependencies
install_python() {
    print_header "Installing Python Dependencies (uv sync)"

    LELAMP_DIR=$(get_lelamp_dir)

    if [ ! -d "$LELAMP_DIR" ]; then
        print_error "LeLamp directory not found: $LELAMP_DIR"
        return 1
    fi

    cd "$LELAMP_DIR"

    # Check for UV
    if ! command_exists uv; then
        print_error "UV package manager not found"
        print_info "Please run: ./install/install_uv.sh"
        return 1
    fi

    # Determine install mode
    if [ -z "$INSTALL_MODE" ]; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            echo "Choose installation mode:"
            echo "  1) Raspberry Pi with hardware (recommended for RPi) *Default"
            echo "  2) Computer only (no hardware dependencies)"
            read -p "Enter choice [1-2] (default: 1): " mode_choice < "$INPUT_DEVICE"

            # Default to 1 if empty
            if [ -z "$mode_choice" ]; then
                mode_choice="1"
            fi

            case $mode_choice in
                1) INSTALL_MODE="hardware" ;;
                2) INSTALL_MODE="minimal" ;;
                *) print_error "Invalid choice"; return 1 ;;
            esac
        else
            # Default to hardware mode if skipping confirmation
            INSTALL_MODE="hardware"
            print_info "Using default mode: hardware"
        fi
    fi

    # Set environment variables for better installation
    export UV_CONCURRENT_DOWNLOADS=1
    # Skip Git LFS downloads for lerobot test assets (not needed for runtime)
    export GIT_LFS_SKIP_SMUDGE=1

    print_info "Installing Python dependencies (mode: $INSTALL_MODE)..."
    print_warning "This may take 10-20 minutes on Raspberry Pi..."

    case $INSTALL_MODE in
        hardware)
            uv sync --extra hardware
            ;;
        minimal|computer)
            uv sync
            ;;
        *)
            print_error "Unknown install mode: $INSTALL_MODE"
            return 1
            ;;
    esac

    print_success "Python dependencies installed"

    # Fix OpenCV
    fix_opencv

    # Set capabilities for privileged port binding and hardware access
    set_python_capabilities
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            install_python
            ;;
        check)
            check_deps
            ;;
        fix-opencv)
            fix_opencv
            ;;
        set-caps)
            set_python_capabilities
            ;;
    esac
}

# Run main function
main "$@"
