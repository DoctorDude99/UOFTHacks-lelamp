# LeLamp v2 - Engineering Handover

This document outlines priority areas for the next engineer working on LeLamp.

## Project Overview

LeLamp is a voice-controlled robot lamp running on Raspberry Pi 5. The runtime uses LiveKit for real-time voice interaction, with servo motors, RGB LEDs, camera, and audio I/O.

**Key entry points:**
- `main.py` - Main runtime entry point
- `~/.lelamp/config.yaml` - Configuration
- `lelamp/` - Core package
- `install/` - Component installers
- `oem_install.sh` - Manufacturing provisioning script

## Priority Work Areas

### 1. VAD / Microphone Input / AEC

**Current state:** Using LiveKit's built-in VAD with Silero. Audio quality issues on hardware with the ReSpeaker 2-mic HAT.

**Issues to investigate:**
- Echo cancellation (AEC) not fully working - lamp sometimes responds to its own speech
- Background noise triggers false VAD activations
- VAD / Microphone needs fine tuning

**Files:**
- `lelamp/service/microphone/microphone_service.py` - Audio playback/recording
- `system/asound/` - ALSA configurations for different audio setups

**Suggestions:**
- Test with different parameters and values
- Consider implementing a simple energy-based pre-filter before VAD, High Pass Filter, AGC

### 2. MCP Testing

**Current state:** MCP (Model Context Protocol) server support is partially implemented but not fully tested.

**What needs testing:**
- Tool discovery and registration
- Bidirectional communication with MCP clients
- Error handling and reconnection logic
- Integration with workflow system

**Files:**
- Check MCP-related code in vclean branch
- LiveKit agent tool registration in `main.py`

### 3. Bug Fixes

**Known issues:**
- Workflow testing with Barge-In issues

# Run Full system
uv run main.py console
```

**Common hardware issues:**
- Motors getting hot after extended use - use sleep mode
- Camera not detected - check `/dev/video*` permissions
- USB-C Speaker pops during boot
- setcaps sometimes needs help in regards to the RGB Led, GPIO, Camera access, and General Linux Permissions

**Hardware variants:**
- USB-C Speaker
- Waveshare USB Dual Speaker
- ReSpeaker 2-mic HAT

### 5. Security & Auth Testing

**Areas needing review:**
- `.env` file permissions and handling
- LiveKit token generation and expiry
- Hub API authentication (`HUB_URL`, `HUB_API_KEY`)
- WiFi AP mode security (WPA2-PSK with default password)
- SSH with default credentials post-OEM install

**Security hardening TODOs:**
- Force password change on first login
- Add rate limiting to WebUI API
- Audit workflow / MCP tool execution for injection risks

**Test scenarios:**
- Test API endpoints without auth
- Check for sensitive data in logs
- Validate input sanitization in voice commands
- Analyze Data Collection / Privacy

## Development Setup

```bash
# Clone and install
git clone https://github.com/humancomputerlab/lelampv2.git
cd lelampv2
./oem_install.sh

# Run locally (needs .env with API keys)
uv run main.py console
```

## Useful Commands

```bash
# Service management
sudo systemctl status lelamp.service
sudo systemctl start lelamp.service
sudo systemctl stop lelamp.service
sudo systemctl restart lelamp.service
sudo systemctl enable lelamp.service
sudo systemctl disable lelamp.service
sudo journalctl -u lelamp.service -f

# Database queries
sqlite3 lelamp.db "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT 5"
sqlite3 lelamp.db "SELECT * FROM workflow_errors"

```
