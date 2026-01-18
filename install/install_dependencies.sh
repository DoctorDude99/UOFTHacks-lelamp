#!/bin/bash
#
# install_dependencies.sh - Install system dependencies for LeLamp
#
# Installs: portaudio, sox, mpg123, alsa-utils, git, git-lfs, build-essential, jq
#
# Usage:
#   ./install_dependencies.sh              # Interactive
#   ./install_dependencies.sh -y           # Install without prompting
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

show_help() {
    echo "LeLamp System Dependencies Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Installs the following packages:"
    echo "  - portaudio19-dev    Audio I/O library"
    echo "  - sox, libsox-fmt-mp3, mpg123    Audio tools"
    echo "  - alsa-utils         ALSA sound utilities"
    echo "  - git, git-lfs       Version control"
    echo "  - build-essential    Compiler tools"
    echo "  - python3-dev        Python development headers"
    echo "  - jq                 JSON processing"
    echo "  - i2c-tools          I2C utilities (for ReSpeaker)"
    echo "  - swig               SWIG interface generator (for lgpio)"
    echo "  - liblgpio-dev       GPIO library for Raspberry Pi 5"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
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

# Install system dependencies
install_dependencies() {
    print_header "Installing System Dependencies"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will install system packages required for LeLamp."
        echo ""
        if ! ask_yes_no "Install system packages?" "y"; then
            print_info "Skipping dependency installation"
            return 0
        fi
    fi

    print_info "Updating package lists..."
    sudo apt-get update

    print_info "Installing portaudio19-dev for audio support..."
    sudo apt-get install -y portaudio19-dev

    print_info "Installing audio tools (sox, libsox-fmt-mp3, mpg123)..."
    sudo apt-get install -y sox libsox-fmt-mp3 mpg123 alsa-utils

    print_info "Installing git and git-lfs..."
    sudo apt-get install -y git git-lfs

    print_info "Installing build essentials..."
    sudo apt-get install -y build-essential python3-dev

    print_info "Installing jq for JSON processing..."
    sudo apt-get install -y jq

    print_info "Installing i2c-tools for hardware detection..."
    sudo apt-get install -y i2c-tools

    print_info "Installing swig for lgpio Python bindings..."
    sudo apt-get install -y swig

    print_info "Installing lgpio library for GPIO access..."
    sudo apt-get install -y liblgpio-dev

    print_info "Installing curl for downloads..."
    sudo apt-get install -y curl apt-transport-https

    print_success "System dependencies installed"
}

# Main function
main() {
    init_script
    parse_args "$@"

    install_dependencies
}

# Run main function
main "$@"
