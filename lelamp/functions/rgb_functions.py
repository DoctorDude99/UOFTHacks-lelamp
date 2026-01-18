"""
RGB lighting function tools for LeLamp

This module contains all RGB/lighting-related function tools including:
- Solid color control
- RGB animations
- Pattern painting
- Animation listing
"""

import logging
from lelamp.service.agent.tools import Tool


class RGBFunctions:
    """Mixin class providing RGB lighting function tools"""

    def _is_rgb_enabled(self) -> bool:
        """Check if RGB service is enabled and running."""
        return (
            hasattr(self, 'rgb_service') and
            self.rgb_service is not None and
            self.rgb_service._running.is_set()
        )

    @Tool.register_tool
    async def set_rgb_solid(self, red: int, green: int, blue: int) -> str:
        """
        Express emotions and moods by changing your lamp color! Use this to show feelings during conversation.
        Perfect for: excitement (bright yellow/orange), happiness (warm colors), calmness (soft blues/greens),
        surprise (bright white), thinking (purple), error/concern (red), or any emotional response.
        Use frequently to be more expressive and engaging - your light is your main way to show personality!

        This will apply the color to your currently running animation (keeping it animated),
        or start a nice animated effect with the new color.

        Args:
            red: Red component (0-255) - higher values for warmth, energy, alerts
            green: Green component (0-255) - higher values for nature, calm, success
            blue: Blue component (0-255) - higher values for cool, tech, focus
        """
        print(f"LeLamp: set_rgb_solid function called with RGB({red}, {green}, {blue})")

        # Check if RGB service is enabled
        if not self._is_rgb_enabled():
            return "The RGB LED service is currently disabled. Enable it in the Services panel to use lighting features."

        # Don't change lights when sleeping (keep them off)
        if self.is_sleeping:
            logging.info(f"Blocked RGB change to ({red}, {green}, {blue}) while sleeping")
            return ""  # Silent - don't acknowledge

        try:
            # Mark activity for idle timeout
            self._mark_activity()

            # Validate RGB values
            if not all(0 <= val <= 255 for val in [red, green, blue]):
                return "Error: RGB values must be between 0 and 255"

            # Get current animation name from RGB service
            current_anim = getattr(self.rgb_service, '_current_animation', None)

            # If no animation is running or it's a static solid color, use a nice default
            if not current_anim or current_anim == 'solid':
                current_anim = 'aura_glow'  # Default gentle animation

            # Apply the color to the current (or default) animation
            self.rgb_service.dispatch("animation", {
                "name": current_anim,
                "color": (red, green, blue)
            })

            result = f"Changed lamp color to RGB({red}, {green}, {blue}) with {current_anim} animation"
            return result
        except Exception as e:
            result = f"Error setting RGB color: {str(e)}"
            return result

    @Tool.register_tool
    async def play_rgb_animation(self, animation_name: str, red: int = None, green: int = None, blue: int = None, duration: float = None) -> str:
        """
        Play expressive RGB light animations! Use this to enhance your emotional expression through dynamic lighting.
        Each animation has a specific mood and use case. Pair animations with appropriate colors for maximum impact!

        Available animations:
        - aura_glow: Gentle pulsing idle glow - calm, mysterious, idle states. Default animation.
        - thinking: Gentle wave pattern - processing, contemplating, analyzing
        - speaking: Subtle pulsing - use when talking to show you're alive and engaged
        - alarm: Quick urgent flashes - alarms, alerts, urgent notifications (use red/orange for urgency)
        - scan: Active scanning sweep - searching, analyzing, alert and focused
        - targeting: Crosshair targeting - focusing on something specific, locked-on feel
        - angry: Intense aggressive pulsing - frustrated, angry (pairs well with red)
        - ripple: Waves from center outward - expanding ideas, wave-like responses
        - burst: Quick bright flash - surprise, sudden realization, emphasis, 'aha!' moments
        - beacon: Rotating bright spot - attracting attention, alert mode

        Use this frequently to be more expressive! Combine with motor movements for maximum personality.

        Args:
            animation_name: Name of the animation to play (see list above)
            red: Optional red component (0-255) to set color. If omitted, keeps current color.
            green: Optional green component (0-255) to set color. If omitted, keeps current color.
            blue: Optional blue component (0-255) to set color. If omitted, keeps current color.
            duration: Optional duration in seconds. If omitted, animation loops continuously.

        Examples:
            - play_rgb_animation("thinking", 150, 100, 200) - Purple thinking animation
            - play_rgb_animation("alarm", 255, 100, 0) - Bright orange alarm
            - play_rgb_animation("burst", 255, 255, 255, 0.5) - Quick white flash for half a second
        """
        print(f"LeLamp: play_rgb_animation called with animation={animation_name}, RGB=({red}, {green}, {blue}), duration={duration}")

        # Check if RGB service is enabled
        if not self._is_rgb_enabled():
            return "The RGB LED service is currently disabled. Enable it in the Services panel to use lighting features."

        # Don't animate when sleeping
        if self.is_sleeping:
            logging.info(f"Blocked RGB animation '{animation_name}' while sleeping")
            return ""

        try:
            # Mark activity for idle timeout
            self._mark_activity()

            # Get available animations
            available = self.rgb_service.get_available_animations()
            if animation_name not in available:
                return f"Unknown animation '{animation_name}'. Available: {', '.join(available.keys())}"

            # Build payload
            payload = {"name": animation_name}

            # Add color if provided
            if red is not None and green is not None and blue is not None:
                if not all(0 <= val <= 255 for val in [red, green, blue]):
                    return "Error: RGB values must be between 0 and 255"
                payload["color"] = (red, green, blue)

            # Add duration if provided
            if duration is not None:
                payload["duration"] = duration

            # Dispatch animation event
            self.rgb_service.dispatch("animation", payload)

            color_str = f" with RGB({red}, {green}, {blue})" if red is not None else ""
            duration_str = f" for {duration}s" if duration else ""
            result = f"Playing RGB animation: {animation_name}{color_str}{duration_str}"
            return result

        except Exception as e:
            result = f"Error playing RGB animation: {str(e)}"
            return result

    @Tool.register_tool
    async def list_rgb_animations(self) -> str:
        """
        Get a list of all available RGB animations with their descriptions.
        Use this when you want to explore your RGB animation capabilities or
        when someone asks what light animations you can do.

        Returns:
            List of available RGB animations with descriptions
        """
        print("LeLamp: list_rgb_animations called")

        # Check if RGB service is enabled
        if not self._is_rgb_enabled():
            return "The RGB LED service is currently disabled. Enable it in the Services panel to use lighting features."

        try:
            animations = self.rgb_service.get_available_animations()
            result_lines = ["Available RGB animations:"]
            for name, description in animations.items():
                result_lines.append(f"  - {name}: {description}")
            return "\n".join(result_lines)
        except Exception as e:
            return f"Error listing RGB animations: {str(e)}"

    @Tool.register_tool
    async def paint_rgb_pattern(self, colors: list) -> str:
        """
        Create dynamic visual patterns and animations with your lamp! Use this for complex expressions.
        Perfect for: rainbow effects, gradients, sparkles, waves, celebrations, visual emphasis,
        storytelling through color sequences, or when you want to be extra animated and playful.
        Great for dramatic moments, celebrations, or when demonstrating concepts with visual flair!

        You have to put in 40 colors. It's a 8x5 Grid in a one dim array. (8,5)

        Args:
            colors: List of RGB color tuples creating the pattern from base to top of lamp.
                   Each tuple is (red, green, blue) with values 0-255.
                   Example: [(255,0,0), (255,127,0), (255,255,0)] creates red-to-orange-to-yellow gradient
        """
        print(f"LeLamp: paint_rgb_pattern function called with {len(colors)} colors")

        # Check if RGB service is enabled
        if not self._is_rgb_enabled():
            return "The RGB LED service is currently disabled. Enable it in the Services panel to use lighting features."

        # Don't change lights when sleeping (keep them off)
        if self.is_sleeping:
            logging.info(f"Blocked RGB pattern while sleeping")
            return ""  # Silent - don't acknowledge

        try:
            # Validate colors format
            if not isinstance(colors, list):
                return "Error: colors must be a list of RGB tuples"

            validated_colors = []
            for i, color in enumerate(colors):
                if not isinstance(color, (list, tuple)) or len(color) != 3:
                    return f"Error: color at index {i} must be a 3-element RGB tuple"
                if not all(isinstance(val, int) and 0 <= val <= 255 for val in color):
                    return f"Error: RGB values at index {i} must be integers between 0 and 255"
                validated_colors.append(tuple(color))

            # Send paint event to RGB service
            self.rgb_service.dispatch("paint", validated_colors)
            result = f"Painted RGB pattern with {len(validated_colors)} colors"
            return result
        except Exception as e:
            result = f"Error painting RGB pattern: {str(e)}"
            return result
