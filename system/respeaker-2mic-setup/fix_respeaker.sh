#!/bin/bash
#
# fix_respeaker.sh - Setup script for ReSpeaker 2-Mics Pi HAT
#
# This script configures the correct audio overlay based on your board version
# and installs the ALSA configuration for proper audio routing.
#
# Usage: sudo ./fix_respeaker.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "  ReSpeaker 2-Mics Pi HAT Setup Script"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Please run as root (sudo ./fix_respeaker.sh)${NC}"
    exit 1
fi

# Detect config.txt location
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo -e "${RED}Error: Cannot find config.txt${NC}"
    exit 1
fi

echo "Config file: $CONFIG_FILE"
echo ""

# Detect board version via I2C
echo "Detecting board version via I2C..."

# Enable i2c if not already
if ! command -v i2cdetect &> /dev/null; then
    echo "Installing i2c-tools..."
    apt-get update && apt-get install -y i2c-tools
fi

# Check I2C bus 1
I2C_OUTPUT=$(i2cdetect -y 1 2>/dev/null || echo "error")

if echo "$I2C_OUTPUT" | grep -q "error"; then
    echo -e "${YELLOW}Warning: Could not scan I2C bus. Is the HAT connected?${NC}"
    echo ""
    echo "Please specify your board version manually:"
    echo "  1) v1.x (v1.0, v1.2, etc.) - WM8960 codec"
    echo "  2) v2.0 - TLV320AIC3X codec"
    read -p "Enter choice [1/2]: " CHOICE

    case $CHOICE in
        1) BOARD_VERSION="v1" ;;
        2) BOARD_VERSION="v2" ;;
        *) echo -e "${RED}Invalid choice${NC}"; exit 1 ;;
    esac
else
    # Check for WM8960 at 0x1a
    if echo "$I2C_OUTPUT" | grep -q "1a"; then
        BOARD_VERSION="v1"
        echo -e "${GREEN}Detected: WM8960 codec at 0x1a (v1.x board)${NC}"
    # Check for TLV320AIC3X at 0x18
    elif echo "$I2C_OUTPUT" | grep -q "18"; then
        BOARD_VERSION="v2"
        echo -e "${GREEN}Detected: TLV320AIC3X codec at 0x18 (v2.0 board)${NC}"
    else
        echo -e "${YELLOW}Warning: No audio codec detected on I2C bus${NC}"
        echo "Make sure the HAT is properly seated on the GPIO pins."
        echo ""
        echo "Please specify your board version manually:"
        echo "  1) v1.x (v1.0, v1.2, etc.) - WM8960 codec"
        echo "  2) v2.0 - TLV320AIC3X codec"
        read -p "Enter choice [1/2]: " CHOICE

        case $CHOICE in
            1) BOARD_VERSION="v1" ;;
            2) BOARD_VERSION="v2" ;;
            *) echo -e "${RED}Invalid choice${NC}"; exit 1 ;;
        esac
    fi
fi

echo ""

# Set overlay based on version
if [ "$BOARD_VERSION" = "v1" ]; then
    OVERLAY="wm8960-soundcard"
    CARD_NAME="wm8960soundcard"
    OLD_OVERLAY="respeaker-2mic-v2_0-overlay"
else
    OVERLAY="respeaker-2mic-v2_0-overlay"
    CARD_NAME="seeed2micvoicec"
    OLD_OVERLAY="wm8960-soundcard"
fi

echo "Configuring for: $BOARD_VERSION board"
echo "Using overlay: $OVERLAY"
echo ""

# Backup config.txt
BACKUP_FILE="${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
cp "$CONFIG_FILE" "$BACKUP_FILE"
echo "Backed up config to: $BACKUP_FILE"

# Remove any existing respeaker/wm8960 overlays
sed -i '/dtoverlay=respeaker-2mic-v2_0-overlay/d' "$CONFIG_FILE"
sed -i '/dtoverlay=wm8960-soundcard/d' "$CONFIG_FILE"
sed -i '/dtoverlay=seeed-voicecard/d' "$CONFIG_FILE"
sed -i '/dtoverlay=i2s-mmap/d' "$CONFIG_FILE"

# Check if [all] section exists
if grep -q "^\[all\]" "$CONFIG_FILE"; then
    # Add overlay after [all] section
    sed -i "/^\[all\]/a dtoverlay=$OVERLAY" "$CONFIG_FILE"
