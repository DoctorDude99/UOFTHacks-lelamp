# LeLamp ALSA Audio Configuration

## Overview

This directory contains ALSA configuration files for different hardware setups. All configurations provide **abstract device names** that allow applications to work across different hardware without code changes.

## Abstract Device Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Application Layer                                      │
│  (livekit, spotifyd, sox, aplay, etc.)                  │
│  Always use: lelamp_playback / lelamp_capture           │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Abstraction Layer (defined in asound.conf)             │
│  - lelamp_playback: Abstract output device              │
│  - lelamp_capture: Abstract input device                │
│  - Automatic rate/format conversion via 'plug'          │
│  - Shared access via 'dmix'                             │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Hardware Layer                                         │
│  Real devices: UACDemoV10, Waveshare, ReSpeaker, etc.  │
└─────────────────────────────────────────────────────────┘
```

## Device Names

### For Applications (use these in your code)

| Device Name       | Purpose                          | Example Usage                    |
|-------------------|----------------------------------|----------------------------------|
| `lelamp_playback` | Audio output (speakers)          | `aplay -D lelamp_playback`       |
| `lelamp_capture`  | Audio input (microphone)         | `arecord -D lelamp_capture`      |
| `default`         | System default (both directions) | `play audio.mp3`                 |

### Benefits

✅ **Hardware Independence**: Applications don't need to know about specific hardware
✅ **Easy Hardware Swapping**: Just change `/etc/asound.conf`, no code changes
✅ **Multiple App Support**: dmix allows simultaneous playback (Spotify + LiveKit + system sounds)
✅ **Automatic Conversion**: plug handles sample rate/format conversion automatically

## Available Configurations

### asound-halox.conf
- **Playback**: UACDemoV10 (HaloX USB Audio)
- **Capture**: Centerm Camera (USB microphone)
- **Sample Rate**: 48000 Hz stereo

### asound-waveshare_usbaudio.conf
- **Playback**: Waveshare USB PnP Audio Device
- **Capture**: Centerm Camera (USB microphone)
- **Sample Rate**: 48000 Hz stereo

### asound-respeaker-v1.conf (if exists)
- **Playback**: ReSpeaker 2-Mic HAT
- **Capture**: ReSpeaker 2-Mic array
- **Sample Rate**: 48000 Hz stereo

## Activating a Configuration

To switch hardware configurations:

```bash
# Copy the desired config to /etc/asound.conf
sudo cp /home/halox/boxbots_lelampruntime/system/asound/asound-waveshare_usbaudio.conf /etc/asound.conf

# Restart audio applications
sudo systemctl restart lelamp.service  # if using systemd
# or kill and restart your applications
```

## Sample Rate & Format Conversion

All configurations use **48000 Hz stereo** as the hardware rate. The `plug` plugin automatically converts:

| Input Format      | Conversion                | Output to Hardware |
|-------------------|---------------------------|---------------------|
| 44.1kHz stereo    | Resample to 48kHz         | 48kHz stereo        |
| 96kHz stereo      | Downsample to 48kHz       | 48kHz stereo        |
| 22.05kHz mono     | Resample + upmix          | 48kHz stereo        |
| 16-bit            | No conversion needed      | 16-bit              |
| 24-bit            | Convert to 16-bit         | 16-bit              |

**No application changes needed** - ALSA handles conversion transparently!

## dmix (Multiple Application Support)

The `dmix` plugin allows multiple applications to share the same audio output:

```
┌──────────┐
│ Spotify  │───┐
└──────────┘   │
               ├──► dmix ──► Hardware Speaker
┌──────────┐   │
│ LiveKit  │───┘
└──────────┘
```

**Key points:**
- Multiple apps can play simultaneously
- Audio is mixed in software
- No "device busy" errors
- Shared buffer configuration (1024 period, 4096 buffer)

## Testing Your Configuration

### Test Playback
```bash
# Test with sox
play /path/to/audio.mp3

# Test with aplay (explicit device)
aplay -D lelamp_playback /path/to/audio.wav

