#!/bin/bash
#
# install_audio.sh - Audio hardware configuration for LeLamp
#
# Supports:
#   - LeLamp Default (USB-C Speaker + Innomaker USB Camera Microphone)
#   - ReSpeaker 2-Mic HAT v1.x (WM8960 codec)
#   - ReSpeaker 2-Mic HAT v2.x (TLV320AIC3X / seeed2micvoicec)
#   - Custom setup (select your own playback/capture devices)
#   - ALSA loopback for audio processing pipeline (optional)
#
# Usage:
#   ./install_audio.sh                    # Interactive menu
#   ./install_audio.sh --choice 0         # LeLamp Default (recommended)
#   ./install_audio.sh --choice 1         # ReSpeaker v1.x
#   ./install_audio.sh --choice 2         # ReSpeaker v2.x
#   ./install_audio.sh --choice 3         # Custom device selection
#   ./install_audio.sh --setup-loopback   # Setup ALSA loopback module
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
AUDIO_CHOICE=""
SETUP_LOOPBACK=false

show_help() {
    echo "LeLamp Audio Hardware Configuration"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --choice <TYPE>    Select audio hardware without prompting"
    echo "                     Types: 0, 1, 2, 3, default, respeaker-v1, respeaker-v2, custom"
    echo "  --setup-loopback   Setup ALSA loopback module for audio processing"
    echo ""
    echo "Audio hardware types:"
    echo "  0, default         LeLamp Default (USB-C Speaker + Innomaker Camera Mic)"
    echo "  1, respeaker-v1    ReSpeaker 2-Mic HAT v1.x (WM8960 codec)"
    echo "  2, respeaker-v2    ReSpeaker 2-Mic HAT v2.x (TLV320AIC3X)"
    echo "  3, custom          Custom device selection (interactive)"
    echo ""
    echo "Audio processing (optional):"
    echo "  --setup-loopback   Install snd-aloop kernel module for audio routing"
    echo "                     Enables gating mic during AI playback (echo prevention)"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --choice)
                AUDIO_CHOICE="$2"
                shift 2
                ;;
            --setup-loopback)
                SETUP_LOOPBACK=true
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

# Normalize choice to numeric value
normalize_choice() {
    case "$1" in
        0|default|lelamp|lelamp-default|usb-c|innomaker)
            echo "0"
            ;;
        1|respeaker-v1|respeaker_v1|v1|wm8960)
            echo "1"
            ;;
        2|respeaker-v2|respeaker_v2|v2|seeed|seeed2micvoicec|tlv320)
            echo "2"
            ;;
        3|custom|halox|halo|uac)
            echo "3"
            ;;
        4|skip|none)
            echo "4"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Test audio playback and recording
test_audio() {
    echo ""
    print_header "Testing Audio"

    # Set volume to 75% for testing
    print_info "Setting volume to 75% for testing..."
    amixer sset 'Speaker' 75% 2>/dev/null || true
    amixer sset 'Playback' 75% 2>/dev/null || true
    amixer sset 'PCM' 75% 2>/dev/null || true

    # Test playback
    TEST_WAV="$LELAMP_DIR/assets/setup/LeLamp-SpeakerTest.wav"
    if [ -f "$TEST_WAV" ]; then
        print_info "Playing test audio at 75% volume..."
        aplay "$TEST_WAV" 2>/dev/null || play "$TEST_WAV" 2>/dev/null || true
        echo ""
        if ! ask_yes_no "Did you hear the audio?" "y"; then
            print_warning "Audio playback may need troubleshooting after reboot"
        else
            print_success "Playback working"
        fi
    else
        print_warning "Test audio file not found, skipping playback test"
    fi

    # Test recording
    echo ""
    print_info "Recording 5 seconds of audio... speak now!"
    TEMP_RECORDING="/tmp/lelamp_audio_test.wav"
    arecord -f S16_LE -r 48000 -c 2 -d 5 "$TEMP_RECORDING" 2>/dev/null || true

    if [ -f "$TEMP_RECORDING" ]; then
        print_info "Playing back your recording..."
        aplay "$TEMP_RECORDING" 2>/dev/null || play "$TEMP_RECORDING" 2>/dev/null || true
        rm -f "$TEMP_RECORDING"
        echo ""
        if ! ask_yes_no "Did you hear your recording?" "y"; then
            print_warning "Audio recording may need troubleshooting after reboot"
        else
            print_success "Recording working"
        fi
    else
        print_warning "Recording failed, may need reboot first"
    fi
}

