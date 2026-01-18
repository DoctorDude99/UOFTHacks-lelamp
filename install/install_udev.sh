#!/bin/bash
#
# install_udev.sh - Install udev rules for USB devices
#
# Sets up udev rules for:
#   - LeLamp motor controller (/dev/lelamp symlink)
#   - USB cameras
#   - Other USB devices from system/udev/
#
# Usage:
#   ./install_udev.sh                        # Interactive
#   ./install_udev.sh -y                     # Install without prompting
#   ./install_udev.sh --serial-only          # Only setup motor controller
#   ./install_udev.sh --cameras-only         # Only setup camera rules
#   ./install_udev.sh --detect               # Detect USB serial device
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
SERIAL_NUMBER=""

show_help() {
    echo "LeLamp Udev Rules Installation"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --serial-only        Only setup motor controller symlink"
    echo "  --cameras-only       Only setup camera udev rules"
    echo "  --serial <NUM>       Specify USB device serial number"
    echo "  --detect             Detect USB serial device"
    echo "  --list               List installed udev rules"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --serial-only)
                ACTION="serial"
                shift
                ;;
            --cameras-only)
                ACTION="cameras"
                shift
                ;;
            --serial)
                SERIAL_NUMBER="$2"
                shift 2
                ;;
            --detect)
                ACTION="detect"
                shift
                ;;
            --list)
                ACTION="list"
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

# Detect USB serial device
detect_serial() {
    print_info "Detecting USB serial device (Vendor: 1a86, Product: 55d3)..."

    # Try to auto-detect the serial number (filter out null bytes)
    local serial
    serial=$(usb-devices 2>/dev/null | tr -d '\0' | grep -A 10 "Vendor=1a86 ProdID=55d3" | grep "SerialNumber=" | sed 's/.*SerialNumber=//' | head -1)

    if [ -n "$serial" ]; then
        print_success "Found device with serial number: $serial"
        echo "$serial"
        return 0
    else
        print_warning "Could not auto-detect USB device serial number"
        print_info "Make sure the motor controller is connected"
        return 1
    fi
}

# Setup motor controller udev rule
setup_serial_udev() {
    print_header "USB Serial Device Setup"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This creates a persistent /dev/lelamp symlink for your motor controller."
        echo ""
        print_warning "Please plug in your Waveshare Servo Bus Adapter now"
        echo ""
        if ! ask_yes_no "Setup udev rules for motor controller?" "y"; then
            print_info "Skipping serial udev setup"
            return 0
        fi
    fi

    # Try to detect serial number if not provided
    if [ -z "$SERIAL_NUMBER" ]; then
        while true; do
            # Attempt auto-detection
            local detected_serial
            detected_serial=$(usb-devices 2>/dev/null | tr -d '\0' | grep -A 10 "Vendor=1a86 ProdID=55d3" | grep "SerialNumber=" | sed 's/.*SerialNumber=//' | head -1)

            if [ -n "$detected_serial" ]; then
                echo ""
                print_success "Waveshare USB Servo Bus Adapter Found!"
                print_info "SerialNumber: $detected_serial"

                # In non-interactive mode, auto-select the detected device
                if [ "$SKIP_CONFIRM" = "true" ]; then
                    print_info "Auto-selecting detected device (-y mode)"
                    SERIAL_NUMBER="$detected_serial"
                    break
                fi

                echo ""
                if ask_yes_no "Use this device?" "y"; then
                    SERIAL_NUMBER="$detected_serial"
                    break
                fi
            else
                echo ""
                print_warning "Waveshare USB Servo Bus Adapter not detected"

                # In non-interactive mode, skip if not found
                if [ "$SKIP_CONFIRM" = "true" ]; then
                    print_info "No device found, skipping udev rules (-y mode)"
                    return 0
                fi
            fi

            echo ""
            echo "  1) Search again"
            echo "  2) Manual entry"
            echo "  3) Skip"
            echo ""
            read -p "Enter choice [1-3]: " search_choice < "$INPUT_DEVICE"

            case $search_choice in
                1)
                    print_info "Searching for device..."
                    ;;
                2)
                    read -p "Enter SerialNumber: " SERIAL_NUMBER < "$INPUT_DEVICE"
                    if [ -n "$SERIAL_NUMBER" ]; then
                        break
                    fi
                    ;;
                3|*)
                    print_info "Skipping udev rules setup"
                    return 0
                    ;;
            esac
        done
    fi

    # Create udev rule
    UDEV_RULE_FILE="/etc/udev/rules.d/99-lelamp.rules"
    print_info "Creating udev rule at $UDEV_RULE_FILE..."
    print_warning "This requires sudo permissions..."

    if echo "SUBSYSTEM==\"tty\", ATTRS{idVendor}==\"1a86\", ATTRS{idProduct}==\"55d3\", ATTRS{serial}==\"$SERIAL_NUMBER\", MODE=\"0660\", GROUP=\"dialout\", SYMLINK+=\"lelamp\"" | sudo tee $UDEV_RULE_FILE > /dev/null; then
        print_success "Udev rule created successfully"
        print_info "The device will be available at /dev/lelamp after reboot"
    else
        print_error "Failed to create udev rule"
        return 1
    fi
}

