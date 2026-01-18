"""
OllamaVisionService - Scene analysis using Ollama vision models
Provides periodic scene context for the LeLamp agent
"""

import asyncio
import base64
import io
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import cv2
from PIL import Image

logger = logging.getLogger("service.OllamaVisionService")
logger.setLevel(logging.INFO)  # Quiet down - only show significant changes


@dataclass
class SceneContext:
    """Structured scene analysis data"""
    environment: str = "Unknown"
    lighting: str = "Unknown"
    number_of_people: int = 0
    people: List[Dict[str, str]] = field(default_factory=list)
    animals: List[Dict[str, str]] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    changes_detected: str = "First observation"
    confidence: str = "low"
    timestamp: float = 0.0
    raw_response: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment": self.environment,
            "lighting": self.lighting,
            "number_of_people": self.number_of_people,
            "people": self.people,
            "animals": self.animals,
            "objects": self.objects,
            "changes_detected": self.changes_detected,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }

    def to_prompt_string(self) -> str:
        """Format scene context for injection into agent system prompt"""
        parts = [f"Environment: {self.environment}"]
        parts.append(f"Lighting: {self.lighting}")

        if self.number_of_people > 0:
            parts.append(f"People present: {self.number_of_people}")
            for i, person in enumerate(self.people, 1):
                desc = person.get('description', 'Unknown')
                activity = person.get('activity', 'Unknown')
                parts.append(f"  Person {i}: {desc}, {activity}")
        else:
            parts.append("People present: None detected")

        if self.animals:
            animals_str = ", ".join([f"{a.get('type', 'animal')} ({a.get('description', '')})" for a in self.animals])
            parts.append(f"Animals: {animals_str}")

        if self.objects:
            parts.append(f"Notable objects: {', '.join(self.objects[:10])}")  # Limit to 10 objects

        return "\n".join(parts)

    def has_significant_change(self, previous: Optional["SceneContext"]) -> bool:
        """Check if there's a significant change worth commenting on"""
        if previous is None:
            return False

        # People count changed (only if difference is real, not detection noise)
        if self.number_of_people != previous.number_of_people:
            return True

        # Animals appeared or disappeared
        if len(self.animals) != len(previous.animals):
            return True

        # NOTE: Removed environment text comparison - too noisy with vision models
        # The model describes scenes differently each time even when nothing changed

        return False

    def describe_changes(self, previous: Optional["SceneContext"]) -> str:
        """Describe what changed for proactive commenting"""
        if previous is None:
            return ""

        changes = []

        # People changes
        if self.number_of_people > previous.number_of_people:
            diff = self.number_of_people - previous.number_of_people
            changes.append(f"{diff} new person(s) appeared")
        elif self.number_of_people < previous.number_of_people:
            diff = previous.number_of_people - self.number_of_people
            changes.append(f"{diff} person(s) left")

        # Animal changes
        if len(self.animals) > len(previous.animals):
            new_animals = [a.get('type', 'animal') for a in self.animals]
            changes.append(f"Animal spotted: {', '.join(new_animals)}")
        elif len(self.animals) < len(previous.animals):
            changes.append("Animal left the scene")

        return "; ".join(changes) if changes else ""