# Load audio overlay and set volume (call after overlay is configured)
load_audio_overlay() {
    local overlay_name="$1"
    local card_name="$2"

    # Try to load overlay dynamically (avoids needing immediate reboot)
    print_info "Attempting to load $overlay_name overlay..."
    if sudo dtoverlay "$overlay_name" 2>/dev/null; then
        print_success "Overlay loaded dynamically"
        sleep 1

        # Find the card number for this device
        local card_num
        card_num=$(aplay -l 2>/dev/null | grep -i "$card_name" | grep -oP 'card \K[0-9]+' | head -1)

        if [ -n "$card_num" ]; then
            print_info "Setting audio levels on card $card_num..."
            # Set playback volume levels to 50%
            amixer -c "$card_num" sset 'Speaker' 50% 2>/dev/null || true
            amixer -c "$card_num" sset 'Playback' 50% 2>/dev/null || true
            amixer -c "$card_num" sset 'Left Output Mixer PCM' on 2>/dev/null || true
            amixer -c "$card_num" sset 'Right Output Mixer PCM' on 2>/dev/null || true
            # Set capture/input volume levels
            amixer -c "$card_num" sset 'Capture' 80% 2>/dev/null || true
            amixer -c "$card_num" sset 'Left Input Mixer Boost' on 2>/dev/null || true
            amixer -c "$card_num" sset 'Right Input Mixer Boost' on 2>/dev/null || true
            amixer -c "$card_num" sset 'ADC' 80% 2>/dev/null || true
            amixer -c "$card_num" sset 'ADC PCM' 80% 2>/dev/null || true
            # Save mixer settings
            sudo alsactl store 2>/dev/null || true
            print_success "Audio levels configured"
        else
            print_warning "Could not find $card_name card - volume will be set after reboot"
        fi
    else
        print_warning "Could not load overlay dynamically - will be active after reboot"
    fi
}

# Setup ReSpeaker v1.x (WM8960)
setup_respeaker_v1() {
    print_info "Setting up ReSpeaker 2-Mic HAT v1.x (WM8960)..."

    # Run the ReSpeaker setup script for overlay configuration
    RESPEAKER_SCRIPT="$LELAMP_DIR/system/respeaker-2mic-setup/fix_respeaker.sh"

    if [ -f "$RESPEAKER_SCRIPT" ]; then
        chmod +x "$RESPEAKER_SCRIPT"
        print_info "Running ReSpeaker setup script..."

        # Force v1 selection by echoing 1 to the script, suppress verbose output
        echo "1" | sudo bash "$RESPEAKER_SCRIPT" > /dev/null 2>&1
        print_success "ReSpeaker v1.x (WM8960) configured"

        # Load overlay and set volume
        load_audio_overlay "wm8960-soundcard" "wm8960"

        # Test audio
        test_audio
    else
        print_error "ReSpeaker setup script not found at $RESPEAKER_SCRIPT"
        return 1
    fi
}

