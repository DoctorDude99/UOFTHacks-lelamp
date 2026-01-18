#!/bin/bash
#
# generate_asound.sh - Generate ALSA configuration from template
#
# Usage:
#   ./generate_asound.sh <playback_device> <capture_device> [output_file]
#   ./generate_asound.sh waveshare camera
#   ./generate_asound.sh halox camera /etc/asound.conf
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/template.conf"
DEVICES_YAML="$SCRIPT_DIR/devices.yaml"

# Parse arguments
PLAYBACK_DEVICE="$1"
CAPTURE_DEVICE="$2"
OUTPUT_FILE="${3:-/tmp/asound.conf}"

if [ -z "$PLAYBACK_DEVICE" ] || [ -z "$CAPTURE_DEVICE" ]; then
    echo "Usage: $0 <playback_device> <capture_device> [output_file]"
    echo ""
    echo "Available playback devices:"
    grep -A 1 "^  [a-z]" "$DEVICES_YAML" | grep -E "^  [a-z]|name:" | sed 's/://' | paste - - | awk '{print "  " $1 " - " $4,$5,$6,$7,$8}'
    echo ""
    echo "Available capture devices:"
    grep -A 1 "^  [a-z]" "$DEVICES_YAML" | grep -E "^  [a-z]|name:" | tail -n +3 | sed 's/://' | paste - - | awk '{print "  " $1 " - " $4,$5,$6,$7,$8}'
    exit 1
fi

# Function to get YAML value
get_yaml_value() {
    local section=$1
    local device=$2
    local key=$3

    # Extract value from YAML (simple parsing, good enough for our needs)
    awk -v section="$section" -v device="$device" -v key="$key" '
        $0 ~ "^" section ":" { in_section=1; next }
        in_section && $1 == device ":" { in_device=1; next }
        in_device && $1 == key ":" {
            gsub(/^[ \t]+|[ \t]+$/, "", $2)
            gsub(/"/, "", $2)
            print $2
            exit
        }
        in_device && /^  [a-z]/ { exit }
    ' "$DEVICES_YAML"
}

# Get playback device info
PLAYBACK_NAME=$(get_yaml_value "playback_devices" "$PLAYBACK_DEVICE" "name")
PLAYBACK_CARD=$(get_yaml_value "playback_devices" "$PLAYBACK_DEVICE" "card")
PLAYBACK_DEVICE_NUM=$(get_yaml_value "playback_devices" "$PLAYBACK_DEVICE" "device")
PLAYBACK_CHANNELS=$(get_yaml_value "playback_devices" "$PLAYBACK_DEVICE" "channels")
PLAYBACK_RATE=$(get_yaml_value "playback_devices" "$PLAYBACK_DEVICE" "rate")

# Get capture device info
CAPTURE_NAME=$(get_yaml_value "capture_devices" "$CAPTURE_DEVICE" "name")
CAPTURE_CARD=$(get_yaml_value "capture_devices" "$CAPTURE_DEVICE" "card")
CAPTURE_DEVICE_NUM=$(get_yaml_value "capture_devices" "$CAPTURE_DEVICE" "device")
CAPTURE_CHANNELS=$(get_yaml_value "capture_devices" "$CAPTURE_DEVICE" "channels")
CAPTURE_RATE=$(get_yaml_value "capture_devices" "$CAPTURE_DEVICE" "rate")
CAPTURE_DSNOOP=$(get_yaml_value "capture_devices" "$CAPTURE_DEVICE" "dsnoop")

# Validate we got the data
if [ -z "$PLAYBACK_CARD" ]; then
    echo "Error: Playback device '$PLAYBACK_DEVICE' not found in devices.yaml"
    exit 1
fi

if [ -z "$CAPTURE_CARD" ]; then
    echo "Error: Capture device '$CAPTURE_DEVICE' not found in devices.yaml"
    exit 1
fi

# Build dsnoop block - ALWAYS use dsnoop to allow mic sharing (needed for sleep mode wake detection)
# Only skip dsnoop if explicitly set to "false"
if [ "$CAPTURE_DSNOOP" != "false" ]; then
    CAPTURE_DSNOOP_SUFFIX="_dsnoop"
    CAPTURE_DSNOOP_COMMENT=" and dsnoop for capture"
    CAPTURE_DSNOOP_BLOCK="pcm.hw_capture_dsnoop {
    type dsnoop
    ipc_key 1025
    ipc_perm 0666
    slave {
        pcm {
            type hw
            card $CAPTURE_CARD
            device $CAPTURE_DEVICE_NUM
        }
        rate $CAPTURE_RATE
        format S16_LE
        channels $CAPTURE_CHANNELS
        period_size 1024
        buffer_size 4096
    }
    bindings {
        0 0
        1 1
    }
}"
else
    CAPTURE_DSNOOP_SUFFIX=""
    CAPTURE_DSNOOP_COMMENT=""
    CAPTURE_DSNOOP_BLOCK="pcm.hw_capture {
    type hw
    card $CAPTURE_CARD
    device $CAPTURE_DEVICE_NUM
}"
fi

