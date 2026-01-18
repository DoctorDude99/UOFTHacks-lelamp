#!/bin/bash
#
# install_mediapipe.sh - Install MediaPipe for advanced face tracking
#
# MediaPipe provides better face tracking with head pose estimation.
# Requires Python 3.8-3.12 (not compatible with Python 3.13+)
#
# Usage:
#   ./install_mediapipe.sh              # Interactive
#   ./install_mediapipe.sh -y           # Install without prompting
#   ./install_mediapipe.sh --check      # Check if MediaPipe is installed
#   ./install_mediapipe.sh --uninstall  # Remove MediaPipe
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"

show_help() {
    echo "LeLamp MediaPipe Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check              Check if MediaPipe is installed"
    echo "  --uninstall          Remove MediaPipe"
    echo "  --force              Force reinstall even if already installed"
    show_help_footer
    echo "Notes:"
    echo "  - MediaPipe requires Python 3.8-3.12"
    echo "  - If installation fails, OpenCV face tracking will be used instead"
    echo "  - Set 'engine: mediapipe' in config.yaml to use MediaPipe"
    echo ""
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check)
                ACTION="check"
                shift
                ;;
            --uninstall|--remove)
                ACTION="uninstall"
                shift
                ;;
            --force)
                FORCE_INSTALL=true
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

# Check Python version compatibility (uses venv Python if available)
check_python_version() {
    local python_version
    local python_cmd="python3"

    # Use venv Python if available
    if [ -d "$LELAMP_DIR/.venv" ] && [ -x "$LELAMP_DIR/.venv/bin/python3" ]; then
        python_cmd="$LELAMP_DIR/.venv/bin/python3"
    fi

    python_version=$($python_cmd --version 2>&1 | cut -d' ' -f2)
    local major minor

    major=$(echo "$python_version" | cut -d. -f1)
    minor=$(echo "$python_version" | cut -d. -f2)

    print_info "Python version (venv): $python_version"

    if [ "$major" -eq 3 ] && [ "$minor" -ge 8 ] && [ "$minor" -le 12 ]; then
        print_success "Python version is compatible with MediaPipe (3.8-3.12)"
        return 0
    else
        print_warning "Python $python_version may not be compatible with MediaPipe"
        print_info "MediaPipe requires Python 3.8-3.12"
        return 1
    fi
}

# Check if MediaPipe is installed
check_mediapipe() {
    print_info "Checking MediaPipe installation..."

    cd "$LELAMP_DIR"

    if [ -d ".venv" ]; then
        if .venv/bin/python3 -c "import mediapipe" 2>/dev/null; then
            local version
            version=$(.venv/bin/python3 -c "import mediapipe; print(mediapipe.__version__)" 2>/dev/null)
            print_success "MediaPipe is installed (version $version)"
            return 0
        else
            print_info "MediaPipe is not installed"
            return 1
        fi
    else
        print_warning "Virtual environment not found at $LELAMP_DIR/.venv"
        return 1
    fi
}

# Install MediaPipe
install_mediapipe() {
    print_header "Installing MediaPipe"

    cd "$LELAMP_DIR"

    # Check if already installed
    if check_mediapipe && [ "$FORCE_INSTALL" != "true" ]; then
        print_info "MediaPipe is already installed. Use --force to reinstall."
        return 0
    fi

    # Check Python version
    if ! check_python_version; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "Python version may not be compatible. Try anyway?"; then
                print_info "Skipping MediaPipe installation"
                return 1
            fi
        else
            print_warning "Attempting installation despite Python version mismatch"
        fi
    fi

    # Check for virtual environment
    if [ ! -d ".venv" ]; then
        print_error "Virtual environment not found at $LELAMP_DIR/.venv"
        print_info "Please run the Python dependencies installation first"
        return 1
    fi

    # Check for UV
    if ! command_exists uv; then
        print_error "UV package manager not found"
        print_info "Please install UV first: ./install/install_uv.sh"
        return 1
    fi

    print_info "Installing MediaPipe..."

    # Attempt installation
    if uv pip install mediapipe 2>&1 | tee /tmp/mediapipe_install.log; then
        print_success "MediaPipe installed successfully"
        print_info "Set 'engine: mediapipe' in config.yaml to use it"
        rm -f /tmp/mediapipe_install.log
        return 0
    else
        # Check if it's a Python version issue
        if grep -q "No matching distribution found" /tmp/mediapipe_install.log 2>/dev/null; then
            print_error "MediaPipe installation failed - Python version incompatible"
            print_info "MediaPipe requires Python 3.8-3.12"
            print_info "You can still use OpenCV for face tracking (set 'engine: opencv' in config.yaml)"
        else
            print_error "MediaPipe installation failed"
            print_info "Check /tmp/mediapipe_install.log for details"
        fi
        return 1
    fi
}

# Uninstall MediaPipe
uninstall_mediapipe() {
    print_header "Uninstalling MediaPipe"

    cd "$LELAMP_DIR"

    if [ ! -d ".venv" ]; then
        print_error "Virtual environment not found"
        return 1
    fi

    if ! check_mediapipe; then
        print_info "MediaPipe is not installed"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        if ! ask_yes_no "Are you sure you want to uninstall MediaPipe?"; then
            print_info "Cancelled"
            return 0
        fi
    fi

    print_info "Uninstalling MediaPipe..."

    if uv pip uninstall mediapipe -y; then
        print_success "MediaPipe uninstalled"
        print_info "Face tracking will use OpenCV (Haar Cascade) engine"
    else
        print_error "Failed to uninstall MediaPipe"
        return 1
    fi
}

# Main function
main() {
    init_script
    parse_args "$@"

    # Get LELAMP_DIR
    LELAMP_DIR=$(get_lelamp_dir)

    if [ ! -d "$LELAMP_DIR" ]; then
        print_error "LeLamp directory not found: $LELAMP_DIR"
        print_info "Set LELAMP_DIR environment variable or run from install directory"
        exit 1
    fi

    case $ACTION in
        install)
            if [ "$SKIP_CONFIRM" != "true" ]; then
                print_header "MediaPipe Installation"
                echo "MediaPipe provides advanced face tracking with head pose estimation."
                echo ""
                echo "Requirements:"
                echo "  - Python 3.8-3.12 (not compatible with Python 3.13+)"
                echo "  - Virtual environment at $LELAMP_DIR/.venv"
                echo ""
                check_python_version
                echo ""

                if ! ask_yes_no "Install MediaPipe?" "n"; then
                    print_info "Skipping MediaPipe installation"
                    print_info "Face tracking will use OpenCV (Haar Cascade) engine"
                    exit 0
                fi
            fi
            install_mediapipe
            ;;
        check)
            check_mediapipe
            ;;
        uninstall)
            uninstall_mediapipe
            ;;
    esac
}

# Run main function
main "$@"
