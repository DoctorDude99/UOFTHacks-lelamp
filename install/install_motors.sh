#!/bin/bash
#
# install_motors.sh - Setup and configure LeLamp motors
#
# Handles:
#   - Motor driver port detection
#   - Motor ID scanning and assignment
#   - Individual motor ID assignment with safety checks
#   - Center position calibration (set position to 2048)
#   - Servo voltage configuration (7.4V or 12V)
#   - Gentle torque preset for safe operation
#
# Usage:
#   ./install_motors.sh                           # Interactive full setup
#   ./install_motors.sh --detect                  # Detect motor port only
#   ./install_motors.sh --scan                    # Scan for existing motor IDs
#   ./install_motors.sh --check-ids               # Check if IDs 1-5 are configured
#   ./install_motors.sh --motor-id 1              # ID single motor as ID 1
#   ./install_motors.sh --motor-id 2 --force      # Force ID even if exists
#   ./install_motors.sh --set-center 1            # Set motor 1 to center (2048)
#   ./install_motors.sh --set-center all          # Set all motors to center
#   ./install_motors.sh --set-center 1 --confirm  # Skip safety prompt (WebUI)
#   ./install_motors.sh --voltage 12              # Full setup with 12V servos
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
MOTOR_PORT=""
SERVO_VOLTAGE=""
TARGET_MOTOR_ID=""
SET_CENTER_TARGET=""
FORCE_ID=false
CONFIRM_CENTER=false
SKIP_MOTOR_SETUP=false

# Get venv Python path (has PyYAML installed)
get_venv_python() {
    local lelamp_dir="${LELAMP_DIR:-$HOME/lelampv2}"
    local venv_python="$lelamp_dir/.venv/bin/python"
    if [ -x "$venv_python" ]; then
        echo "$venv_python"
    else
        # Fallback to system python3 (may not have PyYAML)
        echo "python3"
    fi
}