class OllamaVisionService:
    """
    Vision service that uses Ollama to analyze camera frames
    - Runs periodic scene analysis in background
    - Maintains scene context with history for consistency
    - Provides callbacks for significant changes
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen3-vl:2b",
        analysis_interval: float = 5.0,
        camera_index: int = 0,
        resolution: tuple = (640, 480),
        max_frame_size: int = 512,
        instructions_file: Optional[str] = None
    ):
        self.ollama_url = ollama_url.rstrip('/')
        self.model = model
        self.analysis_interval = analysis_interval
        self.camera_index = camera_index
        self.resolution = resolution
        self.max_frame_size = max_frame_size

        # Load instructions
        self.instructions = self._load_instructions(instructions_file)

        # Camera
        self.cap = None
        self._camera_lock = threading.Lock()

        # Scene context
        self.current_context: Optional[SceneContext] = None
        self.previous_context: Optional[SceneContext] = None
        self._context_lock = threading.Lock()
        self._context_history: List[SceneContext] = []
        self._max_history = 10

        # State
        self._running = False
        self._analysis_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Proactive comment cooldown (prevent excessive chattering)
        self._last_proactive_comment_time: float = 0.0
        self._proactive_cooldown_seconds: float = 300.0  # Minimum 5 minutes between proactive comments
        self._stable_people_count: int = 0  # Require consistent readings
        self._people_count_stable_frames: int = 0  # How many frames with same count

        # Callbacks
        self._on_scene_change: Optional[Callable[[SceneContext, str], None]] = None
        self._on_context_update: Optional[Callable[[SceneContext], None]] = None

        logger.info(f"OllamaVisionService initialized (model={model}, interval={analysis_interval}s)")

    def _load_instructions(self, instructions_file: Optional[str]) -> str:
        """Load vision analysis instructions from file"""
        if instructions_file and os.path.exists(instructions_file):
            with open(instructions_file, 'r') as f:
                return f.read()

        # Try default location
        default_path = os.path.join(os.path.dirname(__file__), 'vision_instructions.txt')
        if os.path.exists(default_path):
            with open(default_path, 'r') as f:
                return f.read()

        # Fallback instructions
        return """Analyze this image and describe what you see in JSON format with keys:
        environment, lighting, number_of_people, people, animals, objects, confidence"""

    def set_camera(self, cap: cv2.VideoCapture):
        """Set external camera capture (share with VisionService)"""
        with self._camera_lock:
            self.cap = cap
        logger.info("Camera capture shared with OllamaVisionService")

    def _open_camera(self) -> bool:
        """Open camera if not already open"""
        with self._camera_lock:
            if self.cap is not None and self.cap.isOpened():
                return True

            # Try to open camera
            for cam_idx in [self.camera_index, 0, 1, 2]:
                test_cap = cv2.VideoCapture(cam_idx)
                if test_cap.isOpened():
                    ret, _ = test_cap.read()
                    if ret:
                        logger.info(f"Camera opened at index {cam_idx}")
                        test_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                        test_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                        self.cap = test_cap
                        return True
                    test_cap.release()
                else:
                    test_cap.release()

            logger.error("No camera found for OllamaVisionService")
            return False

    def _capture_frame(self) -> Optional[str]:
        """Capture and encode a frame as base64"""
        with self._camera_lock:
            if self.cap is None or not self.cap.isOpened():
                return None

            ret, frame = self.cap.read()
            if not ret:
                return None

        try:
            # Resize if needed
            height, width = frame.shape[:2]
            if max(width, height) > self.max_frame_size:
                scale = self.max_frame_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))

            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to JPEG
            pil_image = Image.fromarray(frame_rgb)
            buffer = io.BytesIO()
            pil_image.save(buffer, format='JPEG', quality=85)
            jpeg_bytes = buffer.getvalue()

            return base64.b64encode(jpeg_bytes).decode('utf-8')

        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            return None

    async def _analyze_frame(self, base64_image: str) -> Optional[SceneContext]:
        """Send frame to Ollama for analysis"""
        try:
            # Build prompt with previous context for consistency
            prompt = self.instructions
            if self.previous_context:
                prompt += f"\n\nPrevious Context (use for consistency):\n{self.previous_context.to_prompt_string()}"

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [base64_image],
                "stream": False,
                "format": "json",  # Enforce structured JSON output
                "options": {
                    "temperature": 0.3,  # Lower temp for more consistent output
                    "num_predict": 800   # Increased to allow complete JSON response
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama API error: {response.status} - {error_text}")
                        return None

                    result = await response.json()
                    raw_response = result.get('response', '')

                    return self._parse_response(raw_response)

        except asyncio.TimeoutError:
            logger.warning("Ollama analysis timed out")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in frame analysis: {e}")
            return None

    def _parse_response(self, response: str) -> Optional[SceneContext]:
        """Parse Ollama response into SceneContext"""
        try:
            # Try to extract JSON from response
            # Handle cases where model wraps JSON in markdown code blocks
            json_str = response.strip()

            if "```json" in json_str:
                start = json_str.find("```json") + 7
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()
            elif "```" in json_str:
                start = json_str.find("```") + 3
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()

            # Find JSON object boundaries
            if '{' in json_str and '}' in json_str:
                start = json_str.find('{')
                end = json_str.rfind('}') + 1
                json_str = json_str[start:end]

            data = json.loads(json_str)

            context = SceneContext(
                environment=data.get('environment', 'Unknown'),
                lighting=data.get('lighting', 'Unknown'),
                number_of_people=data.get('number_of_people', 0),
                people=data.get('people', []),
                animals=data.get('animals', []),
                objects=data.get('objects', []),
                changes_detected=data.get('changes_detected', 'Unknown'),
                confidence=data.get('confidence', 'low'),
                timestamp=time.time(),
                raw_response=response
            )

            return context

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Ollama response as JSON: {e}")
            logger.debug(f"Raw response: {response[:200]}...")

            # Return a basic context with raw description
            return SceneContext(
                environment=response[:100] if response else "Unknown",
                confidence="low",
                timestamp=time.time(),
                raw_response=response
            )

    async def _analysis_loop(self):
        """Background loop for periodic scene analysis"""
        logger.info("Starting Ollama vision analysis loop")

        while self._running:
            try:
                # Capture frame
                base64_image = self._capture_frame()
                if base64_image is None:
                    await asyncio.sleep(self.analysis_interval)
                    continue

                # Analyze with Ollama
                context = await self._analyze_frame(base64_image)

                if context:
                    with self._context_lock:
                        self.previous_context = self.current_context
                        self.current_context = context

                        # Keep history
                        self._context_history.append(context)
                        if len(self._context_history) > self._max_history:
                            self._context_history.pop(0)

                    # Call update callback
                    if self._on_context_update:
                        try:
                            self._on_context_update(context)
                        except Exception as e:
                            logger.error(f"Error in context update callback: {e}")

                    # Track people count stability (require 3 consistent readings before triggering)
                    if context.number_of_people == self._stable_people_count:
                        self._people_count_stable_frames += 1
                    else:
                        # Count changed - start tracking new count
                        self._stable_people_count = context.number_of_people
                        self._people_count_stable_frames = 1

                    # Check for significant changes with cooldown and stability requirements
                    current_time = time.time()
                    time_since_last_comment = current_time - self._last_proactive_comment_time

                    # Only trigger if:
                    # 1. Cooldown has passed (60s)
                    # 2. People count is stable for 3+ readings (15+ seconds at 5s interval)
                    # 3. There's an actual significant change
                    if (time_since_last_comment >= self._proactive_cooldown_seconds and
                        self._people_count_stable_frames >= 3 and
                        context.has_significant_change(self.previous_context)):

                        change_description = context.describe_changes(self.previous_context)

                        # Only trigger for meaningful changes (not just environment text differences)
                        if change_description:  # Only if there's something concrete to describe
                            logger.info(f"Significant scene change (stable): {change_description}")

                            if self._on_scene_change:
                                try:
                                    self._on_scene_change(context, change_description)
                                    self._last_proactive_comment_time = current_time
                                except Exception as e:
                                    logger.error(f"Error in scene change callback: {e}")

                    logger.debug(f"Scene analyzed: {context.environment}, {context.number_of_people} people, confidence={context.confidence}")

            except Exception as e:
                logger.error(f"Error in analysis loop: {e}")

            await asyncio.sleep(self.analysis_interval)

    def start(self, event_loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start the vision service"""
        import time

        if self._running:
            logger.warning("OllamaVisionService already running")
            return

        # Open camera if not shared - retry with delay for camera to come online
        if self.cap is None:
            max_retries = 3
            retry_delay = 1.0  # seconds

            for attempt in range(max_retries):
                if self._open_camera():
                    break
                if attempt < max_retries - 1:
                    logger.info(f"Camera not ready, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
            else:
                logger.error("Cannot start OllamaVisionService: no camera after retries")
                return

        self._running = True
        self._event_loop = event_loop or asyncio.get_event_loop()

        # Start analysis task
        self._analysis_task = self._event_loop.create_task(self._analysis_loop())
        logger.info(f"OllamaVisionService started (interval={self.analysis_interval}s, model={self.model})")

    def stop(self):
        """Stop the vision service"""
        self._running = False

        if self._analysis_task:
            self._analysis_task.cancel()
            self._analysis_task = None

        # Don't close camera if it was shared
        logger.info("OllamaVisionService stopped")

    def get_scene_context(self) -> Optional[SceneContext]:
        """Get the current scene context"""
        with self._context_lock:
            return self.current_context

    def get_scene_context_string(self) -> str:
        """Get scene context formatted as a string for prompts"""
        with self._context_lock:
            if self.current_context is None:
                return "No scene context available yet."
            return self.current_context.to_prompt_string()

    def get_scene_context_json(self) -> Dict[str, Any]:
        """Get scene context as JSON-serializable dict"""
        with self._context_lock:
            if self.current_context is None:
                return {"status": "No scene context available yet"}
            return self.current_context.to_dict()

    def on_scene_change(self, callback: Callable[[SceneContext, str], None]):
        """Register callback for significant scene changes"""
        self._on_scene_change = callback

    def on_context_update(self, callback: Callable[[SceneContext], None]):
        """Register callback for any context update"""
        self._on_context_update = callback


# Global instance for easy access
_ollama_vision_service: Optional[OllamaVisionService] = None


def get_ollama_vision_service() -> Optional[OllamaVisionService]:
    """Get the global OllamaVisionService instance"""
    return _ollama_vision_service


def init_ollama_vision_service(**kwargs) -> OllamaVisionService:
    """Initialize and return the global OllamaVisionService instance"""
    global _ollama_vision_service
    _ollama_vision_service = OllamaVisionService(**kwargs)
    return _ollama_vision_service