# Test sample rate conversion
sox -n -r 44100 -c 2 test_44k.wav synth 1 sine 440
aplay -D lelamp_playback test_44k.wav  # Auto-converts to 48kHz
```

### Test Capture
```bash
# Record 3 seconds
arecord -D lelamp_capture -d 3 -f cd test.wav

# Record and immediately play back
arecord -D lelamp_capture -f cd | aplay -D lelamp_playback
```

### Test Multi-App Sharing
```bash
# Terminal 1
play music.mp3 -D lelamp_playback

# Terminal 2 (while music is playing)
aplay -D lelamp_playback sound_effect.wav  # Should mix together
```

## Creating New Configurations

When adding support for new hardware:

1. **Identify hardware card names:**
   ```bash
   aplay -l   # List playback devices
   arecord -l # List capture devices
   ```

2. **Copy an existing config:**
   ```bash
   cp asound-waveshare_usbaudio.conf asound-mydevice.conf
   ```

3. **Update the hardware layer:**
   - Change `card` name in `hw_playback_dmix`
   - Change `card` name in `hw_capture`
   - Adjust `rate`, `channels` if needed

4. **Keep abstract layer unchanged:**
   - DO NOT change `lelamp_playback` or `lelamp_capture` definitions
   - These must remain consistent across all configs

## Application Integration Examples

### Python (sounddevice)
```python
import sounddevice as sd
sd.default.device = ('lelamp_capture', 'lelamp_playback')
```

### LiveKit Agent
```python
# In your agent code
mic = rtc.Microphone(device='lelamp_capture')
speaker = rtc.Speaker(device='lelamp_playback')
```

### Spotifyd (Spotify Connect)
```toml
# In /etc/spotifyd.conf
[global]
device_name = "LeLamp"
backend = "alsa"
device = "lelamp_playback"  # Uses abstract device name
mixer = "Master"
```

### Sox/Play
```bash
# Just use default (already mapped to lelamp devices)
play audio.mp3

# Or explicit
play audio.mp3 -t alsa lelamp_playback
```

## Troubleshooting

### "Device or resource busy"
- dmix should prevent this, but if it happens:
  ```bash
  fuser -v /dev/snd/*  # Find processes using audio
  ```

### Wrong device playing/recording
```bash
# Check current config
cat /etc/asound.conf

# List all ALSA PCM devices
aplay -L | grep lelamp
```

### Audio quality issues
- Check if sample rate matches hardware capability
- Verify cables/connections
- Test with: `speaker-test -D lelamp_playback -t wav`

### No sound
```bash
# Check hardware is detected
aplay -l

# Check ALSA mixer levels
alsamixer

# Test direct hardware access
aplay -D hw:1,0 test.wav  # Replace 1,0 with your card,device
```

## Technical Details

### Why 48000 Hz?

Most modern USB audio devices support 48kHz natively. This is the standard for:
- Professional audio equipment
- Video production (48kHz is standard for video)
- VoIP/conferencing systems
- USB audio specifications

### dmix Configuration

```
ipc_key 1024        # Shared memory key (must be unique)
ipc_perm 0666       # Permissions for shared memory (allows multi-user/process access)
period_size 1024    # Samples per interrupt (~21ms at 48kHz)
buffer_size 4096    # Total buffer (4x period, ~85ms latency)
```

**Key parameters:**
- `ipc_key`: Unique identifier for the shared memory segment (avoid conflicts with other dmix instances)
- `ipc_perm 0666`: Allows any user/process to access the dmix device (prevents "permission denied" errors)
- Larger buffers = more latency but fewer dropouts. Adjust for your use case.

### plug Plugin Capabilities

The `plug` plugin handles:
- Sample rate conversion (any rate → 48000 Hz)
- Channel mapping (mono ↔ stereo)
- Sample format conversion (8/16/24/32-bit, signed/unsigned)
- Byte order conversion (little/big endian)
- Automatic device format negotiation

## See Also

- [ALSA Project Documentation](https://www.alsa-project.org/wiki/Asoundrc)
- [dmix Documentation](https://alsa.opensrc.org/Dmix)
- LeLamp Audio Service: `lelamp/service/audio/`
