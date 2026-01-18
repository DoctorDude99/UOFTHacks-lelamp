#!/bin/bash
# Setup ALSA loopback for processed audio routing
# This creates a virtual device that our audio router writes to,
# and LiveKit reads from.

set -e

echo "Setting up ALSA loopback for audio processing..."

# Load snd-aloop module
if ! lsmod | grep -q snd_aloop; then
    echo "Loading snd-aloop module..."
    sudo modprobe snd-aloop index=10 pcm_substreams=1

    # Add to modules for persistence
    if ! grep -q "snd-aloop" /etc/modules 2>/dev/null; then
        echo "snd-aloop index=10 pcm_substreams=1" | sudo tee -a /etc/modules
        echo "Added snd-aloop to /etc/modules for persistence"
    fi
else
    echo "snd-aloop already loaded"
fi

# Verify loopback is available
echo ""
echo "Checking loopback device..."
aplay -l | grep -i loopback || {
    echo "ERROR: Loopback device not found!"
    exit 1
}

echo ""
echo "Loopback device setup complete!"
echo ""
echo "Loopback devices:"
echo "  - Write processed audio to: hw:Loopback,0,0"
echo "  - LiveKit reads from:       hw:Loopback,1,0"
echo ""
echo "Next: Update /etc/asound.conf to route through loopback"