# Setup ReSpeaker v2.x (seeed2micvoicec)
setup_respeaker_v2() {
    print_info "Setting up ReSpeaker 2-Mic HAT v2.x (seeed2micvoicec)..."

    # Run the ReSpeaker setup script for overlay configuration
    RESPEAKER_SCRIPT="$LELAMP_DIR/system/respeaker-2mic-setup/fix_respeaker.sh"

    if [ -f "$RESPEAKER_SCRIPT" ]; then
        chmod +x "$RESPEAKER_SCRIPT"
        print_info "Running ReSpeaker setup script..."

        # Force v2 selection by echoing 2 to the script, suppress verbose output
        echo "2" | sudo bash "$RESPEAKER_SCRIPT" > /dev/null 2>&1
        print_success "ReSpeaker v2.x (seeed2micvoicec) configured"

        # Load overlay and set volume
        load_audio_overlay "seeed-2mic-voicecard" "seeed2micvoicec"

        # Test audio
        test_audio
    else
        print_error "ReSpeaker setup script not found at $RESPEAKER_SCRIPT"
        return 1
    fi
}

# Setup LeLamp Default (USB-C Speaker + Innomaker Camera Microphone)
setup_lelamp_default() {
    print_header "LeLamp Default Audio Configuration"
    print_info "Setting up USB-C Speaker + Innomaker USB Camera Microphone..."

    # Backup existing asound.conf if it exists
    if [ -f /etc/asound.conf ]; then
        BACKUP_FILE="/etc/asound.conf.backup.$(date +%Y%m%d_%H%M%S)"
        print_info "Backing up existing /etc/asound.conf to $BACKUP_FILE"
        sudo cp /etc/asound.conf "$BACKUP_FILE"
    fi

    # Copy the pre-built default configuration
    local DEFAULT_CONF="$LELAMP_DIR/system/asound/asound-lelamp-default.conf"
    if [ -f "$DEFAULT_CONF" ]; then
        sudo cp "$DEFAULT_CONF" /etc/asound.conf
        print_success "ALSA configuration installed"
    else
        print_error "Default config not found: $DEFAULT_CONF"
        return 1
    fi

    # Set audio levels
    print_info "Setting audio levels..."
    amixer sset 'Speaker' 50% 2>/dev/null || true
    amixer sset 'PCM' 50% 2>/dev/null || true
    amixer sset 'Master' 50% 2>/dev/null || true
    # Mic levels
    amixer sset 'Mic' 80% 2>/dev/null || true
    amixer sset 'Capture' 80% 2>/dev/null || true
    sudo alsactl store 2>/dev/null || true
    print_success "Audio levels configured"

    echo ""
    print_info "Configuration:"
    echo "  Playback: USB-C Speaker (card: Device)"
    echo "  Capture:  Innomaker USB Camera (card: InnomakerU20CAM)"
    echo ""
    print_info "Devices used:"
    echo "  lelamp_playback → dmix → hw:Device,0 @ 48kHz"
    echo "  lelamp_capture  → dsnoop → hw:InnomakerU20CAM,0 @ 48kHz"
    echo ""

    # Test audio
    test_audio
}

