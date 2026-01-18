"""
Motor control function tools for LeLamp

This module contains all motor-related function tools including:
- Motor preset management (Gentle/Normal/Sport modes)
- Pushable mode control
"""

import logging
from lelamp.service.agent.tools import Tool


class MotorFunctions:
    """Mixin class providing motor control function tools"""

    def _check_motors_enabled(self) -> str:
        """Check if motors are enabled. Returns error message if disabled, None if enabled."""
        if not getattr(self, 'motors_enabled', True):
            return "Motors are not available - running in headless mode without motor hardware."
        if not getattr(self, 'animation_service', None):
            return "Motor control is not available - animation service not initialized."
        return None

    @Tool.register_tool
    async def set_motor_preset(self, preset: str) -> str:
        """
        Change how your motors behave! Switch between movement presets to adjust your
        physical responsiveness. Use this when someone asks you to be more gentle, more
        energetic, or to change your movement style.

        - "Gentle" - Soft, slow movements. Easy for humans to push/guide you. Safe mode.
        - "Normal" - Balanced responsiveness. Good for everyday interactions.
        - "Sport" - Snappy, fast movements. More resistant to being pushed. Energetic mode.

        Args:
            preset: The movement preset to use - "Gentle", "Normal", or "Sport"
        """
        # Check if motors are available
        error = self._check_motors_enabled()
        if error:
            return error

        from lelamp.globals import CONFIG, save_config

        print(f"LeLamp: set_motor_preset function called with preset: {preset}")
        try:
            # Normalize preset name
            preset_normalized = preset.strip().capitalize()
            available = self.animation_service.get_available_presets()

            if preset_normalized not in available:
                return f"Unknown preset '{preset}'. Available presets: {', '.join(available)}"

            success = self.animation_service.apply_preset(preset_normalized)
            if success:
                # Update config file to persist the change
                CONFIG["motor_preset"] = preset_normalized
                save_config(CONFIG)
                return f"Switched to {preset_normalized} mode. Motors are now {'softer and easier to move' if preset_normalized == 'Gentle' else 'more responsive' if preset_normalized == 'Normal' else 'snappy and energetic'}!"
            else:
                return f"Failed to apply preset {preset_normalized}"
        except Exception as e:
            return f"Error setting motor preset: {str(e)}"

    @Tool.register_tool
    async def set_pushable_mode(self, enabled: bool) -> str:
        """
        Enable or disable pushable mode - allows humans to physically move you by hand!

        When ENABLED (True):
        - You become soft and compliant, easy to push around
        - Animations are paused - you hold still
        - Humans can position you like a desk lamp to shine light where they need it
        - You'll hold whatever position they put you in
        - Use when someone says: "let me move you", "hold still", "stay", "I want to adjust you",
          "be a lamp", "desk lamp mode", "let me position you"

        When DISABLED (False):
        - You return to normal autonomous movement
        - Animations resume, you're free to move and express yourself again
        - Use when someone says: "you're free", "go back to normal", "release", "move freely",
          "be yourself again", "stop being a lamp"

        Args:
            enabled: True to enable pushable mode, False to disable and return to normal
        """
        # Check if motors are available
        error = self._check_motors_enabled()
        if error:
            return error

        print(f"LeLamp: set_pushable_mode function called with enabled: {enabled}")
        try:
            if enabled:
                success = self.animation_service.enable_pushable_mode()
                if success:
                    return "I'm now in pushable mode! Go ahead and move me wherever you'd like - I'll hold still and stay where you put me. Just tell me when you want me to be free again!"
                else:
                    return "Hmm, I couldn't enter pushable mode. Something went wrong with my motors."
            else:
                success = self.animation_service.disable_pushable_mode(return_to_idle=True)
                if success:
                    return "I'm free again! Back to my normal self - ready to move and groove!"
                else:
                    return "Hmm, I had trouble returning to normal mode."
        except Exception as e:
            return f"Error with pushable mode: {str(e)}"