# Generate config from template
cp "$TEMPLATE" "$OUTPUT_FILE"

# Replace all placeholders using awk (handles multiline better than sed)
awk -v playback_name="$PLAYBACK_NAME" \
    -v playback_card="$PLAYBACK_CARD" \
    -v playback_device="$PLAYBACK_DEVICE_NUM" \
    -v playback_channels="$PLAYBACK_CHANNELS" \
    -v playback_rate="$PLAYBACK_RATE" \
    -v capture_name="$CAPTURE_NAME" \
    -v capture_card="$CAPTURE_CARD" \
    -v capture_device="$CAPTURE_DEVICE_NUM" \
    -v capture_channels="$CAPTURE_CHANNELS" \
    -v capture_rate="$CAPTURE_RATE" \
    -v capture_dsnoop_suffix="$CAPTURE_DSNOOP_SUFFIX" \
    -v capture_dsnoop_comment="$CAPTURE_DSNOOP_COMMENT" \
    -v capture_dsnoop_block="$CAPTURE_DSNOOP_BLOCK" '
{
    line = $0
    gsub(/{{PLAYBACK_NAME}}/, playback_name, line)
    gsub(/{{PLAYBACK_CARD}}/, playback_card, line)
    gsub(/{{PLAYBACK_DEVICE}}/, playback_device, line)
    gsub(/{{PLAYBACK_CHANNELS}}/, playback_channels, line)
    gsub(/{{PLAYBACK_RATE}}/, playback_rate, line)
    gsub(/{{CAPTURE_NAME}}/, capture_name, line)
    gsub(/{{CAPTURE_CARD}}/, capture_card, line)
    gsub(/{{CAPTURE_DEVICE}}/, capture_device, line)
    gsub(/{{CAPTURE_CHANNELS}}/, capture_channels, line)
    gsub(/{{CAPTURE_RATE}}/, capture_rate, line)
    gsub(/{{CAPTURE_DSNOOP_SUFFIX}}/, capture_dsnoop_suffix, line)
    gsub(/{{CAPTURE_DSNOOP_COMMENT}}/, capture_dsnoop_comment, line)

    # Handle dsnoop block
    if (line ~ /{{CAPTURE_DSNOOP_BLOCK}}/) {
        if (capture_dsnoop_block != "") {
            print capture_dsnoop_block
        }
        next
    }

    print line
}
' "$OUTPUT_FILE" > "$OUTPUT_FILE.tmp"

mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"

echo "Generated: $OUTPUT_FILE"
echo "  Playback: $PLAYBACK_NAME ($PLAYBACK_CARD)"
echo "  Capture:  $CAPTURE_NAME ($CAPTURE_CARD)"