# Setup camera and other udev rules from system/udev/
setup_camera_udev() {
    print_header "Installing Camera/USB Udev Rules"

    LELAMP_DIR=$(get_lelamp_dir)
    UDEV_SOURCE_DIR="$LELAMP_DIR/system/udev"

    if [ ! -d "$UDEV_SOURCE_DIR" ]; then
        print_warning "Udev rules directory not found at $UDEV_SOURCE_DIR"
        print_info "Skipping camera udev rules installation"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will install udev rules for USB cameras and devices."
        echo ""
        if ! ask_yes_no "Install camera udev rules?" "y"; then
            print_info "Skipping camera udev rules"
            return 0
        fi
    fi

    print_info "Installing udev rules from $UDEV_SOURCE_DIR..."

    # Count rules files
    local rules_count
    rules_count=$(ls -1 "$UDEV_SOURCE_DIR"/*.rules 2>/dev/null | wc -l)

    if [ "$rules_count" -eq 0 ]; then
        print_warning "No .rules files found in $UDEV_SOURCE_DIR"
        return 0
    fi

    print_info "Found $rules_count udev rules file(s)"

    # Copy all .rules files EXCEPT 99-lelamp.rules (handled by setup_serial_udev with detected serial)
    for rules_file in "$UDEV_SOURCE_DIR"/*.rules; do
        if [ -f "$rules_file" ]; then
            local filename
            filename=$(basename "$rules_file")

            # Skip 99-lelamp.rules - it's created dynamically with the detected serial number
            if [ "$filename" = "99-lelamp.rules" ]; then
                print_info "Skipping $filename (created with detected serial number)"
                continue
            fi

            print_info "Installing $filename..."
            sudo cp "$rules_file" /etc/udev/rules.d/
            print_success "  $filename installed"
        fi
    done

    print_success "Udev rules installed"
}

# Reload udev rules
reload_udev() {
    print_info "Reloading udev rules..."
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    print_success "Udev rules reloaded"
}

# List installed udev rules
list_rules() {
    print_header "Installed LeLamp Udev Rules"
    ls -la /etc/udev/rules.d/99-*.rules 2>/dev/null || print_info "No LeLamp udev rules found"
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            setup_camera_udev
            setup_serial_udev
            reload_udev
            print_info "Rules will be fully active after reboot"
            ;;
        serial)
            setup_serial_udev
            reload_udev
            ;;
        cameras)
            setup_camera_udev
            reload_udev
            ;;
        detect)
            detect_serial
            ;;
        list)
            list_rules
            ;;
    esac
}

# Run main function
main "$@"
