#!/bin/bash
#
# common.sh - Shared functions for LeLamp installation scripts
#
# Source this file in other install scripts:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/common.sh"
#

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}→ $1${NC}"
}

print_step() {
    echo -e "${CYAN}[$1/$2]${NC} $3"
}

# Setup input device for interactive mode
# Handles curl | bash, SSH, and normal terminal usage
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

# Check if running as root
check_root() {
    if [ "$EUID" -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Require root and exit if not
require_root() {
    if ! check_root; then
        print_error "This script must be run as root (sudo $0)"
        exit 1
    fi
}

# Check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Get the LeLamp installation directory
# Priority: 1) LELAMP_DIR env var, 2) Script location parent, 3) ~/lelampv2, 4) ~/lelamp
get_lelamp_dir() {
    if [ -n "$LELAMP_DIR" ]; then
        echo "$LELAMP_DIR"
    elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../main.py" ]; then
        echo "$(cd "$SCRIPT_DIR/.." && pwd)"
    elif [ -d "$HOME/lelampv2" ]; then
        echo "$HOME/lelampv2"
    elif [ -d "$HOME/lelamp" ]; then
        echo "$HOME/lelamp"
    else
        echo "$HOME/lelampv2"
    fi
}

# Get the config file path
get_config_file() {
    echo "$(get_lelamp_dir)/config.yaml"
}

# Detect Raspberry Pi model
detect_rpi_model() {
    if [ ! -f /proc/device-tree/model ]; then
        echo "Unknown"
        return 1
    fi

    local model=$(cat /proc/device-tree/model)

    if echo "$model" | grep -q "Raspberry Pi 5"; then
        echo "5"
    elif echo "$model" | grep -q "Raspberry Pi 4"; then
        echo "4"
    else
        echo "Other"
    fi
}

# Detect config.txt location
get_config_txt() {
    if [ -f /boot/firmware/config.txt ]; then
        echo "/boot/firmware/config.txt"
    elif [ -f /boot/config.txt ]; then
        echo "/boot/config.txt"
    else
        echo ""
    fi
}

# Ask yes/no question with default
# Usage: ask_yes_no "Question?" [default: y/n]
# Returns 0 for yes, 1 for no
ask_yes_no() {
    local question="$1"
    local default="${2:-n}"
    local prompt

    if [ "$default" = "y" ] || [ "$default" = "Y" ]; then
        prompt="[Y/n]"
    else
        prompt="[y/N]"
    fi

    read -p "$question $prompt: " response < "$INPUT_DEVICE"

    if [ -z "$response" ]; then
        response="$default"
    fi

    case "$response" in
        [Yy]*) return 0 ;;
        *) return 1 ;;
    esac
}

# Parse command line arguments
# Sets global variables based on common args
parse_common_args() {
    SKIP_CONFIRM=false
    QUIET=false
    SHOW_HELP=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -y|--yes|--skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            -q|--quiet)
                QUIET=true
                shift
                ;;
            -h|--help)
                SHOW_HELP=true
                shift
                ;;
            *)
                # Unknown option, pass through
                shift
                ;;
        esac
    done
}

# Show standard help footer
show_help_footer() {
    echo ""
    echo "Common options:"
    echo "  -y, --yes, --skip-confirm   Skip confirmation prompts"
    echo "  -q, --quiet                 Reduce output verbosity"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  LELAMP_DIR                  LeLamp installation directory"
    echo ""
}

# Mark a setup step as completed in config.yaml
# Usage: mark_setup_complete "audio"
# Usage: mark_setup_complete "motor_controller"
mark_setup_complete() {
    local step_name="$1"
    local lelamp_dir=$(get_lelamp_dir)
    local config_file="$lelamp_dir/config.yaml"

    if [ ! -f "$config_file" ]; then
        print_warning "Config file not found at $config_file - skipping step tracking"
        return 1
    fi

    print_info "Marking '$step_name' as completed in config.yaml..."

    # Use Python to safely update YAML
    cd "$lelamp_dir"

    # Check if uv is available
    if command_exists uv; then
        uv run python -c "
import yaml
import sys

try:
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f) or {}

    # Ensure setup section exists
    if 'setup' not in config:
        config['setup'] = {}
    if 'steps_completed' not in config['setup']:
        config['setup']['steps_completed'] = {}

    # Mark step as complete
    config['setup']['steps_completed']['$step_name'] = True

    # Write back
    with open('config.yaml', 'w') as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

    print('Setup step marked complete: $step_name')
except Exception as e:
    print(f'Error updating config: {e}', file=sys.stderr)
    sys.exit(1)
"
        if [ $? -eq 0 ]; then
            print_success "Step '$step_name' marked as complete"
            return 0
        else
            print_warning "Failed to mark step complete"
            return 1
        fi
    else
        print_warning "UV not found - cannot update config.yaml"
        return 1
    fi
}

# Initialize script (call at start of each install script)
init_script() {
    setup_input_device

    # Set SCRIPT_DIR if not already set
    if [ -z "$SCRIPT_DIR" ]; then
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    fi

    # Set LELAMP_DIR
    LELAMP_DIR=$(get_lelamp_dir)

    # Ensure config.yaml exists (create from example if needed)
    if [ -n "$LELAMP_DIR" ] && [ -d "$LELAMP_DIR" ]; then
        if [ ! -f "$LELAMP_DIR/config.yaml" ]; then
            if [ -f "$LELAMP_DIR/system/config.example.yaml" ]; then
                cp "$LELAMP_DIR/system/config.example.yaml" "$LELAMP_DIR/config.yaml"
                print_info "Created config.yaml from example template"
            fi
        fi
    fi
}
