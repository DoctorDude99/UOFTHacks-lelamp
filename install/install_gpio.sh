#!/bin/bash
#
# install_gpio.sh - Setup GPIO permissions for RGB LEDs
#
# Configures:
#   - GPIO udev rules for non-root access
#   - User group memberships (gpio, dialout, video)
#   - Python capabilities for /dev/mem access
#
# Usage:
#   ./install_gpio.sh              # Interactive
#   ./install_gpio.sh -y           # Install without prompting
#   ./install_gpio.sh --udev       # Only setup udev rules
#   ./install_gpio.sh --groups     # Only setup user groups
#   ./install_gpio.sh --caps       # Only setup Python capabilities
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"

show_help() {
    echo "LeLamp GPIO Permissions Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --udev               Only setup GPIO udev rules"
    echo "  --groups             Only setup user groups"
    echo "  --caps               Only setup Python capabilities"
    echo "  --check              Check current permissions"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --udev)
                ACTION="udev"
                shift
                ;;
            --groups)
                ACTION="groups"
                shift
                ;;
            --caps)
                ACTION="caps"
                shift
                ;;
            --check)
                ACTION="check"
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

# Check current permissions
check_permissions() {
    print_header "GPIO Permissions Status"

    # Check groups
    print_info "User groups:"
    local current_groups
    current_groups=$(groups $USER)
    echo "  $current_groups"

    if echo "$current_groups" | grep -q gpio; then
        print_success "  User is in 'gpio' group"
    else
        print_warning "  User is NOT in 'gpio' group"
    fi

    if echo "$current_groups" | grep -q dialout; then
        print_success "  User is in 'dialout' group"
    else
        print_warning "  User is NOT in 'dialout' group"
    fi

    if echo "$current_groups" | grep -q video; then
        print_success "  User is in 'video' group"
    else
        print_warning "  User is NOT in 'video' group"
    fi

    # Check udev rules
    print_info "GPIO udev rules:"
    if [ -f /etc/udev/rules.d/99-gpio.rules ]; then
        print_success "  /etc/udev/rules.d/99-gpio.rules exists"
    else
        print_warning "  /etc/udev/rules.d/99-gpio.rules not found"
    fi

    # Check Python capabilities
    LELAMP_DIR=$(get_lelamp_dir)
    if [ -d "$LELAMP_DIR/.venv" ]; then
        local python_path
        python_path=$(readlink -f "$LELAMP_DIR/.venv/bin/python3")
        print_info "Python capabilities:"
        if getcap "$python_path" 2>/dev/null | grep -q cap_sys_rawio; then
            print_success "  cap_sys_rawio is set on Python"
        else
            print_warning "  cap_sys_rawio is NOT set on Python"
        fi
    fi
}

# Setup GPIO udev rules
setup_gpio_udev() {
    print_header "GPIO Udev Rules Setup"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This creates udev rules for GPIO and memory access."
        echo "Required for RGB LED control without running as root."
        echo ""
        if ! ask_yes_no "Setup GPIO udev rules?" "y"; then
            print_info "Skipping GPIO udev rules"
            return 0
        fi
    fi

    GPIO_UDEV_FILE="/etc/udev/rules.d/99-gpio.rules"
    print_info "Creating GPIO udev rules at $GPIO_UDEV_FILE..."

    if sudo tee $GPIO_UDEV_FILE > /dev/null << 'EOF'
SUBSYSTEM=="mem", KERNEL=="mem", GROUP="gpio", MODE="0660"
SUBSYSTEM=="gpio", GROUP="gpio", MODE="0660"
EOF
    then
        print_success "GPIO udev rules created"

        # Reload udev rules
        sudo udevadm control --reload-rules
        sudo udevadm trigger
    else
        print_error "Failed to create GPIO udev rules"
        return 1
    fi
}

# Setup user groups
setup_user_groups() {
    print_header "User Group Configuration"

    print_info "Adding user to required groups..."

    # Add to dialout group for serial port access
    if ! groups $USER | grep -q dialout; then
        sudo usermod -a -G dialout $USER
        print_success "Added $USER to 'dialout' group (for USB serial access)"
    else
        print_info "User already in 'dialout' group"
    fi

    # Add to gpio group for GPIO access
    if ! groups $USER | grep -q gpio; then
        sudo usermod -a -G gpio $USER
        print_success "Added $USER to 'gpio' group (for RGB LED access)"
    else
        print_info "User already in 'gpio' group"
    fi

    # Add to video group for camera access
    if ! groups $USER | grep -q video; then
        sudo usermod -a -G video $USER
        print_success "Added $USER to 'video' group (for camera access)"
    else
        print_info "User already in 'video' group"
    fi

    print_success "User groups configured"
    print_warning "Note: Group changes will take effect after logout/login or reboot"
}

# Setup Python capabilities
setup_python_caps() {
    print_header "Python GPIO Capabilities"

    LELAMP_DIR=$(get_lelamp_dir)

    if [ ! -d "$LELAMP_DIR/.venv" ]; then
        print_warning "Virtual environment not found at $LELAMP_DIR/.venv"
        print_info "Run Python dependencies installation first"
        print_info "You can set capabilities later with:"
        print_info "  sudo setcap 'cap_sys_rawio=ep' \$(readlink -f .venv/bin/python3)"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This grants GPIO memory access to Python."
        echo "Required for RGB LED control without running as root."
        echo ""
        if ! ask_yes_no "Grant Python GPIO capabilities?" "y"; then
            print_info "Skipping Python capability setup"
            return 0
        fi
    fi

    local python_path
    python_path=$(readlink -f "$LELAMP_DIR/.venv/bin/python3")

    print_info "Granting cap_sys_rawio capability to: $python_path"

    if sudo setcap 'cap_sys_rawio=ep' "$python_path"; then
        print_success "Python GPIO capabilities configured"
    else
        print_error "Failed to set Python capabilities"
        return 1
    fi
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            setup_gpio_udev
            setup_user_groups
            setup_python_caps
            ;;
        udev)
            setup_gpio_udev
            ;;
        groups)
            setup_user_groups
            ;;
        caps)
            setup_python_caps
            ;;
        check)
            check_permissions
            ;;
    esac
}

# Run main function
main "$@"