# Read voltage from config.yaml
get_config_voltage() {
    local config_file
    config_file=$(get_config_file) || return 1
    local python_cmd
    python_cmd=$(get_venv_python)

    if [ -f "$config_file" ]; then
        local voltage
        voltage=$("$python_cmd" -c "
import yaml
try:
    with open('$config_file', 'r') as f:
        config = yaml.safe_load(f) or {}
    v = config.get('motors', {}).get('voltage', '')
    if v:
        print(v)
except:
    pass
" 2>/dev/null) || true
        if [ -n "$voltage" ]; then
            echo "$voltage"
            return 0
        fi
    fi
    return 1
}

# Update voltage in config.yaml
set_config_voltage() {
    local voltage="$1"
    local config_file
    config_file=$(get_config_file) || return 0
    local python_cmd
    python_cmd=$(get_venv_python)

    if [ -f "$config_file" ]; then
        "$python_cmd" -c "
import yaml
try:
    with open('$config_file', 'r') as f:
        config = yaml.safe_load(f) or {}
    if 'motors' not in config:
        config['motors'] = {}
    config['motors']['voltage'] = float('$voltage')
    with open('$config_file', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
except Exception as e:
    pass  # Ignore errors, voltage setting is not critical
" 2>/dev/null || true
    fi
}

show_help() {
    echo "LeLamp Motor Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Basic Options:"
    echo "  --detect             Detect motor driver port only"
    echo "  --port <PORT>        Specify motor driver port (default: /dev/lelamp)"
    echo "  --voltage <V>        Set servo voltage: 7.4 or 12 (uses config.yaml if not specified)"
    echo "  --skip               Skip motor setup (for pre-built lamps with motors already configured)"
    echo "                       Just verifies motors are present and communication works"
    echo ""
    echo "Motor ID Operations:"
    echo "  --scan               Scan for all motors on the bus"
    echo "  --check-ids          Check if all expected IDs (1-5) are present"
    echo "  --motor-id <ID>      Assign ID to a single motor (1-5)"
    echo "  --force              Force ID assignment even if target ID exists"
    echo ""
    echo "Voltage Limit Operations:"
    echo "  --read-voltage       Read voltage limits from all motors"
    echo "  --fix-voltage        Fix voltage limits for target voltage config"
    echo "                       (Use this if motors show 'Input voltage error')"
    echo ""
    echo "Calibration:"
    echo "  --set-center <ID|all>  Set motor(s) current position as center (2048)"
    echo "  --confirm              Skip safety confirmation (for WebUI use)"
    echo "  --calibrate            Run full motor calibration"
    echo ""
    echo "Testing:"
    echo "  --test               Run motor test"
    echo ""
    echo "Examples:"
    echo "  $0 --skip                        # Pre-built lamp: just verify motors work"
    echo "  $0 --skip --voltage 12           # Pre-built lamp with 12V motors"
    echo "  $0 --voltage 12 -y               # Non-interactive setup with 12V motors"
    echo "  $0 --scan                        # See what motors are connected"
    echo "  $0 --check-ids                   # Verify IDs 1-5 are configured"
    echo "  $0 --motor-id 1                  # ID a single motor as ID 1"
    echo "  $0 --set-center 3                # Set motor 3 to center position"
    echo "  $0 --set-center all --confirm    # Center all motors (WebUI mode)"
    echo "  $0 --read-voltage                # Check motor voltage limits"
    echo "  $0 --fix-voltage --voltage 7.4   # Fix voltage limits for 7.4V servos"
    echo ""
    echo "Motor ID Mapping:"
    echo "  ID 1: base_yaw"
    echo "  ID 2: base_pitch"
    echo "  ID 3: elbow_pitch"
    echo "  ID 4: wrist_roll"
    echo "  ID 5: wrist_pitch"
    echo ""
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --detect)
                ACTION="detect"
                shift
                ;;
            --scan)
                ACTION="scan"
                shift
                ;;
            --check-ids)
                ACTION="check-ids"
                shift
                ;;
            --motor-id)
                ACTION="id-motor"
                TARGET_MOTOR_ID="$2"
                shift 2
                ;;
            --set-center)
                ACTION="set-center"
                SET_CENTER_TARGET="$2"
                shift 2
                ;;
            --confirm)
                CONFIRM_CENTER=true
                shift
                ;;
            --force)
                FORCE_ID=true
                shift
                ;;
            --port)
                MOTOR_PORT="$2"
                shift 2
                ;;
            --voltage)
                SERVO_VOLTAGE="$2"
                shift 2
                ;;
            --calibrate)
                ACTION="calibrate"
                shift
                ;;
            --skip)
                SKIP_MOTOR_SETUP=true
                shift
                ;;
            --read-voltage)
                ACTION="read-voltage"
                shift
                ;;
            --fix-voltage)
                ACTION="fix-voltage"
                shift
                ;;
            --test)
                ACTION="test"
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

# Detect motor driver port
# Note: Status messages go to stderr so they don't get captured by $()
detect_port() {
    print_info "Detecting motor driver port..." >&2

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    # Check if /dev/lelamp exists (udev rule) - preferred
    if [ -e /dev/lelamp ]; then
        print_success "Found /dev/lelamp (udev symlink)" >&2
        echo "/dev/lelamp"
        return 0
    fi

    # Fallback: try lerobot-find-port
    print_info "/dev/lelamp not found, checking for USB device..." >&2
    if command_exists uv; then
        local port
        port=$(uv run lerobot-find-port 2>/dev/null | grep -oP '/dev/tty\w+' | head -1)
        if [ -n "$port" ]; then
            print_warning "Using fallback port: $port (reboot to use /dev/lelamp)" >&2
            echo "$port"
            return 0
        fi
    fi

    print_warning "Could not auto-detect motor driver port" >&2
    print_info "Make sure the motor driver is connected" >&2
    return 1
}

# Ensure port is set
ensure_port() {
    if [ -z "$MOTOR_PORT" ]; then
        MOTOR_PORT=$(detect_port) || true

        if [ -z "$MOTOR_PORT" ]; then
            if [ "$SKIP_CONFIRM" != "true" ]; then
                read -p "Enter motor driver port manually [/dev/lelamp]: " MOTOR_PORT < "$INPUT_DEVICE"
                MOTOR_PORT=${MOTOR_PORT:-/dev/lelamp}
            else
                MOTOR_PORT="/dev/lelamp"
            fi
        fi
    fi
}

