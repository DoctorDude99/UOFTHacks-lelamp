"""
Theme Service for LeLamp

Provides themed audio playback with support for custom sound themes.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Optional
from enum import Enum


class ThemeSound(Enum):
    """Standard theme sound names"""
    STARTUP = "Startup"
    SHUTDOWN = "Shutdown"
    REBOOT = "Reboot"
    SLEEP = "Sleep"
    ACTIVATE = "Activate"
    ALERT = "Alert"
    NOTIFY = "Notify"
    CALIBRATION_COMPLETE = "CalibrationComplete"
    FACE_DETECT = "FaceDetect"
    MANUAL_MODE = "ManualMode"
    PUSHABLE = "Pushable"
    PRESS = "Press"


# Global instance
_theme_service: Optional['ThemeService'] = None


def get_theme_service() -> Optional['ThemeService']:
    """Get the global ThemeService instance"""
    return _theme_service


def init_theme_service(theme_name: str = "Lelamp", assets_dir: str = "assets/Theme") -> 'ThemeService':
    """Initialize the global ThemeService instance"""
    global _theme_service
    _theme_service = ThemeService(theme_name=theme_name, assets_dir=assets_dir)
    return _theme_service


class ThemeService:
    """
    Service for playing themed audio sounds.

    Themes are stored in assets/Theme/{theme_name}/audio/
    Each theme can have the following sounds:
    - Startup.wav - System boot
    - Shutdown.wav - System shutdown
    - Reboot.wav - System reboot
    - Sleep.wav - Going to sleep
    - Activate.wav - Generic activation
    - Alert.wav - Alarm/alert sound
    - Notify.wav - Notification/timer/mic ready
    - CalibrationComplete.wav - Calibration finished
    - FaceDetect.wav - Face first detected
    - ManualMode.wav - Manual motor control enabled
    - Pushable.wav - Pushable mode enabled
    - Press.wav - Button press feedback

    If a sound is missing from a theme, it will be silently skipped.
    """

    def __init__(self, theme_name: str = "Lelamp", assets_dir: str = "assets/Theme"):
        """
        Initialize the theme service.

        Args:
            theme_name: Name of the theme folder
            assets_dir: Root directory for themes
        """
        self.assets_dir = Path(assets_dir)
        self.theme_name = theme_name
        self.logger = logging.getLogger(__name__)

        # Validate theme exists
        self.theme_path = self.assets_dir / theme_name / "audio"
        if not self.theme_path.exists():
            self.logger.warning(f"Theme '{theme_name}' not found at {self.theme_path}")
        else:
            self.logger.info(f"ThemeService initialized with theme '{theme_name}'")
            self._log_available_sounds()

    def _log_available_sounds(self):
        """Log which sounds are available in the current theme"""
        available = []
        for sound in ThemeSound:
            path = self.theme_path / f"{sound.value}.wav"
            if path.exists():
                available.append(sound.value)
        self.logger.info(f"Available theme sounds: {', '.join(available)}")

    def set_theme(self, theme_name: str) -> bool:
        """
        Switch to a different theme.

        Args:
            theme_name: Name of the theme folder

        Returns:
            True if theme was found and set, False otherwise
        """
        new_path = self.assets_dir / theme_name / "audio"
        if not new_path.exists():
            self.logger.error(f"Theme '{theme_name}' not found at {new_path}")
            return False

        self.theme_name = theme_name
        self.theme_path = new_path
        self.logger.info(f"Switched to theme '{theme_name}'")
        self._log_available_sounds()
        return True

    def get_sound_path(self, sound: ThemeSound) -> Optional[Path]:
        """
        Get the file path for a theme sound.

        Args:
            sound: The ThemeSound to get

        Returns:
            Path to the sound file, or None if it doesn't exist
        """
        path = self.theme_path / f"{sound.value}.wav"
        if path.exists():
            return path
        return None

    def play(self, sound: ThemeSound, blocking: bool = False) -> bool:
        """
        Play a theme sound.

        Args:
            sound: The ThemeSound to play
            blocking: If True, wait for sound to finish

        Returns:
            True if sound was played, False if not found
        """
        path = self.get_sound_path(sound)
        if not path:
            self.logger.debug(f"Theme sound '{sound.value}' not found, skipping")
            return False

        return self._play_file(str(path), blocking)

    def _play_file(self, file_path: str, blocking: bool = False) -> bool:
        """
        Play an audio file using aplay.

        Args:
            file_path: Path to the audio file
            blocking: If True, wait for playback to finish

        Returns:
            True if playback started/completed successfully
        """
        try:
            # cmd = ["aplay", "-q", "-D", "lelamp_playback", file_path]
            import sounddevice as sd
            import soundfile as sf
            data, fs = sf.read(file_path)
            sd.play(data, fs)
            if blocking:
                sd.wait()
                # subprocess.run(cmd, timeout=30, check=False)
            else:
                pass
                # subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            self.logger.debug(f"Playing theme sound: {file_path}")
            return True

        except subprocess.TimeoutExpired:
            self.logger.warning(f"Sound playback timed out: {file_path}")
            return False
        except FileNotFoundError:
            self.logger.error("aplay not found - audio playback unavailable")
            return False
        except Exception as e:
            self.logger.error(f"Error playing sound {file_path}: {e}")
            return False

    def list_themes(self) -> list:
        """
        List all available themes.

        Returns:
            List of theme names
        """
        themes = []
        if self.assets_dir.exists():
            for item in self.assets_dir.iterdir():
                if item.is_dir() and (item / "audio").exists():
                    themes.append(item.name)
        return sorted(themes)

    def get_theme_info(self, theme_name: Optional[str] = None) -> dict:
        """
        Get information about a theme.

        Args:
            theme_name: Theme to get info for (default: current theme)

        Returns:
            Dict with theme info including available sounds
        """
        if theme_name is None:
            theme_name = self.theme_name

        theme_path = self.assets_dir / theme_name / "audio"
        if not theme_path.exists():
            return {"name": theme_name, "exists": False, "sounds": []}

        sounds = []
        for sound in ThemeSound:
            path = theme_path / f"{sound.value}.wav"
            if path.exists():
                sounds.append({
                    "name": sound.value,
                    "file": str(path),
                    "exists": True
                })
            else:
                sounds.append({
                    "name": sound.value,
                    "file": None,
                    "exists": False
                })

        return {
            "name": theme_name,
            "exists": True,
            "path": str(theme_path),
            "sounds": sounds
        }
