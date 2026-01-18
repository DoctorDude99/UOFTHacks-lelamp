#!/bin/bash
#
# update-raspotify-name.sh - Safely update Raspotify device name
#
# This script is designed to be called with sudo from the LeLamp web interface.
# It validates input and safely updates the Raspotify configuration.
#

set -e

CONF_FILE="/etc/raspotify/conf"
NEW_NAME="$1"

# Validate input
if [ -z "$NEW_NAME" ]; then
    echo "Error: Device name required" >&2
    exit 1
fi

# Sanitize input - only allow alphanumeric, spaces, hyphens, underscores
if ! echo "$NEW_NAME" | grep -qE '^[a-zA-Z0-9 _-]+$'; then
    echo "Error: Invalid device name. Only letters, numbers, spaces, hyphens and underscores allowed." >&2
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONF_FILE" ]; then
    echo "Error: Raspotify config not found at $CONF_FILE" >&2
    exit 1
fi

# Update the config file
sed -i "s/^LIBRESPOT_NAME=.*/LIBRESPOT_NAME=\"$NEW_NAME\"/" "$CONF_FILE"

# Also update commented out lines (in case it's commented)
sed -i "s/^#LIBRESPOT_NAME=.*/LIBRESPOT_NAME=\"$NEW_NAME\"/" "$CONF_FILE"

echo "Raspotify device name updated to: $NEW_NAME"
exit 0