# Scan for motors
scan_motors() {
    print_header "Motor Scan"

    ensure_port
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Scanning for motors on $MOTOR_PORT..."
    uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" scan
}

# Check if IDs 1-5 are configured
check_motor_ids() {
    print_header "Motor ID Check"

    ensure_port
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Checking motor IDs on $MOTOR_PORT..."

    if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" check-ids; then
        print_success "All motor IDs (1-5) are properly configured"
        return 0
    else
        print_warning "Motor IDs are not fully configured"
        print_info "Run motor setup to configure missing IDs"
        return 1
    fi
}

# ID a single motor
id_single_motor() {
    print_header "Single Motor ID Assignment"

    if [ -z "$TARGET_MOTOR_ID" ]; then
        print_error "No target motor ID specified"
        print_info "Usage: $0 --motor-id <1-5>"
        return 1
    fi

    # Validate ID range
    if [ "$TARGET_MOTOR_ID" -lt 1 ] || [ "$TARGET_MOTOR_ID" -gt 5 ]; then
        print_error "Motor ID must be 1-5, got: $TARGET_MOTOR_ID"
        return 1
    fi

    ensure_port
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    # Get motor name
    local motor_name
    case $TARGET_MOTOR_ID in
        1) motor_name="base_yaw" ;;
        2) motor_name="base_pitch" ;;
        3) motor_name="elbow_pitch" ;;
        4) motor_name="wrist_roll" ;;
        5) motor_name="wrist_pitch" ;;
    esac

    echo ""
    echo "Motor ID Assignment:"
    echo "  Target ID: $TARGET_MOTOR_ID ($motor_name)"
    echo "  Port: $MOTOR_PORT"
    echo ""

    # Check if target ID already exists (unless force)
    if [ "$FORCE_ID" != "true" ]; then
        print_info "Checking if ID $TARGET_MOTOR_ID already exists on bus..."

        # Run a quick scan to check
        local existing
        existing=$(uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" --json scan 2>/dev/null | grep -o "\"$TARGET_MOTOR_ID\":" || true)

        if [ -n "$existing" ]; then
            print_error "Motor ID $TARGET_MOTOR_ID already exists on the bus!"
            echo ""
            print_warning "If you want to replace this motor:"
            echo "  1. Disconnect the existing motor with ID $TARGET_MOTOR_ID"
            echo "  2. Connect only the new motor to be ID'd"
            echo "  3. Run this command again"
            echo ""
            print_info "Or use --force to override (dangerous if both motors are connected)"
            return 1
        fi
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "IMPORTANT: Connect ONLY the motor you want to assign ID $TARGET_MOTOR_ID"
        echo "All other motors should be disconnected from the bus."
        echo ""
        if ! ask_yes_no "Is only the target motor connected?" "n"; then
            print_info "Please connect only the target motor and try again"
            return 1
        fi
    fi

    local force_arg=""
    if [ "$FORCE_ID" = "true" ]; then
        force_arg="--force"
    fi

    # Retry loop for motor ID assignment
    while true; do
        print_info "Assigning ID $TARGET_MOTOR_ID to connected motor..."

        local id_error
        id_error=$(mktemp)
        if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" id-motor --target-id "$TARGET_MOTOR_ID" $force_arg 2>"$id_error"; then
            rm -f "$id_error"
            print_success "Motor successfully assigned ID $TARGET_MOTOR_ID ($motor_name)"

            # Apply Gentle preset to the motor
            print_info "Applying Gentle torque preset..."
            uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" apply-preset --preset Gentle || true

            echo ""
            print_info "You can now connect the next motor to ID, or run --check-ids to verify"
            return 0
        else
            local error_msg
            error_msg=$(cat "$id_error" 2>/dev/null || echo "Unknown error")
            rm -f "$id_error"

            echo ""
            print_error "Failed to assign motor ID $TARGET_MOTOR_ID"
            echo ""
            echo -e "${YELLOW}Common causes:${NC}"
            echo "  • Motor not connected to the bus"
            echo "  • Motor controller not powered (needs external 7.4V/12V supply)"
            echo "  • USB cable not connected"
            echo "  • Multiple motors connected (only connect ONE at a time)"
            echo ""

            if [ "$SKIP_CONFIRM" = "true" ]; then
                # Non-interactive mode, just fail
                print_error "Motor ID assignment failed in non-interactive mode"
                return 1
            fi

            if ask_yes_no "Would you like to try again?" "y"; then
                echo ""
                print_info "Please check the motor connection and power, then press Enter..."
                read -r < "$INPUT_DEVICE"
                continue
            else
                print_info "Motor ID assignment cancelled"
                return 1
            fi
        fi
    done
}

