"""
Vision function tools for LeLamp

This module contains vision-related function tools including:
- Scene context from Ollama vision
- What the agent can see
"""

import logging
from lelamp.service.agent.tools import Tool


class VisionFunctions:
    """Mixin class providing vision function tools"""

    @Tool.register_tool
    async def describe_scene(self) -> str:
        """
        Describe what you currently see through your camera. Use this when someone asks
        "what do you see?", "what's around you?", "describe the room", "who's here?",
        or any question about your visual surroundings.

        This uses local Ollama vision AI to analyze the camera feed and provide a
        structured description of the environment, people, animals, and objects visible.

        Returns:
            A description of the current scene including environment, people detected,
            animals, notable objects, and any changes since the last observation.
        """
        from lelamp.globals import ollama_vision_service

        print("LeLamp: describe_scene function called")
        try:
            # Skip vision processing when sleeping
            if self.is_sleeping:
                return "Sleeping"

            if ollama_vision_service is None:
                return "Scene analysis is not available. Enable Ollama vision in config.yaml under 'vision.ollama'."

            context = ollama_vision_service.get_scene_context()

            if context is None:
                return "I haven't analyzed the scene yet. Give me a moment to look around."

            # Build a natural language description
            parts = []

            # Environment
            parts.append(f"I'm in what looks like {context.environment}.")
            parts.append(f"The lighting is {context.lighting}.")

            # People
            if context.number_of_people == 0:
                parts.append("I don't see anyone right now.")
            elif context.number_of_people == 1:
                parts.append("I see one person.")
                if context.people:
                    person = context.people[0]
                    desc = person.get('description', '')
                    activity = person.get('activity', '')
                    if desc:
                        parts.append(f"They appear to be {desc}.")
                    if activity:
                        parts.append(f"They seem to be {activity}.")
            else:
                parts.append(f"I see {context.number_of_people} people.")
                for i, person in enumerate(context.people, 1):
                    desc = person.get('description', '')
                    if desc:
                        parts.append(f"Person {i}: {desc}.")

            # Animals
            if context.animals:
                animal_descs = []
                for animal in context.animals:
                    a_type = animal.get('type', 'animal')
                    a_desc = animal.get('description', '')
                    if a_desc:
                        animal_descs.append(f"{a_type} ({a_desc})")
                    else:
                        animal_descs.append(a_type)
                parts.append(f"I also see: {', '.join(animal_descs)}.")

            # Notable objects
            if context.objects and len(context.objects) > 0:
                obj_list = context.objects[:5]  # Limit to 5
                parts.append(f"Notable objects: {', '.join(obj_list)}.")

            # Confidence
            if context.confidence == "low":
                parts.append("(My view is a bit unclear, so I'm not very confident about this.)")

            return " ".join(parts)

        except Exception as e:
            logging.error(f"Error in describe_scene: {e}")
            return f"Error analyzing scene: {str(e)}"

    @Tool.register_tool
    async def get_scene_details(self) -> str:
        """
        Get detailed, structured information about the current scene. This returns
        raw scene analysis data including exact counts, positions, and changes detected.

        Use this for more technical queries or when you need precise scene data rather
        than a natural description. Good for: counting people, checking for specific
        objects, or debugging vision.

        Returns:
            Structured scene data in a detailed format.
        """
        from lelamp.globals import ollama_vision_service

        print("LeLamp: get_scene_details function called")
        try:
            # Skip vision processing when sleeping
            if self.is_sleeping:
                return "Sleeping"

            if ollama_vision_service is None:
                return "Scene analysis not available. Enable Ollama vision in config.yaml."

            context = ollama_vision_service.get_scene_context()

            if context is None:
                return "No scene data available yet."

            # Return the formatted prompt string (structured but readable)
            details = [
                f"Environment: {context.environment}",
                f"Lighting: {context.lighting}",
                f"People count: {context.number_of_people}",
            ]

            if context.people:
                details.append("People details:")
                for i, p in enumerate(context.people, 1):
                    details.append(f"  {i}. {p.get('description', 'N/A')} - {p.get('activity', 'N/A')} - {p.get('position', 'N/A')}")

            if context.animals:
                animal_strs = [f"{a.get('type')} ({a.get('description', '')})" for a in context.animals]
                details.append(f"Animals: {', '.join(animal_strs)}")

            if context.objects:
                details.append(f"Objects: {', '.join(context.objects)}")

            details.append(f"Changes: {context.changes_detected}")
            details.append(f"Confidence: {context.confidence}")
            details.append(f"Last updated: {context.timestamp:.1f}s ago" if context.timestamp else "Last updated: Unknown")

            return "\n".join(details)

        except Exception as e:
            logging.error(f"Error in get_scene_details: {e}")
            return f"Error getting scene details: {str(e)}"
