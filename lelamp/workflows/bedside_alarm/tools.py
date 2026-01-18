from livekit.agents import function_tool
import asyncio
import subprocess
import threading


@function_tool
async def play_alarm_sound(self) -> str:
    """
    Play an alarm sound effect to wake the user up. This plays a short, attention-grabbing
    alert sound that signals it's time to wake up. Use this when you need to get the user's
    attention with an audio cue.

    Returns:
        Confirmation that the alarm sound was played.
    """
    from lelamp.service.theme import get_theme_service, ThemeSound

    print("LeLamp: play_alarm_sound called")
    try:
        # Play the theme's alert sound
        theme = get_theme_service()
        if theme:
            theme.play(ThemeSound.ALERT)
        else:
            # Fallback to old method if theme service not initialized
            def _play():
                try:
                    subprocess.run(["aplay", "-q", "assets/AudioFX/Effects/Scifi-AlertShort.wav"], capture_output=True, timeout=5)
                except Exception as e:
                    print(f"Error playing alarm sound: {e}")
            threading.Thread(target=_play, daemon=True).start()

        return "Alarm sound played successfully"
    except Exception as e:
        return f"Error playing alarm sound: {str(e)}"


@function_tool
async def wait_seconds(self, duration: int) -> str:
    """
    Wait for a specified number of seconds. Use this to pause the workflow execution
    and give the user time to respond or wake up naturally. During the wait, you can
    still animate and show RGB patterns to indicate you're waiting.

    Args:
        duration: Number of seconds to wait (e.g., 60 for 1 minute, 300 for 5 minutes)

    Returns:
        Confirmation that the wait period has completed.
    """
    print(f"LeLamp: wait_seconds called with duration={duration}s")
    try:
        if duration <= 0:
            return "Error: Duration must be positive"

        if duration > 600:  # 10 minutes max
            return "Error: Duration too long (max 600 seconds / 10 minutes)"

        # Use asyncio.sleep to avoid blocking
        await asyncio.sleep(duration)

        return f"Wait completed - {duration} seconds have passed"
    except Exception as e:
        return f"Error during wait: {str(e)}"


@function_tool
async def check_user_sleeping_llm(self) -> str:
    """
    Ask the user if they are still in bed sleeping. This is an interactive check where
    you directly ask them and listen for their response. Use this to determine if the
    user has woken up yet.

    The workflow should update the 'user_awake' state based on their answer:
    - If they respond "yes I'm awake" or similar, set user_awake=true
    - If they don't respond or say "still sleeping", set user_awake=false

    Returns:
        Instruction to ask the user if they're still sleeping
    """
    print("LeLamp: check_user_sleeping_llm called")
    try:
        return "Ask the user: 'Are you still in bed sleeping?' and listen carefully to their response. Based on their answer, update the user_awake state when you call complete_step."

    except Exception as e:
        return f"Error during sleep check: {str(e)}"


@function_tool
async def check_user_phone_llm(self) -> str:
    """
    Ask the user if they are playing on their phone while still in bed. This is an
    interactive check where you directly ask them and listen for their response.
    Be a bit sarcastic and playful when asking!

    The workflow should update the 'playing_on_phone' state based on their answer:
    - If they admit to being on their phone, set playing_on_phone=true
    - If they say no or don't respond, set playing_on_phone=false

    Returns:
        Instruction to ask the user if they're on their phone
    """
    print("LeLamp: check_user_phone_llm called")
    try:
        return "Ask the user in a sarcastic way: 'Are you playing on your phone while still in bed?' and listen to their response. Based on their answer, update the playing_on_phone state when you call complete_step."

    except Exception as e:
        return f"Error during phone check: {str(e)}"


@function_tool
async def check_user_awake_vision(self) -> str:
    """
    Use vision to check if the user appears to be awake. This analyzes the camera feed
    to look for signs that the user is up and moving vs still in bed sleeping.

    Signs of being awake:
    - User is sitting up or standing
    - User is moving around the room
    - User is not in bed
    - Eyes are open and looking alert

    Signs of still sleeping:
    - User is lying down
    - User appears to be in bed
    - Eyes closed or barely open
    - Not much movement

    Returns:
        A description of what was observed and whether the user appears awake or asleep.
        Update user_awake state based on the observation.
    """
    from lelamp.globals import ollama_vision_service

    print("LeLamp: check_user_awake_vision called")
    try:
        if ollama_vision_service is None:
            return "Vision not available - ask the user directly if they're awake."

        context = ollama_vision_service.get_scene_context()

        if context is None:
            return "Cannot see clearly right now - ask the user directly if they're awake."

        # Build observation report
        observations = []

        if context.number_of_people == 0:
            observations.append("I don't see anyone in view. They might have gotten up!")
            return "No one visible in the room - the user may have gotten out of bed. Set user_awake to true and congratulate them for getting up!"

        if context.people:
            person = context.people[0]
            activity = person.get('activity', '').lower()
            position = person.get('position', '').lower()
            description = person.get('description', '').lower()

            # Check for signs of being awake
            awake_indicators = ['sitting', 'standing', 'walking', 'moving', 'working', 'typing', 'looking', 'active']
            sleeping_indicators = ['lying', 'sleeping', 'resting', 'bed', 'eyes closed', 'asleep']

            is_awake = any(indicator in activity or indicator in position or indicator in description
                          for indicator in awake_indicators)
            is_sleeping = any(indicator in activity or indicator in position or indicator in description
                              for indicator in sleeping_indicators)

            observations.append(f"I see someone: {description}")
            if activity:
                observations.append(f"They appear to be: {activity}")
            if position:
                observations.append(f"Position: {position}")

            if is_awake and not is_sleeping:
                observations.append("The user appears to be AWAKE and active!")
                return f"{' '.join(observations)} Set user_awake to true - they're up!"
            elif is_sleeping:
                observations.append("The user still appears to be sleeping or in bed.")
                return f"{' '.join(observations)} Set user_awake to false - they need more encouragement to get up!"
            else:
                observations.append("Hard to tell if they're fully awake.")
                return f"{' '.join(observations)} Ask the user directly if they're awake to confirm."

        return "Could not determine if user is awake. Ask them directly."

    except Exception as e:
        return f"Error checking vision: {str(e)} - Ask the user directly if they're awake."