# Set center position
set_center_position() {
    print_header "Motor Center Calibration"

    if [ -z "$SET_CENTER_TARGET" ]; then
        print_error "No target specified"
        print_info "Usage: $0 --set-center <1-5|all>"
        return 1
    fi

    ensure_port
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    echo ""
    echo -e "${YELLOW}⚠ WARNING: Center Position Calibration${NC}"
    echo ""
    echo "This will set the motor's CURRENT physical position as center (2048)."
    echo ""
    echo -e "${RED}IMPORTANT SAFETY NOTICE:${NC}"
    echo "  - The motor should be UNINSTALLED from the arm mechanism"
    echo "  - Or the arm should be positioned at its mechanical center"
    echo "  - Running this on an installed motor in wrong position can cause:"
    echo "    • Unexpected movement when the arm is powered"
    echo "    • Mechanical damage to the arm or motor"
    echo "    • Position limits being set incorrectly"
    echo ""

    # Safety confirmation (unless --confirm is passed for WebUI)
    if [ "$CONFIRM_CENTER" != "true" ] && [ "$SKIP_CONFIRM" != "true" ]; then
        echo "Is the motor UNINSTALLED from the arm mechanism, or is the arm"
        echo "positioned at its true mechanical center?"
        echo ""
        if ! ask_yes_no "Confirm motor is safe to calibrate?" "n"; then
            print_info "Calibration cancelled for safety"
            print_info "Use --confirm to bypass this check (WebUI mode)"
            return 1
        fi
    fi

    if [ "$SET_CENTER_TARGET" = "all" ]; then
        print_info "Setting center position for all motors..."
        if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" set-center-all; then
            print_success "All motors centered at position 2048"
        else
            print_error "Failed to center some motors"
            return 1
        fi
    else
        # Validate motor ID
        if [ "$SET_CENTER_TARGET" -lt 1 ] || [ "$SET_CENTER_TARGET" -gt 5 ]; then
            print_error "Motor ID must be 1-5, got: $SET_CENTER_TARGET"
            return 1
        fi

        print_info "Setting center position for motor $SET_CENTER_TARGET..."
        if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" set-center --motor-id "$SET_CENTER_TARGET"; then
            print_success "Motor $SET_CENTER_TARGET centered at position 2048"
        else
            print_error "Failed to center motor $SET_CENTER_TARGET"
            return 1
        fi
    fi
}

# Read voltage limits from motors
read_voltage_limits() {
    print_header "Motor Voltage Limits"

    ensure_port
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Reading voltage limits from motors on $MOTOR_PORT..."
    echo ""
    uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" read-voltage
}

