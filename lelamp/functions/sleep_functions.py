"""
Sleep/wake function tools for LeLamp

This module contains all sleep/wake-related function tools including:
- Going to sleep mode
- Waking up from sleep
"""

import logging
import asyncio
from lelamp.service.agent.tools import Tool


class SleepFunctions:
    """Mixin class providing sleep/wake function tools"""

    @Tool.register_tool
    async def go_to_sleep(self) -> str:
        """
        Put LeLamp to sleep! Use this when someone says goodnight, go to sleep,
        sleep mode, or similar. LeLamp will say goodnight, turn off lights, play
        the sleep animation, and stop responding to conversation until woken up.

        In sleep mode:
        - Disconnects from OpenAI (no cloud, no cost)
        - Uses local wake word detection for "wake up"
        - Timers and alarms still work
        - Motors frozen, LEDs off
        - Spotify paused, camera off

        Returns:
            Confirmation message
        """
        from lelamp.globals import wake_service, agent_session_global, vision_service, ollama_vision_service

        print("LeLamp: go_to_sleep called")
        try:
            # Play sleep animation FIRST (if motors available)
            if self.animation_service:
                self.animation_service.dispatch("play", "sleep")

            # Set sleep state to block further animations (except sleep/wake_up)
            # Don't release motors yet - let the animation complete first!
            self.is_sleeping = True
            if self.animation_service:
                self.animation_service.set_sleep_mode(True, release_motors=False)
            self.rgb_service.set_sleep_mode(True)

            # Stop Spotify music if playing
            if hasattr(self, 'spotify_service') and self.spotify_service:
                try:
                    if self.spotify_service.is_playing():
                        self.spotify_service.pause()
                        logging.info("Spotify paused for sleep mode")
                except Exception as e:
                    logging.warning(f"Could not pause Spotify: {e}")

            # Disable music modifier
            if self.animation_service:
                self.animation_service.disable_modifier("music")

            # Stop vision services (camera)
            if vision_service:
                try:
                    vision_service.stop()
                    logging.info("Vision service stopped for sleep mode")
                except Exception as e:
                    logging.warning(f"Could not stop vision service: {e}")

            if ollama_vision_service:
                try:
                    ollama_vision_service.stop()
                    logging.info("Ollama vision service stopped for sleep mode")
                except Exception as e:
                    logging.warning(f"Could not stop Ollama vision service: {e}")

            # Stop all audio playback and clear queue
            if self.audio_service:
                self.audio_service.clear_queue()
                logging.info("Audio playback cleared for sleep mode")

            logging.info("LeLamp entering sleep mode")

            # IMMEDIATELY disable audio to fully disconnect OpenAI
            # Use multiple approaches for reliability:
            # 1. Disable audio input/output (this is what actually works!)
            # 2. Mute the room's audio track as backup
            from lelamp.globals import agent_session_global as current_session
            import lelamp.globals as globals_module

            if current_session:
                try:
                    current_session.input.set_audio_enabled(False)
                    logging.info("🔇 Audio INPUT disabled - OpenAI cannot hear")
                    current_session.output.set_audio_enabled(False)
                    logging.info("🔇 Audio OUTPUT disabled - OpenAI cannot speak")
                except Exception as e:
                    logging.error(f"Error disabling audio: {e}", exc_info=True)
            else:
                logging.warning("agent_session_global is None - cannot disable audio")

            # Backup: Mute mic track on room
            room = globals_module.livekit_room
            if room and room.local_participant:
                try:
                    for pub in room.local_participant.track_publications.values():
                        if hasattr(pub, 'track') and pub.track:
                            pub.track.muted = True
                            logging.info(f"🔇 Muted track: {pub.sid}")
                except Exception as e:
                    logging.error(f"Error muting tracks: {e}")

            # IMMEDIATELY mute system volume so even if agent responds, nothing plays
            self._set_system_volume(0)
            logging.info("🔇 System volume muted to 0")

            # Wait for animation to complete, then do the rest
            def _complete_sleep_sequence():
                import time
                # Wait for "goodnight" speech to finish
                logging.info("Sleep sequence: waiting for goodbye speech (3s)...")
                time.sleep(3)

                # Wait for sleep animation to complete
                logging.info("Sleep sequence: waiting for sleep animation (5s)...")
                time.sleep(5)

                logging.info("Sleep animation complete - turning off RGB and releasing motors")

                # Turn off RGB lights AFTER animation completes
                self.rgb_service.dispatch("solid", (0, 0, 0))

                # Release motors AFTER animation completes
                if self.animation_service and self.animation_service.robot and self.animation_service.robot.bus:
                    try:
                        self.animation_service.robot.bus.disable_torque()
                        logging.info("Motors released (torque disabled)")
                    except Exception as e:
                        logging.error(f"Error disabling motor torque: {e}")

                # Final RGB turn-off (redundant but ensures LEDs are off even if race condition occurred)
                self.rgb_service.dispatch("solid", (0, 0, 0))
                logging.info("RGB LEDs turned off (final)")

                # Volume already muted immediately, no need to do it again

                # Start local wake word detection (uses dsnoop to share mic)
                if wake_service:
                    def on_wake_word():
                        """Called when wake word detected"""
                        logging.info("Wake word detected! Triggering wake up...")
                        # Trigger wake up in async context
                        if self.event_loop:
                            asyncio.run_coroutine_threadsafe(
                                self.wake_up(),
                                self.event_loop
                            )

                    try:
                        wake_service.start(on_wake_word)
                        logging.info("Local Whisper wake word detection active")
                    except Exception as e:
                        logging.error(f"Failed to start wake word service: {e}")

                logging.info("LeLamp now in deep sleep mode (local wake detection only)")

            import threading
            threading.Thread(target=_complete_sleep_sequence, daemon=True).start()

            return "Goodnight! Sweet dreams. Say wake up when you need me."

        except Exception as e:
            return f"Error going to sleep: {str(e)}"

    @Tool.register_tool
    async def wake_up(self) -> str:
        """
        Wake LeLamp up from sleep! Use this when someone says wake up, good morning,
        or similar phrases. LeLamp will come back to life with the wake_up animation
        and be ready to interact again.

        Returns:
            Confirmation message
        """
        from lelamp.globals import CONFIG, wake_service, agent_session_global, vision_service, ollama_vision_service
        import lelamp.globals as g

        print("LeLamp: wake_up called")
        try:
            # Stop local wake word detection
            if wake_service and wake_service.is_running():
                wake_service.stop()
                logging.info("Stopped local wake word detection")

            # Exit sleep state
            self.is_sleeping = False

            # Re-enable motor torque by reconfiguring motors
            if self.animation_service and self.animation_service.robot:
                try:
                    self.animation_service.robot.configure()
                    logging.info("Motors reconfigured and torque enabled")
                except Exception as e:
                    logging.error(f"Error reconfiguring motors: {e}")

            # Restore volume
            volume = CONFIG.get("volume", 100)
            self._set_system_volume(volume)

            # Re-enable animations and RGB
            if self.animation_service:
                self.animation_service.set_sleep_mode(False)
            self.rgb_service.set_sleep_mode(False)

            # Play wake up animation
            if self.animation_service:
                self.animation_service.dispatch("play", "wake_up")

            # Start default RGB animation
            rgb_config = CONFIG.get("rgb", {})
            default_anim = rgb_config.get("default_animation", "aura_glow")
            self.rgb_service.dispatch("animation", {
                "name": default_anim,
                "color": tuple(rgb_config.get("default_color", [255, 255, 255]))
            })

            # Restart vision services
            face_config = CONFIG.get("face_tracking", {})
            if face_config.get("enabled", False):
                if g.vision_service:
                    try:
                        g.vision_service.start()
                        logging.info("Vision service restarted after wake")
                    except Exception as e:
                        logging.warning(f"Could not restart vision service: {e}")

            vision_config = CONFIG.get("vision", {})
            ollama_config = vision_config.get("ollama", {})
            if ollama_config.get("enabled", False):
                if g.ollama_vision_service:
                    try:
                        import asyncio
                        g.ollama_vision_service.start(event_loop=asyncio.get_running_loop())
                        logging.info("Ollama vision service restarted after wake")
                    except Exception as e:
                        logging.warning(f"Could not restart Ollama vision service: {e}")

            # Re-enable audio - reverse everything we did in sleep
            # 1. Clear any pending audio/conversation from sleep period
            # 2. Re-enable audio input/output
            # 3. Unmute room tracks
            if agent_session_global:
                try:
                    # FIRST: Clear any queued audio/conversation from sleep period
                    # This prevents the agent from responding to things said while asleep
                    try:
                        agent_session_global.interrupt()
                        logging.info("🧹 Interrupted any pending responses")
                    except Exception:
                        pass  # May fail if nothing pending

                    try:
                        agent_session_global.clear_user_turn()
                        logging.info("🧹 Cleared user turn buffer")
                    except Exception:
                        pass  # May fail if no user turn

                    # NOW re-enable audio
                    agent_session_global.input.set_audio_enabled(True)
                    logging.info("🔊 Audio INPUT re-enabled - OpenAI can hear again")
                    agent_session_global.output.set_audio_enabled(True)
                    logging.info("🔊 Audio OUTPUT re-enabled - OpenAI can speak again")
                except Exception as e:
                    logging.error(f"Error re-enabling audio: {e}")

            # Unmute room tracks
            room = g.livekit_room
            if room and room.local_participant:
                try:
                    for pub in room.local_participant.track_publications.values():
                        if hasattr(pub, 'track') and pub.track:
                            pub.track.muted = False
                            logging.info(f"🔊 Unmuted track: {pub.sid}")
                except Exception as e:
                    logging.error(f"Error unmuting tracks: {e}")

            logging.info("LeLamp waking up from sleep mode - full OpenAI mode restored")
            return "Good morning! I'm awake and ready to help!"

        except Exception as e:
            return f"Error waking up: {str(e)}"

    @Tool.register_tool
    async def shutdown_system(self) -> str:
        """
        Shut down the entire system (Raspberry Pi)! Use this when someone asks you to
        shut down, power off, turn off completely, or shut down the system. This is
        different from sleep mode - it actually powers off the device.

        WARNING: This will completely power off the device. It can only be turned back
        on by physically unplugging and replugging the power.

        Shutdown sequence:
        1. Says goodbye to the user
        2. Plays shutdown theme sound
        3. Plays "beacon" RGB animation
        4. Plays "sleep" motor animation
        5. Turns off RGB LEDs
        6. Executes system shutdown

        Use when someone says: "shut down", "power off", "turn off", "shut down the system"

        Returns:
            Goodbye message
        """
        from lelamp.service.theme import get_theme_service, ThemeSound

        print("LeLamp: shutdown_system called")
        try:
            # Start the shutdown sequence in background
            def _shutdown_sequence():
                import time
                import subprocess

                logging.info("🔴 SHUTDOWN SEQUENCE INITIATED")

                # Wait for goodbye message to be spoken (3 seconds)
                time.sleep(3)

                # Play shutdown theme sound
                theme = get_theme_service()
                if theme:
                    theme.play(ThemeSound.SHUTDOWN, blocking=True)

                # Play beacon RGB animation
                logging.info("Playing beacon RGB animation...")
                self.rgb_service.dispatch("animation", {
                    "name": "beacon",
                    "color": (255, 100, 0)  # Orange beacon
                })

                # Play sleep motor animation (if motors available)
                if self.animation_service:
                    logging.info("Playing sleep motor animation...")
                    self.animation_service.dispatch("play", "sleep")
                    # Wait for animations to complete (~11 seconds for sleep animation)
                    time.sleep(11)
                else:
                    logging.info("Motors not available - skipping sleep animation")
                    time.sleep(2)  # Brief pause anyway

                # Turn off RGB LEDs
                logging.info("Turning off RGB LEDs...")
                self.rgb_service.dispatch("solid", (0, 0, 0))

                # Wait a moment for LEDs to turn off
                time.sleep(1)

                # Release motors right before shutdown
                if self.animation_service and self.animation_service.robot and self.animation_service.robot.bus:
                    try:
                        self.animation_service.robot.bus.disable_torque()
                        logging.info("Motors released (torque disabled)")
                    except Exception as e:
                        logging.error(f"Error disabling motor torque: {e}")

                # Wait for motors to fully release
                time.sleep(2)

                # Execute system shutdown
                logging.info("🔴 EXECUTING SYSTEM SHUTDOWN NOW")
                try:
                    subprocess.run(["sudo", "shutdown", "now"], check=True)
                except subprocess.CalledProcessError as e:
                    logging.error(f"Shutdown command failed: {e}")
                    logging.error("Make sure 'sudo shutdown now' is configured for passwordless execution")
                except Exception as e:
                    logging.error(f"Error during shutdown: {e}")

            import threading
            threading.Thread(target=_shutdown_sequence, daemon=True).start()

            return "Goodbye! It's been wonderful spending time with you. Shutting down now... see you next time!"

        except Exception as e:
            return f"Error initiating shutdown: {str(e)}"
