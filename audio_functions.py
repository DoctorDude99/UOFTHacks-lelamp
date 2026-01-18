"""
Audio function tools for LeLamp

This module contains all audio-related function tools including:
- Volume control
- Sound effect playback
- Sound library browsing
- Sound searching
"""

import logging
import subprocess
from typing import Optional
from lelamp.service.agent.tools import Tool

class AudioFunctions:
    """Mixin class providing audio control function tools"""

    @Tool.register_tool
    async def set_volume(self, volume_percent: int) -> str:
        """
        Control system audio volume for better interaction experience! Use this when users ask
        you to be louder, quieter, or set a specific volume level. Perfect for adjusting to
        room conditions, user preferences, or creating dramatic audio effects during conversations.
        Use when someone says "turn it up", "lower the volume", "I can't hear you", or gives
        specific volume requests. Great for being considerate of your environment!

        Args:
            volume_percent: Volume level as percentage (0-100). 0=mute, 50=half volume, 100=max
        """
        from lelamp.globals import CONFIG, save_config

        print(f"LeLamp: set_volume function called with volume: {volume_percent}%")
        try:
            # Validate volume range
            if not 0 <= volume_percent <= 100:
                return "Error: Volume must be between 0 and 100 percent"

            # Use the internal helper function
            self._set_system_volume(volume_percent)

            # Save to config for persistence
            CONFIG["volume"] = volume_percent
            save_config(CONFIG)

            result = f"Set speaker volume to {volume_percent}%"
            return result

        except subprocess.TimeoutExpired:
            result = "Error: Volume control command timed out"
            print(result)
            return result
        except FileNotFoundError:
            result = "Error: amixer command not found on system"
            print(result)
            return result
        except Exception as e:
            result = f"Error controlling volume: {str(e)}"
            print(result)
            return result

    @Tool.register_tool
    async def set_microphone_volume(self, volume_percent: int) -> str:
        """
        Control microphone/input volume for voice capture sensitivity! Use this when users say
        the microphone is too quiet or too sensitive, or when there's background noise issues.
        Higher values make the mic more sensitive (picks up quieter speech but also more noise),
        lower values reduce sensitivity (needs louder speech but less noise pickup).

        Typical values:
        - 50-60%: Quiet environment, close speaking
        - 70-80%: Normal room conditions (recommended default)
        - 90-100%: Noisy environment or distant speaking

        Args:
            volume_percent: Microphone sensitivity as percentage (0-100). 0=mute, 80=default
        """
        from lelamp.globals import CONFIG, save_config

        print(f"LeLamp: set_microphone_volume function called with volume: {volume_percent}%")
        try:
            # Validate volume range
            if not 0 <= volume_percent <= 100:
                return "Error: Microphone volume must be between 0 and 100 percent"

            # Use the internal helper function
            self._set_system_microphone_volume(volume_percent)

            # Save to config for persistence
            CONFIG["microphone_volume"] = volume_percent
            save_config(CONFIG)

            result = f"Set microphone volume to {volume_percent}%"
            return result

        except subprocess.TimeoutExpired:
            result = "Error: Microphone volume control command timed out"
            print(result)
            return result
        except FileNotFoundError:
            result = "Error: amixer command not found on system"
            print(result)
            return result
        except Exception as e:
            result = f"Error controlling microphone volume: {str(e)}"
            print(result)
            return result

    @Tool.register_tool
    async def play_sound_effect(self, sound_name: str) -> str:
        """
        Play a sound effect to enhance your expressiveness! Use sounds to punctuate moments,
        create atmosphere, or respond to events. Perfect for: celebrations (success sounds),
        errors (alert sounds), thinking (processing sounds), transitions, or dramatic moments.

        You have a library of sci-fi sounds including: alerts, success chimes, errors, data
        processing, calculations, digitization, lift-off, and more.

        Use sounds sparingly for maximum impact - too many sounds can be overwhelming!

        Args:
            sound_name: Name or description of the sound (e.g., "success", "alert", "error",
                       "data received", "calculation", "lift off"). The system will search
                       for matching sounds.

        Returns:
            Confirmation that sound is playing
        """
        print(f"LeLamp: play_sound_effect called with sound_name: {sound_name}")
        try:
            # Search for matching sounds
            matches = self.audio_service.search_sounds(sound_name)

            if not matches:
                return f"No sound found matching '{sound_name}'. Try listing available sounds first."

            # Play the first match
            sound_id = matches[0]
            self.audio_service.play(sound_id, volume=100, blocking=False)

            sound_info = self.audio_service.get_sound_info(sound_id)
            return f"Playing sound: {sound_info['name']} from {sound_info['category']}"

        except Exception as e:
            return f"Error playing sound: {str(e)}"

    @Tool.register_tool
    async def list_available_sounds(self, category: Optional[str] = None) -> str:
        """
        Get a list of all available sound effects you can play. Use this when you want to
        explore what sounds you have access to, or when searching for a specific type of sound.

        Args:
            category: Optional category filter (e.g., "Effects", "Emotions"). If None, lists all categories.

        Returns:
            List of available sounds organized by category
        """
        print(f"LeLamp: list_available_sounds called with category: {category}")
        try:
            if category:
                # List sounds in specific category
                sounds = self.audio_service.get_sounds_by_category(category)
                if not sounds:
                    return f"No sounds found in category '{category}'"

                result_lines = [f"Sounds in {category}:"]
                for sound_id in sounds[:20]:  # Limit to 20 to avoid overwhelming
                    sound_info = self.audio_service.get_sound_info(sound_id)
                    result_lines.append(f"  - {sound_info['name']}")

                if len(sounds) > 20:
                    result_lines.append(f"  ... and {len(sounds) - 20} more")

                return "\n".join(result_lines)
            else:
                # List all categories
                categories = self.audio_service.get_categories()
                total_sounds = len(self.audio_service.sounds)

                result_lines = [f"Available sound categories ({total_sounds} total sounds):"]
                for cat in categories:
                    cat_sounds = self.audio_service.get_sounds_by_category(cat)
                    result_lines.append(f"  - {cat}: {len(cat_sounds)} sounds")

                result_lines.append("\nUse list_available_sounds(category='Effects') to see sounds in a specific category")
                return "\n".join(result_lines)

        except Exception as e:
            return f"Error listing sounds: {str(e)}"

    @Tool.register_tool
    async def search_sounds(self, query: str) -> str:
        """
        Search for specific sounds by name or keyword. Use this when you need a particular
        type of sound but don't know the exact name.

        Examples:
        - search_sounds("success") - Find success/completion sounds
        - search_sounds("alert") - Find alert/warning sounds
        - search_sounds("data") - Find data processing sounds

        Args:
            query: Search term to find matching sounds

        Returns:
            List of matching sounds
        """
        print(f"LeLamp: search_sounds called with query: {query}")
        try:
            matches = self.audio_service.search_sounds(query)

            if not matches:
                return f"No sounds found matching '{query}'"

            result_lines = [f"Sounds matching '{query}':"]
            for sound_id in matches[:15]:  # Limit to 15
                sound_info = self.audio_service.get_sound_info(sound_id)
                result_lines.append(f"  - {sound_info['name']} ({sound_info['category']})")

            if len(matches) > 15:
                result_lines.append(f"  ... and {len(matches) - 15} more")

            return "\n".join(result_lines)

        except Exception as e:
            return f"Error searching sounds: {str(e)}"