# Fix voltage limits on motors
fix_voltage_limits() {
    print_header "Fix Motor Voltage Limits"

    ensure_port
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    # Get servo voltage if not specified
    # Priority: 1) --voltage flag, 2) config.yaml, 3) prompt user
    if [ -z "$SERVO_VOLTAGE" ]; then
        local config_voltage
        config_voltage=$(get_config_voltage) || config_voltage=""

        if [ "$SKIP_CONFIRM" != "true" ]; then
            # Interactive mode - prompt user, suggest config value if available
            echo ""
            echo "What voltage are your Feetech servos?"
            echo "  1) 7.4V servos (STS3215, common)"
            echo "  2) 12V servos"

            local default_choice="1"
            if [ "$config_voltage" = "12" ]; then
                default_choice="2"
                print_info "(config.yaml: 12V)"
            elif [ "$config_voltage" = "7.4" ]; then
                print_info "(config.yaml: 7.4V)"
            fi

            read -p "Enter choice [1-2] (default: $default_choice): " voltage_choice < "$INPUT_DEVICE"
            voltage_choice=${voltage_choice:-$default_choice}

            case $voltage_choice in
                1) SERVO_VOLTAGE="7.4" ;;
                2) SERVO_VOLTAGE="12" ;;
                *) SERVO_VOLTAGE="7.4" ;;
            esac

            set_config_voltage "$SERVO_VOLTAGE"
        else
            # Non-interactive mode - use config.yaml if available
            if [ -n "$config_voltage" ]; then
                SERVO_VOLTAGE="$config_voltage"
                print_info "Using voltage from config.yaml: ${SERVO_VOLTAGE}V"
            else
                print_error "Servo voltage not specified and not in config.yaml!"
                return 1
            fi
        fi
    fi

    print_info "Target voltage config: ${SERVO_VOLTAGE}V"
    echo ""

    local force_arg=""
    if [ "$FORCE_ID" = "true" ]; then
        force_arg="--force"
    fi

    if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" fix-voltage --voltage "$SERVO_VOLTAGE" $force_arg; then
        print_success "Voltage limits updated successfully"
    else
        print_error "Failed to update voltage limits"
        return 1
    fi
}