else
    # Add [all] section and overlay at end
    echo "" >> "$CONFIG_FILE"
    echo "[all]" >> "$CONFIG_FILE"
    echo "dtoverlay=$OVERLAY" >> "$CONFIG_FILE"
fi

echo -e "${GREEN}Updated $CONFIG_FILE with dtoverlay=$OVERLAY${NC}"

# Install asound.conf
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASOUND_SRC="$SCRIPT_DIR/asound.conf"

if [ -f "$ASOUND_SRC" ]; then
    # Update card name in asound.conf based on board version
    sed "s/CARD_NAME_PLACEHOLDER/$CARD_NAME/g" "$ASOUND_SRC" > /etc/asound.conf
    echo -e "${GREEN}Installed /etc/asound.conf${NC}"
else
    echo -e "${YELLOW}Warning: asound.conf not found in script directory${NC}"
    echo "You may need to configure /etc/asound.conf manually."
fi

# Create mixer setup script that runs after reboot
MIXER_SCRIPT="/usr/local/bin/respeaker-mixer-init"

if [ "$BOARD_VERSION" = "v1" ]; then
    cat > "$MIXER_SCRIPT" << 'MIXER_EOF'
#!/bin/bash
# ReSpeaker 2-Mic HAT (WM8960) Mixer Initialization
# This script enables the PCM playback path and sets volumes

CARD="wm8960soundcard"

# Wait for sound card to be available
for i in {1..30}; do
    if amixer -c "$CARD" info &>/dev/null; then
        break
    fi
    sleep 1
done

# CRITICAL: Enable PCM playback path through output mixers
# Without these, audio will not reach the speakers!
amixer -c "$CARD" cset numid=52 on  # Left Output Mixer PCM Playback Switch
amixer -c "$CARD" cset numid=55 on  # Right Output Mixer PCM Playback Switch

# Set playback volumes to reasonable levels
amixer -c "$CARD" sset 'Speaker' 100%
amixer -c "$CARD" sset 'Playback' 100%
amixer -c "$CARD" sset 'Headphone' 100%

# Set capture volumes
amixer -c "$CARD" sset 'Capture' 100%

echo "ReSpeaker WM8960 mixer initialized"
MIXER_EOF
else
    cat > "$MIXER_SCRIPT" << 'MIXER_EOF'
#!/bin/bash
# ReSpeaker 2-Mic HAT v2.0 (TLV320AIC3X) Mixer Initialization

CARD="seeed2micvoicec"

# Wait for sound card to be available
for i in {1..30}; do
    if amixer -c "$CARD" info &>/dev/null; then
        break
    fi
    sleep 1
done

# Set playback and capture volumes
amixer -c "$CARD" sset 'PCM' 100%
amixer -c "$CARD" sset 'Line' 100%

echo "ReSpeaker TLV320AIC3X mixer initialized"
MIXER_EOF
fi

chmod +x "$MIXER_SCRIPT"
echo -e "${GREEN}Installed mixer init script: $MIXER_SCRIPT${NC}"

# Create systemd service to run mixer init at boot
cat > /etc/systemd/system/respeaker-mixer.service << EOF
[Unit]
Description=ReSpeaker Mixer Initialization
After=sound.target
Wants=sound.target

[Service]
Type=oneshot
ExecStart=$MIXER_SCRIPT
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable respeaker-mixer.service
echo -e "${GREEN}Enabled respeaker-mixer.service to run at boot${NC}"

echo ""
echo "============================================"
echo -e "${GREEN}  Setup Complete!${NC}"
echo "============================================"
echo ""
echo "Changes made:"
echo "  - Configured overlay: $OVERLAY"
echo "  - Installed ALSA config: /etc/asound.conf"
echo "  - Installed mixer init script: $MIXER_SCRIPT"
echo "  - Enabled systemd service: respeaker-mixer.service"
echo ""
echo -e "${YELLOW}You must reboot for changes to take effect:${NC}"
echo ""
echo "    sudo reboot"
echo ""
echo "After reboot, test with:"
echo "    aplay -D plughw:$CARD_NAME,0 /usr/share/sounds/alsa/Front_Center.wav"
echo "    arecord -D plughw:$CARD_NAME,0 -f S16_LE -r 48000 -c 2 -d 5 test.wav"
echo ""
echo "If audio still doesn't work, manually run:"
echo "    sudo $MIXER_SCRIPT"
echo ""
