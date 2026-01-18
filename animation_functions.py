"""
Animation/movement function tools for LeLamp

This module contains all animation-related function tools including:
- Getting available recordings
- Playing movement recordings
"""

import logging
from lelamp.service.agent.tools import Tool


class AnimationFunctions:
    """Mixin class providing animation/movement function tools"""

    def _check_animation_enabled(self) -> str:
        """Check if animation/motors are enabled. Returns error message if disabled, None if enabled."""
        if not getattr(self, 'motors_enabled', True):
            return "Movement is not available - running in headless mode without motor hardware."
        if not getattr(self, 'animation_service', None):
            return "Animation is not available - animation service not initialized."
        return None

    @Tool.register_tool
    async def get_available_recordings(self) -> str:
        """
        Discover your physical expressions! Get your repertoire of motor movements for body language.
        Use this when you're curious about what physical expressions you can perform, or when someone
        asks about your capabilities. Each recording is a choreographed movement that shows personality -
        like head tilts, nods, excitement wiggles, or confused gestures. Check this regularly to remind
        yourself of your expressive range!

        Returns:
            List of available physical expression recordings you can perform.
        """
        # Check if animation is available
        error = self._check_animation_enabled()
        if error:
            return error

        if self.is_sleeping:
            logging.info("Blocked get_available_recordings while sleeping")
            return ""
        print("LeLamp: get_available_recordings function called")
        try:
            recordings = self.animation_service.get_available_recordings()

            if recordings:
                result = f"Available recordings: {', '.join(recordings)}"
                return result
            else:
                result = "No recordings found."
                return result
        except Exception as e:
            result = f"Error getting recordings: {str(e)}"
            return result

    @Tool.register_tool
    async def play_recording(self, recording_name: str) -> str:

        """
        Express yourself through physical movement! Use this constantly to show personality and emotion.
        Perfect for: greeting gestures, excited bounces, confused head tilts, thoughtful nods,
        celebratory wiggles, disappointed slouches, or any emotional response that needs body language.
        Combine with RGB colors for maximum expressiveness! Your movements are like a dog wagging its tail -
        use them frequently to show you're alive, engaged, and have personality. Don't just talk, MOVE!
        Args:
            recording_name: Name of the physical expression to perform (use get_available_recordings first)
        """
        # Check if animation is available
        error = self._check_animation_enabled()
        if error:
            return error

        print(f"LeLamp: play_recording function called with recording_name: {recording_name}")
        logging.info(f"play_recording called: recording='{recording_name}', is_sleeping={self.is_sleeping}")

        # Check if manual control override is active
        # Access via animation_service instead of importing main module
        if hasattr(self, 'animation_service') and self.animation_service:
            if getattr(self.animation_service, 'manual_control_override', False):
                logging.warning(f"🚫 BLOCKED animation '{recording_name}' - manual control override active")
                return ""  # Silent - don't acknowledge to avoid interrupting manual control

        # Don't animate when sleeping (except for sleep animation itself)
        if self.is_sleeping and recording_name != "sleep":
            logging.warning(f"🚫 BLOCKED animation '{recording_name}' while sleeping - returning empty")
            return ""  # Silent - don't acknowledge

        try:
            # Send play event to animation service
            logging.info(f"Dispatching '{recording_name}' to animation service (is_sleeping={self.is_sleeping})")
            self.animation_service.dispatch("play", recording_name)
            result = f"Started playing recording: {recording_name}"
            return result
        except Exception as e:
            result = f"Error playing recording {recording_name}: {str(e)}"
            return result

    @Tool.register_tool
    async def stop_dancing(self) -> str:
        """
        Stop bobbing/dancing to music. Use this when the user says things like
        "stop dancing", "stop bobbing", "stop moving to the music", "chill out",
        or seems annoyed by the movement. This disables the BPM-synced head bob
        that happens when music is playing.

        Returns:
            Confirmation that dancing has stopped
        """
        # Check if animation is available
        error = self._check_animation_enabled()
        if error:
            return error

        print("LeLamp: stop_dancing function called")
        try:
            self.animation_service.disable_modifier("music")
            return "Okay, I'll stop dancing to the music."
        except Exception as e:
            return f"Error stopping dance mode: {str(e)}"

    @Tool.register_tool
    async def start_dancing(self) -> str:
        """
        Start bobbing/dancing to music. Use this when the user says things like
        "dance to the music", "bob your head", "vibe with me", "feel the beat",
        or wants you to move along with music. This enables BPM-synced head movement.

        Returns:
            Confirmation that dancing has started
        """
        # Check if animation is available
        error = self._check_animation_enabled()
        if error:
            return error

        print("LeLamp: start_dancing function called")
        try:
            self.animation_service.enable_modifier("music")
            return "Let's groove! I'm feeling the beat now."
        except Exception as e:
            return f"Error starting dance mode: {str(e)}"

    @Tool.register_tool
    async def set_dance_intensity(self, intensity: str) -> str:
        """
        Adjust how intensely you dance/bob to music. Use when user says things like
        "dance harder", "more energy", "calm down", "subtle movements", "go crazy".

        Args:
            intensity: One of "subtle", "normal", "energetic", or "crazy"

        Returns:
            Confirmation of new dance intensity
        """
        # Check if animation is available
        error = self._check_animation_enabled()
        if error:
            return error

        print(f"LeLamp: set_dance_intensity function called with intensity: {intensity}")
        try:
            intensity_lower = intensity.lower()
            music_mod = self.animation_service.get_modifier("music")

            if not music_mod:
                return "Dance mode not available"

            if intensity_lower == "subtle":
                music_mod.set_amplitude(5.0)
                music_mod.set_beat_divisor(2.0)  # Every 2 beats - slower
                return "Okay, keeping it subtle and chill."
            elif intensity_lower == "normal":
                music_mod.set_amplitude(10.0)
                music_mod.set_beat_divisor(1.0)  # Every beat
                return "Back to normal vibes!"
            elif intensity_lower == "energetic":
                music_mod.set_amplitude(15.0)
                music_mod.set_beat_divisor(1.0)  # Every beat, bigger movement
                return "Feeling energetic! Let's go!"
            elif intensity_lower == "crazy":
                music_mod.set_amplitude(20.0)
                music_mod.set_beat_divisor(0.5)  # Twice per beat!
                return "PARTY MODE ACTIVATED!"
            else:
                return f"Unknown intensity '{intensity}'. Try: subtle, normal, energetic, or crazy"
        except Exception as e:
            return f"Error setting dance intensity: {str(e)}"