# Full motor setup
setup_motors() {
    print_header "Motor Setup"

    LELAMP_DIR=$(get_lelamp_dir)

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will configure your LeLamp motors."
        echo "Make sure the motor driver is connected!"
        echo ""
        if ! ask_yes_no "Continue with motor setup?" "y"; then
            print_info "Skipping motor setup"
            return 0
        fi
    fi

    cd "$LELAMP_DIR"
    print_info "Working directory: $LELAMP_DIR"

    # Important power reminder
    echo ""
    echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}  ⚡ IMPORTANT: Motor Controller Power Required ⚡${NC}"
    echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  The motor controller needs BOTH:"
    echo "    1. USB cable connected to Raspberry Pi"
    echo "    2. External power supply (7.4V or 12V depending on your servos)"
    echo ""
    echo "  Without external power, motors will NOT be detected!"
    echo ""
    echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
    echo ""

    if ! ask_yes_no "Is the motor controller powered on?" "y"; then
        print_warning "Please connect power to the motor controller and try again"
        return 0
    fi

    # Detect port if not specified
    ensure_port
    print_success "Using motor driver at: $MOTOR_PORT"

    # Small delay to ensure port is fully released from any previous operation
    sleep 0.5

    # Get servo voltage early (needed for voltage limit check)
    # Priority: 1) --voltage flag, 2) config.yaml (with confirmation), 3) prompt user
    if [ -z "$SERVO_VOLTAGE" ]; then
        # Try to read from config.yaml first
        local config_voltage
        config_voltage=$(get_config_voltage) || config_voltage=""

        if [ "$SKIP_CONFIRM" != "true" ]; then
            # Interactive mode - prompt user, suggest config value if available
            echo ""
            echo "What voltage are your Feetech servos?"
            echo "  1) 7.4V servos (STS3215, common)"
            echo "  2) 12V servos"

            local default_choice="1"
            if [ "$config_voltage" = "12" ]; then
                default_choice="2"
                print_info "(config.yaml: 12V)"
            elif [ "$config_voltage" = "7.4" ]; then
                print_info "(config.yaml: 7.4V)"
            fi

            read -p "Enter choice [1-2] (default: $default_choice): " voltage_choice < "$INPUT_DEVICE"
            voltage_choice=${voltage_choice:-$default_choice}

            case $voltage_choice in
                1) SERVO_VOLTAGE="7.4" ;;
                2) SERVO_VOLTAGE="12" ;;
                *) SERVO_VOLTAGE="7.4" ;;
            esac

            # Save to config.yaml for future use
            set_config_voltage "$SERVO_VOLTAGE"
            print_success "Saved voltage ${SERVO_VOLTAGE}V to config.yaml"
        else
            # Non-interactive mode - use config.yaml if available, else default to 12V
            if [ -n "$config_voltage" ]; then
                SERVO_VOLTAGE="$config_voltage"
                print_info "Using voltage from config.yaml: ${SERVO_VOLTAGE}V"
            else
                SERVO_VOLTAGE="12"
                print_info "Using default voltage: 12V"
                set_config_voltage "$SERVO_VOLTAGE"
            fi
        fi
    else
        # Voltage was specified via --voltage flag, save it to config
        set_config_voltage "$SERVO_VOLTAGE"
    fi
    print_info "Servo voltage: ${SERVO_VOLTAGE}V"

    # Check voltage limits BEFORE scanning (to avoid "Input voltage error")
    print_info "Checking motor voltage limits..."
    local voltage_output
    voltage_output=$(uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" --json read-voltage 2>/dev/null) || voltage_output=""

    if [ -n "$voltage_output" ]; then
        # Check if any motors have wrong voltage config
        local needs_fix
        needs_fix=$(echo "$voltage_output" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    limits = d.get('voltage_limits', {})
    target = '$SERVO_VOLTAGE'
    for mid, info in limits.items():
        if info.get('config') != target:
            print('yes')
            sys.exit(0)
    print('no')
except:
    print('unknown')
" 2>/dev/null) || needs_fix="unknown"

        if [ "$needs_fix" = "yes" ]; then
            echo ""
            echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
            echo -e "${YELLOW}  ⚠ VOLTAGE LIMIT MISMATCH DETECTED ⚠${NC}"
            echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
            echo ""
            echo "  Some motors have voltage limits that don't match your ${SERVO_VOLTAGE}V config."
            echo "  This can cause 'Input voltage error' during setup."
            echo ""
            echo "  Current voltage limits:"
            uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" read-voltage 2>/dev/null || true
            echo ""
            echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
            echo ""

            if [ "$SKIP_CONFIRM" != "true" ]; then
                if ask_yes_no "Fix voltage limits to ${SERVO_VOLTAGE}V config?" "y"; then
                    print_info "Fixing voltage limits..."
                    if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" fix-voltage --voltage "$SERVO_VOLTAGE"; then
                        print_success "Voltage limits fixed!"
                        sleep 0.5
                    else
                        print_error "Failed to fix voltage limits"
                        print_info "You can try manually with: ./install_motors.sh --fix-voltage --voltage $SERVO_VOLTAGE"
                    fi
                fi
            else
                # In non-interactive mode, auto-fix voltage limits
                print_info "Auto-fixing voltage limits..."
                uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" fix-voltage --voltage "$SERVO_VOLTAGE" || true
            fi
            echo ""
        fi
    fi

    # Scan for motors and show what's found
    print_info "Scanning for motors on bus..."
    local check_output
    local check_err
    check_err=$(mktemp)
    check_output=$(uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" --json check-ids 2>"$check_err") || true

    # Show any errors that occurred
    if [ -s "$check_err" ]; then
        print_warning "Motor scan stderr: $(cat "$check_err")"
    fi
    rm -f "$check_err"

    if [ -n "$check_output" ]; then
        # Parse JSON output to show found motors
        local found_ids missing_ids all_present
        found_ids=$(echo "$check_output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(map(str,d['found_ids'])))" 2>/dev/null) || found_ids=""
        missing_ids=$(echo "$check_output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(map(str,d['missing_ids'])))" 2>/dev/null) || missing_ids=""
        all_present=$(echo "$check_output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['all_present'])" 2>/dev/null) || all_present="False"

        if [ -n "$found_ids" ]; then
            print_success "Found motor IDs: $found_ids"
        else
            print_warning "No motors found on bus"
        fi

        if [ -n "$missing_ids" ]; then
            print_warning "Missing motor IDs: $missing_ids"
        fi

        if [ "$all_present" = "True" ]; then
            print_success "All motor IDs (1-5) are configured!"

            if [ "$SKIP_CONFIRM" != "true" ]; then
                echo ""
                print_warning "Motors appear to already be set up."
                echo "Do you want to:"
                echo "  1) Skip motor ID setup (recommended)"
                echo "  2) Re-run full motor ID setup anyway"
                read -p "Enter choice [1-2]: " setup_choice < "$INPUT_DEVICE"

                case $setup_choice in
                    1)
                        print_info "Skipping motor ID setup"
                        ;;
                    2)
                        print_info "Re-running full motor ID setup..."
                        run_full_motor_setup
                        ;;
                    *)
                        print_info "Skipping motor ID setup"
                        ;;
                esac
            else
                print_info "All motors present, skipping ID setup"
            fi

            # Always apply Gentle preset for safe operation
            print_info "Applying Gentle torque preset..."
            uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" apply-preset --preset Gentle 2>/dev/null || true
            print_success "Motor setup complete"
        else
            print_info "Motor IDs need to be configured, running setup..."
            run_full_motor_setup
        fi
    else
        print_warning "Could not communicate with motor controller"
        print_info "Running setup anyway..."
        run_full_motor_setup
    fi
}

