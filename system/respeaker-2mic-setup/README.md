# ReSpeaker 2-Mics Pi HAT Setup Guide

## Overview

The [Seeed ReSpeaker 2-Mics Pi HAT](https://www.seeedstudio.com/ReSpeaker-2-Mics-Pi-HAT.html) is an audio HAT for Raspberry Pi with 2 microphones and a speaker output. There are two hardware versions with different audio codecs:

| Board Version | Codec Chip | I2C Address | Required Overlay |
|---------------|------------|-------------|------------------|
| v1.x (v1.0, v1.2, etc.) | WM8960 | 0x1a | `wm8960-soundcard` |
| v2.0 | TLV320AIC3X | 0x18 | `respeaker-2mic-v2_0-overlay` |

**Check your board version**: Look at the back of the HAT for a version number (e.g., "v1.2").

## The Problem

On Raspberry Pi OS Bookworm/Trixie (Debian 12/13), using the wrong overlay causes I2C communication errors:

```
tlv320aic3x 1-0018: ASoC: error at soc_component_read_no_lock
bcm2835-i2s fe203000.i2s: I2S SYNC error!
```

Symptoms:
- Card appears in `aplay -l` but audio doesn't work
- `speaker-test` fails with "Input/output error"
- `dmesg` shows I2C and I2S errors

## Quick Diagnosis

### 1. Check your board version
Look at the back of the physical board for version number.

### 2. Check I2C devices
```bash
sudo i2cdetect -y 1
```

- Device at `0x1a` = WM8960 (v1.x board)
- Device at `0x18` = TLV320AIC3X (v2.0 board)

### 3. Check current overlay
```bash
grep respeaker /boot/firmware/config.txt
grep wm8960 /boot/firmware/config.txt
```

## Solution

### For v1.x boards (WM8960)

Edit `/boot/firmware/config.txt`:
```bash
sudo nano /boot/firmware/config.txt
```

In the `[all]` section, use:
```
dtoverlay=wm8960-soundcard
```

Remove or comment out any `respeaker-2mic-v2_0-overlay` line.

### For v2.0 boards (TLV320AIC3X)

In the `[all]` section, use:
```
dtoverlay=respeaker-2mic-v2_0-overlay
```

### After editing, reboot:
```bash
sudo reboot
```

## Verifying It Works

After reboot:

```bash
# List audio devices
aplay -l

# For v1.x (WM8960), you should see:
# card X: wm8960soundcard [wm8960-soundcard], device 0: ...

# Test speaker output using plughw (handles format conversion)
aplay -D plughw:wm8960soundcard,0 /usr/share/sounds/alsa/Front_Center.wav

# Or play any wav file
play ~/path/to/your/file.wav

# Test recording
arecord -D plughw:wm8960soundcard,0 -f S16_LE -r 48000 -c 2 -d 5 test.wav
aplay -D plughw:wm8960soundcard,0 test.wav
```

**Note:** Use `plughw:` instead of `hw:` for automatic format conversion.

## ALSA Configuration

For applications that need a default audio device, copy the provided `asound.conf`:

```bash
sudo cp asound.conf /etc/asound.conf
```

This configuration:
- Sets the ReSpeaker as the default audio device
- Uses `dmix` for playback (allows multiple apps to play audio simultaneously)
- Uses `dsnoop` for capture (allows multiple apps to record simultaneously)

## Setting Volume (CRITICAL)

The WM8960 codec requires enabling the PCM playback path through the output mixers. **Without this step, you will get no audio output even with volumes at 100%.**

### Enable PCM Playback (Required!)

```bash
# CRITICAL: Enable PCM playback switches - audio won't work without these!
amixer -c wm8960soundcard cset numid=52 on  # Left Output Mixer PCM Playback Switch
amixer -c wm8960soundcard cset numid=55 on  # Right Output Mixer PCM Playback Switch
```

### Set Volumes

```bash
# Set speaker and playback volumes
amixer -c wm8960soundcard sset 'Speaker' 100%
amixer -c wm8960soundcard sset 'Playback' 100%
amixer -c wm8960soundcard sset 'Headphone' 100%

# Set capture volume for microphones
amixer -c wm8960soundcard sset 'Capture' 100%
```

### Using alsamixer

```bash
alsamixer -c wm8960soundcard
```

Note: The PCM playback switches are not visible in alsamixer - you must use the `amixer cset` commands above.

### Persist Settings Across Reboots

The `fix_respeaker.sh` script creates a systemd service that runs these commands at boot. If you set up manually, you can save settings with:

```bash
sudo alsactl store
```

## Version Confusion Clarified

People online mention "firmware 1.9" vs "2.1" compatibility issues. This refers to:

- **Seeed's seeed-voicecard driver package versions** - their GitHub repo has different releases
- **NOT the hardware board version**

The good news: Modern Raspberry Pi OS (Bookworm/Trixie) includes the `wm8960-soundcard` overlay in the kernel, so you don't need Seeed's custom driver package. Just use the built-in overlay.

## Troubleshooting

### Card not appearing at all
1. Check HAT is seated properly on GPIO pins
2. Verify overlay is in config.txt
3. Check `dmesg | grep -i wm8960` for errors

### Audio plays but no sound
1. **Enable PCM playback switches** (most common issue!):
   ```bash
   amixer -c wm8960soundcard cset numid=52 on
   amixer -c wm8960soundcard cset numid=55 on
   ```
2. Check speaker connection (3.5mm jack or JST connector)
3. Increase volume: `amixer -c wm8960soundcard sset 'Speaker' 100%`
4. Run the mixer init script: `sudo /usr/local/bin/respeaker-mixer-init`

### Microphone not working
1. Check capture volume: `amixer -c wm8960soundcard sset 'Capture' 80%`
2. Ensure correct device: `arecord -D hw:wm8960soundcard ...`

## Files in This Directory

- `README.md` - This documentation
- `fix_respeaker.sh` - Automated setup script (configures overlay, mixer, and systemd service)
- `asound.conf` - ALSA configuration for default audio routing

## What the Setup Script Does

The `fix_respeaker.sh` script:

1. **Detects your board version** via I2C (WM8960 at 0x1a or TLV320AIC3X at 0x18)
2. **Configures the correct overlay** in `/boot/firmware/config.txt`
3. **Installs ALSA config** to `/etc/asound.conf`
4. **Creates mixer init script** at `/usr/local/bin/respeaker-mixer-init` that:
   - Enables the PCM playback switches (numid=52, numid=55)
   - Sets Speaker, Playback, Headphone, and Capture volumes to 100%
5. **Creates systemd service** `respeaker-mixer.service` to run mixer init at boot