# Setup custom audio devices
setup_custom_audio() {
    print_header "Custom Audio Device Configuration"

    # Load device mapping from devices.yaml
    local DEVICES_YAML="$LELAMP_DIR/system/asound/devices.yaml"

    # Get playback devices
    echo ""
    print_info "Available PLAYBACK devices (speakers/output):"
    echo "----------------------------------------"

    # Show pre-configured devices from yaml
    local playback_keys=()
    local playback_names=()
    local idx=1

    while IFS= read -r line; do
        # Match only top-level device keys (2 spaces, key, colon)
        if [[ "$line" =~ ^[[:space:]]{2}([a-z0-9_]+):[[:space:]]*$ ]]; then
            local key="${BASH_REMATCH[1]}"
            playback_keys+=("$key")

            # Get device name
            local name=$(awk -v key="$key" '
                $1 == key ":" { in_device=1; next }
                in_device && /name:/ {
                    gsub(/^[ \t]+name:[ \t]+"/, "")
                    gsub(/".*$/, "")
                    print
                    exit
                }
            ' "$DEVICES_YAML")

            playback_names+=("$name")
            echo "  $idx) $name"
            ((idx++))
        fi
    done < <(sed -n '/^playback_devices:/,/^capture_devices:/p' "$DEVICES_YAML" | head -n -1)

    echo "----------------------------------------"
    echo ""
    read -p "Select PLAYBACK device [1-${#playback_keys[@]}]: " playback_choice < "$INPUT_DEVICE"

    if [ -z "$playback_choice" ] || [ "$playback_choice" -lt 1 ] || [ "$playback_choice" -gt "${#playback_keys[@]}" ]; then
        print_error "Invalid selection"
        return 1
    fi

    PLAYBACK_DEVICE="${playback_keys[$((playback_choice - 1))]}"
    print_success "Selected playback: ${playback_names[$((playback_choice - 1))]} ($PLAYBACK_DEVICE)"

    # Get capture devices
    echo ""
    print_info "Available CAPTURE devices (microphones/input):"
    echo "----------------------------------------"

    # Show pre-configured devices from yaml
    local capture_keys=()
    local capture_names=()
    idx=1

    while IFS= read -r line; do
        # Match only top-level device keys (2 spaces, key, colon)
        if [[ "$line" =~ ^[[:space:]]{2}([a-z0-9_]+):[[:space:]]*$ ]]; then
            local key="${BASH_REMATCH[1]}"
            capture_keys+=("$key")

            # Get device name
            local name=$(awk -v key="$key" '
                $1 == key ":" { in_device=1; next }
                in_device && /name:/ {
                    gsub(/^[ \t]+name:[ \t]+"/, "")
                    gsub(/".*$/, "")
                    print
                    exit
                }
            ' "$DEVICES_YAML")

            capture_names+=("$name")
            echo "  $idx) $name"
            ((idx++))
        fi
    done < <(sed -n '/^capture_devices:/,$p' "$DEVICES_YAML")

    echo "----------------------------------------"
    echo ""
    read -p "Select CAPTURE device [1-${#capture_keys[@]}]: " capture_choice < "$INPUT_DEVICE"

    if [ -z "$capture_choice" ] || [ "$capture_choice" -lt 1 ] || [ "$capture_choice" -gt "${#capture_keys[@]}" ]; then
        print_error "Invalid selection"
        return 1
    fi

    CAPTURE_DEVICE="${capture_keys[$((capture_choice - 1))]}"
    print_success "Selected capture: ${capture_names[$((capture_choice - 1))]} ($CAPTURE_DEVICE)"

    # Generate custom asound.conf using template
    echo ""
    print_info "Generating ALSA configuration from template..."

    # Backup existing asound.conf if it exists
    if [ -f /etc/asound.conf ]; then
        BACKUP_FILE="/etc/asound.conf.backup.$(date +%Y%m%d_%H%M%S)"
        print_info "Backing up existing /etc/asound.conf to $BACKUP_FILE"
        sudo cp /etc/asound.conf "$BACKUP_FILE"
    fi

    # Use the generate script
    GENERATE_SCRIPT="$LELAMP_DIR/system/asound/generate_asound.sh"
    if [ -f "$GENERATE_SCRIPT" ]; then
        bash "$GENERATE_SCRIPT" "$PLAYBACK_DEVICE" "$CAPTURE_DEVICE" /tmp/asound.conf
        sudo cp /tmp/asound.conf /etc/asound.conf
        rm /tmp/asound.conf
        print_success "ALSA configuration installed"
    else
        print_error "Generator script not found: $GENERATE_SCRIPT"
        return 1
    fi

    # Test audio
    test_audio
}

# Setup ALSA loopback for audio processing pipeline
setup_alsa_loopback() {
    print_header "ALSA Loopback Setup"
    print_info "Setting up snd-aloop kernel module for audio processing pipeline..."

    # Load the loopback module with specific index
    if lsmod | grep -q snd_aloop; then
        print_info "snd-aloop module already loaded"
    else
        print_info "Loading snd-aloop module..."
        sudo modprobe snd-aloop index=10 pcm_substreams=1
        if lsmod | grep -q snd_aloop; then
            print_success "snd-aloop module loaded"
        else
            print_error "Failed to load snd-aloop module"
            return 1
        fi
    fi

    # Make module persistent across reboots
    if ! grep -q "snd-aloop" /etc/modules 2>/dev/null; then
        print_info "Adding snd-aloop to /etc/modules for persistence..."
        echo "snd-aloop" | sudo tee -a /etc/modules > /dev/null
        print_success "Module will load on boot"
    else
        print_info "snd-aloop already in /etc/modules"
    fi

    # Configure modprobe options
    MODPROBE_CONF="/etc/modprobe.d/snd-aloop.conf"
    if [ ! -f "$MODPROBE_CONF" ]; then
        print_info "Creating modprobe configuration..."
        echo "options snd-aloop index=10 pcm_substreams=1" | sudo tee "$MODPROBE_CONF" > /dev/null
        print_success "Modprobe config created"
    fi

    # Verify loopback device
    if aplay -l 2>/dev/null | grep -q "Loopback"; then
        print_success "Loopback device verified"
        aplay -l 2>/dev/null | grep "Loopback"
    else
        print_warning "Loopback device not visible yet - may need reboot"
    fi

    echo ""
    print_info "Loopback Audio Pipeline Architecture:"
    echo "  Real Mic (lelamp_capture_raw)"
    echo "       ↓"
    echo "  AudioRouter (gating during AI playback)"
    echo "       ↓"
    echo "  Loopback (loopback_sink → loopback_source)"
    echo "       ↓"
    echo "  LiveKit (lelamp_capture)"
    echo "       ↓"
    echo "  AI Backend"
    echo ""
    print_info "To enable loopback routing, set in config.yaml:"
    echo "  microphone:"
    echo "    audio_routing_enabled: true"
    echo ""
    print_success "ALSA loopback setup complete"
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

    # Handle --setup-loopback flag
    if [ "$SETUP_LOOPBACK" = true ]; then
        setup_alsa_loopback
        exit 0
    fi

    local choice

    # Use provided choice or show menu
    if [ -n "$AUDIO_CHOICE" ]; then
        choice=$(normalize_choice "$AUDIO_CHOICE")
        if [ -z "$choice" ]; then
            print_error "Invalid audio choice: $AUDIO_CHOICE"
            print_info "Valid options: 1, 2, 3, respeaker-v1, respeaker-v2, custom"
            exit 1
        fi
        print_info "Using audio configuration: $AUDIO_CHOICE (option $choice)"
    else
        # Show menu directly (no command substitution)
        print_header "Audio Hardware Configuration"

        echo "Select your audio hardware:"
        echo ""
        echo "  0) LeLamp Default (Recommended)"
        echo "     USB-C Speaker + Innomaker USB Camera Microphone"
        echo ""
        echo "  1) ReSpeaker 2-Mic HAT v1.x (WM8960 codec)"
        echo "     Older ReSpeaker boards (v1.0, v1.2, etc.)"
        echo ""
        echo "  2) ReSpeaker 2-Mic HAT v2.x (seeed2micvoicec)"
        echo "     Newer ReSpeaker boards with TLV320AIC3X codec"
        echo ""
        echo "  3) Custom (select your own devices)"
        echo "     Pick playback and capture devices from a list"
        echo ""
        echo "  4) Skip audio configuration"
        echo ""
        read -p "Enter choice [0-4] (default: 0): " choice < "$INPUT_DEVICE"
        choice=${choice:-0}
    fi

    case $choice in
        0)
            setup_lelamp_default
            ;;
        1)
            setup_respeaker_v1
            ;;
        2)
            setup_respeaker_v2
            ;;
        3)
            setup_custom_audio
            ;;
        4)
            print_info "Skipping audio configuration"
            print_info "You can configure audio later using:"
            print_info "  $0 --choice <type>"
            ;;
        *)
            print_warning "Invalid choice: $choice"
            exit 1
            ;;
    esac

    # Mark audio setup as complete in config.yaml
    mark_setup_complete "audio"
}

# Run main function
main "$@"