# Run the full motor ID setup (called by setup_motors)
run_full_motor_setup() {
    # Ensure we're in the right directory for uv run
    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    # Always use "lelamp" as the lamp ID
    # Lamp ID is always "lelamp" - one lamp per RPi5

    # Get servo voltage if not specified
    # Priority: 1) already set (from setup_motors), 2) config.yaml, 3) prompt user
    if [ -z "$SERVO_VOLTAGE" ]; then
        local config_voltage
        config_voltage=$(get_config_voltage) || config_voltage=""

        if [ "$SKIP_CONFIRM" != "true" ]; then
            # Interactive mode - prompt user, suggest config value if available
            echo ""
            echo "What voltage are your Feetech servos?"
            echo "  1) 7.4V servos (STS3215, common)"
            echo "  2) 12V servos"

            local default_choice="1"
            if [ "$config_voltage" = "12" ]; then
                default_choice="2"
                print_info "(config.yaml: 12V)"
            elif [ "$config_voltage" = "7.4" ]; then
                print_info "(config.yaml: 7.4V)"
            fi

            read -p "Enter choice [1-2] (default: $default_choice): " voltage_choice < "$INPUT_DEVICE"
            voltage_choice=${voltage_choice:-$default_choice}

            case $voltage_choice in
                1) SERVO_VOLTAGE="7.4" ;;
                2) SERVO_VOLTAGE="12" ;;
                *) SERVO_VOLTAGE="7.4" ;;
            esac

            set_config_voltage "$SERVO_VOLTAGE"
            print_success "Saved voltage ${SERVO_VOLTAGE}V to config.yaml"
        else
            # Non-interactive mode - use config.yaml if available, else default to 12V
            if [ -n "$config_voltage" ]; then
                SERVO_VOLTAGE="$config_voltage"
                print_info "Using voltage from config.yaml: ${SERVO_VOLTAGE}V"
            else
                SERVO_VOLTAGE="12"
                print_info "Using default voltage: 12V"
                set_config_voltage "$SERVO_VOLTAGE"
            fi
        fi
    fi

    print_info "Servo voltage: ${SERVO_VOLTAGE}V"

    # Run motor setup
    print_info "Setting up motors..."
    print_warning "Follow the on-screen instructions carefully!"

    # Use relative path since we're already in LELAMP_DIR
    # Redirect INPUT_DEVICE to stdin so Python's input() works properly
    uv run python install/setup_motors.py --port "$MOTOR_PORT" --voltage "$SERVO_VOLTAGE" < "$INPUT_DEVICE"

    print_success "Motor setup complete!"
    echo ""
    print_info "Next step: Calibrate motors with:"
    echo "  uv run -m lelamp.calibrate --port $MOTOR_PORT"
}

# Skip motor setup - just verify motors are present (for pre-built lamps)
verify_motors_only() {
    print_header "Motor Verification (Pre-Built Lamp)"

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Verifying motors for pre-built lamp..."
    print_info "This will check that all 5 motors are present and responding."
    echo ""

    # Detect port
    ensure_port
    print_info "Using motor driver at: $MOTOR_PORT"

    # Get voltage from --voltage flag or config.yaml
    if [ -z "$SERVO_VOLTAGE" ]; then
        local config_voltage
        config_voltage=$(get_config_voltage) || config_voltage=""

        if [ -n "$config_voltage" ]; then
            SERVO_VOLTAGE="$config_voltage"
            print_info "Using voltage from config.yaml: ${SERVO_VOLTAGE}V"
        else
            print_error "Servo voltage not specified and not in config.yaml!"
            print_info "Either:"
            print_info "  1. Set motors.voltage in config.yaml"
            print_info "  2. Use --voltage flag: ./install_motors.sh --skip --voltage 12"
            return 1
        fi
    fi
    print_info "Servo voltage: ${SERVO_VOLTAGE}V"

    # Check if all motor IDs 1-5 are present
    print_info "Scanning for motors..."
    local check_output
    check_output=$(uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" --json check-ids 2>/dev/null) || check_output=""

    if [ -z "$check_output" ]; then
        print_error "Could not communicate with motor controller!"
        print_info "Check that:"
        print_info "  1. USB cable is connected"
        print_info "  2. Motor controller has external power (${SERVO_VOLTAGE}V)"
        print_info "  3. /dev/lelamp symlink exists (or specify --port)"
        return 1
    fi

    # Parse JSON output
    local found_ids missing_ids all_present
    found_ids=$(echo "$check_output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(map(str,d['found_ids'])))" 2>/dev/null) || found_ids=""
    missing_ids=$(echo "$check_output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(map(str,d['missing_ids'])))" 2>/dev/null) || missing_ids=""
    all_present=$(echo "$check_output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['all_present'])" 2>/dev/null) || all_present="False"

    echo ""
    if [ -n "$found_ids" ]; then
        print_success "Found motors: $found_ids"
    fi

    if [ "$all_present" = "True" ]; then
        print_success "All 5 motors (IDs 1-5) verified!"
        echo ""

        # Apply Gentle preset for safe operation
        print_info "Applying Gentle torque preset..."
        if uv run python -m lelamp.motor_utils --port "$MOTOR_PORT" apply-preset --preset Gentle 2>/dev/null; then
            print_success "Torque preset applied"
        else
            print_warning "Could not apply preset (motors may have existing settings)"
        fi

        print_success "Pre-built lamp motor verification complete!"
        return 0
    else
        print_error "Not all motors found!"
        if [ -n "$missing_ids" ]; then
            print_warning "Missing motor IDs: $missing_ids"
        fi
        echo ""
        print_info "This lamp appears to need motor ID setup."
        print_info "Run without --skip: ./install_motors.sh"
        return 1
    fi
}

# Run motor calibration
run_calibration() {
    print_header "Motor Calibration"

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Running motor calibration..."
    print_warning "Follow the on-screen instructions!"

    uv run -m lelamp.calibrate
}

# Run motor test
run_test() {
    print_header "Motor Test"

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    print_info "Running motor test..."

    uv run -m lelamp.test.test_motors
}

# Main function
main() {
    init_script
    parse_args "$@"

    # Handle --skip flag for pre-built lamps
    if [ "$SKIP_MOTOR_SETUP" = "true" ]; then
        verify_motors_only
        # Mark motor setup as complete in config.yaml
        mark_setup_complete "motor_controller"
        mark_setup_complete "motor_ids"
        return $?
    fi

    case $ACTION in
        install)
            setup_motors
            ;;
        detect)
            detect_port
            ;;
        scan)
            scan_motors
            ;;
        check-ids)
            check_motor_ids
            ;;
        id-motor)
            id_single_motor
            ;;
        set-center)
            set_center_position
            ;;
        calibrate)
            run_calibration
            ;;
        read-voltage)
            read_voltage_limits
            ;;
        fix-voltage)
            fix_voltage_limits
            ;;
        test)
            run_test
            ;;
    esac

    # Mark motor setup as complete in config.yaml
    mark_setup_complete "motor_controller"
}

# Run main function
main "$@"
