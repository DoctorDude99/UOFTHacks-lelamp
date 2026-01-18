import sounddevice as sd
import logging
import threading
from typing import Callable, Optional

from deepgram import AsyncDeepgramClient
import asyncio
from deepgram.core.events import EventType

import websockets
import json
import base64
import os
import queue
from dotenv import load_dotenv
from groq import Groq
from lelamp.service.agent.tools import Tool

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger("Agent_Service")

load_dotenv()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

from lelamp.functions import (
    MotorFunctions,
    RGBFunctions,
    AnimationFunctions,
    AudioFunctions,
    TimerFunctions,
    WorkflowFunctions,
    SensorFunctions,
    SleepFunctions,
    VisionFunctions,
    LocationFunctions,
)
import lelamp.globals as g
from lelamp.service.theme import ThemeSound
class Agent(
    MotorFunctions,
    RGBFunctions,
    AnimationFunctions,
    AudioFunctions,
    TimerFunctions,
    WorkflowFunctions,
    SensorFunctions,
    SleepFunctions,
    VisionFunctions,
    # SpotifyFunctions,
    LocationFunctions,
):
    def __init__(self):
        super().__init__()
        """
        Initialize LeLamp agent.

        Services are already initialized by server.py and available in globals.
        The agent consumes these services and adds AI-specific behavior.

        Args:
            config: Configuration dict. If None, uses global CONFIG.
        """
        # Use provided config or fall back to global
        config = g.CONFIG
        self.config = config

        # Get services from globals (initialized by server.py)
        self.animation_service = g.animation_service
        self.rgb_service = g.rgb_service
        self.audio_service = g.audio_service
        self.theme_service = g.theme_service
        self.workflow_service = g.workflow_service
        self.spotify_service = g.spotify_service

        # Check if motors are available
        self.motors_enabled = self.animation_service is not None
        self.rgb_enabled = self.rgb_service is not None

        # Session references (set by pipeline)
        self.agent_session = None
        self.event_loop = None

        # Sleep mode state
        self.is_sleeping = False

        # Activity tracking for idle timeout
        self.last_activity_time = None
        self.idle_timeout_task = None
        self.workflow_progression_task = None
        self.rgb_config = config.get("rgb", {})

        # Agent-specific service setup
        # self._setup_workflow_service()
        # self._setup_spotify_service()
        # self._setup_alarm_service()

        # Play startup animation and sound
        if self.theme_service:
            self.theme_service.play(ThemeSound.STARTUP)

        if self.animation_service:
            self.animation_service.dispatch("play", "wake_up")

        if self.rgb_service:
            default_anim = self.rgb_config.get("default_animation", "aura_glow")
            self.rgb_service.dispatch("animation", {
                "name": default_anim,
                "color": tuple(self.rgb_config.get("default_color", [255, 255, 255]))
            })

        logger.info("LeLamp agent initialized (using services from globals)")
    def _mark_activity(self):
        """Mark that activity occurred (for idle timeout)."""
        import time
        self.last_activity_time = time.time()

    def _set_system_volume(self, volume_percent: int):
        """Set system playback volume."""
        import subprocess
        try:
            subprocess.run(
                ["amixer", "sset", "PCM", f"{volume_percent}%"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

    def _set_system_microphone_volume(self, volume_percent: int):
        """Set system microphone/capture volume."""
        import subprocess
        try:
            for control in ['Capture', 'ADC', 'ADC PCM']:
                subprocess.run(
                    ["amixer", "sset", control, f"{volume_percent}%"],
                    capture_output=True, timeout=5
                )
        except Exception:
            pass

async def init_agent_service():
    bot = LLM()
    await bot.start()

class LLM:
    def __init__(self):
        # Configuration
        self.API_KEY = os.getenv("OPENAI_API_KEY")  # Or fill in "sk-..." directly
        # Use the latest Realtime model
        self.URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"#-2024-10-01"

        # Audio configuration (OpenAI Realtime API standard is 24kHz PCM16 Mono)
        self.SAMPLE_RATE = 24000
        self.CHANNELS = 1
        self.DTYPE = 'int16'
        self.CHUNK_SIZE = 1024  # Size of audio frame read each time

        # Thread-safe queue for transferring data between audio callback and asyncio
        self.input_queue = asyncio.Queue()
        self.output_queue = queue.Queue()

        self.agent = Agent()

    def _fix_tools_format(self, original_tools):
        """Convert Chat Completion format tools to Realtime API format"""
        fixed_tools = []
        for t in original_tools:
            # If it is the old format {"type": "function", "function": {"name":...}}
            if "function" in t:
                func_def = t["function"]
                fixed_tools.append({
                    "type": "function",
                    "name": func_def.get("name"),
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {})
                })
            # If it is already the new format (with name at the top level), use it directly
            elif "name" in t:
                fixed_tools.append(t)
        return fixed_tools

    def input_callback(self, indata, frames, time, status):
        """Microphone recording callback: put recorded raw audio data into the queue"""
        # if status:
        #     print(status)
        # Convert numpy array to bytes
        audio_bytes = indata.tobytes()
        # Note: We cannot use await directly here because this runs in a non-async thread
        # We use asyncio.run_coroutine_threadsafe or simple loop.call_soon_threadsafe
        # For simplicity, we use put_nowait of asyncio.Queue (if in the same loop)
        # But since this is cross-thread, standard queue with async wrapper is usually more robust,
        # Or handle directly in the main loop. Here for code brevity, we assume the loop is running.
        try:
            self.loop.call_soon_threadsafe(self.input_queue.put_nowait, audio_bytes)
        except Exception as e:
            pass

    async def send_audio(self, websocket):
        """Continuously read data from microphone queue and send to OpenAI"""
        while True:
            audio_bytes = await self.input_queue.get()
            # Base64 encoding
            base64_audio = base64.b64encode(audio_bytes).decode('utf-8')

            # Send input_audio_buffer.append event
            event = {
                "type": "input_audio_buffer.append",
                "audio": base64_audio
            }
            await websocket.send(json.dumps(event))

    async def receive(self, websocket):
        """Continuously receive OpenAI responses and put into playback queue"""
        async for message in websocket:
            event = json.loads(message)
            event_type = event.get("type")
            current_stream_type = None
            # print(message)

            # Print some logs for debugging
            # --- 1. User Voice Transcription Result (User Input) ---
            # Need to enable input_audio_transcription in session to receive this event
            if event_type == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "").strip()
                if transcript:
                    if current_stream_type: print("") # Newline
                    print(f"[User Voice Transcription]: {transcript}")
                    current_stream_type = None

            # --- 2. AI Text Streaming Output (AI Response) ---
            # Because modalities=["text"], we listen to response.text.delta instead of audio
            elif event_type == "response.text.delta":
                delta = event.get("delta", "")
                if current_stream_type != "text":
                    print(f"[AI Response]: ", end="")
                    current_stream_type = "text"
                print(delta, end="", flush=True)

            # --- 3. Response Ended ---
            elif event_type == "response.done":
                if current_stream_type == "text":
                    print(f"") # End color
                    current_stream_type = None

            elif event['type'] == "response.function_call_arguments.done":
                # AI has generated complete function call arguments
                call_id = event["call_id"]
                name = event["name"]
                arguments = event["arguments"]

                print(f"\n[System] AI requests tool call: {name}({arguments})")
                output_str = await Tool.execute(name, arguments, self.agent)
                # 1. Create a new conversation item (Item) consisting of tool output
                item_create_event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,  # Must correspond to the previous call_id
                        "output": output_str
                    }
                }
                await websocket.send(json.dumps(item_create_event))

                # 2. Tell AI: "Result given to you, now please reply to me based on this result" (triggers response.create)
                response_create_event = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text"],
                    }
                }
                await websocket.send(json.dumps(response_create_event))

    async def start(self):
        self.loop = asyncio.get_running_loop()

        headers = {
            "Authorization": "Bearer " + self.API_KEY,
            "OpenAI-Beta": "realtime=v1"
        }

        print("Connecting to OpenAI Realtime API...")
        async with websockets.connect(self.URL, additional_headers=headers) as websocket:
            system_prompt = "You always think and response in English no matter what language the user speaks. You're a cute lamp who DON'T speak, and the words you say are NOT visible to the user. Use your language as thinking process in your brain. The only way you can interact with the user is calling functions. Use the functions to response the user. For example, when you feel said you should look down and turn led to cold color. When you're happy you should turn your led to warm color and play positive animation. When you're excited you should make your led bright and colorful, and call multiple actions to be hyperactive. For another example, when the user ask you the weather, you can query thr weather first and user warm yellow to represent sunny or cold blue to represent rainy."
            # 1. Initialize session (Optional: set voice, VAD mode, etc.)
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "voice": "alloy",  # Optional: alloy, ash, ballad, coral, echo, sage, shimmer, verse
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",  # Enable server-side voice activity detection (auto interruption, auto reply)
                    },
                    "tools": self._fix_tools_format(Tool.tools_schema),
                    "tool_choice": "auto",
                    "input_audio_transcription": {
                        "model": "whisper-1",
                        },
                    "instructions": system_prompt.strip()
                }
            }
            await websocket.send(json.dumps(session_update))

            input_stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                callback=self.input_callback,
                blocksize=self.CHUNK_SIZE
        )

            with input_stream:
                # 3. Run send and receive tasks concurrently
                send_task = asyncio.create_task(self.send_audio(websocket))
                receive_task = asyncio.create_task(self.receive(websocket))

                try:
                    await asyncio.gather(send_task, receive_task)
                except KeyboardInterrupt:
                    print("Stopping conversation...")

if __name__ == "__main__":
    asyncio.run(init_agent_service())

# Below are not using
class LLM_groq:
    def __init__(self):
        self.is_speaking = False
        self.response_queue = queue.Queue()
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.chat_history = [
            {
                "role": "system",
                "content": ""
            }
        ]
        self.agent = Agent()

    def handle_interruption(self):
        """
        Interruption callback
        """
        pass  # Not Implemented

    async def handle_user_input(self, text):
        """
        Full sentence process callback
        """
        try:
            logger.info(f"LLM received from user, requesting: {text}'")
            self.chat_history.append({"role": "user", "content": text})
            chat_completion = self.client.chat.completions.create(
                messages=self.chat_history,
                model="llama-3.3-70b-versatile",
                tools=Tool.tools_schema[:3],
                tool_choice="required",

            )
            message = chat_completion.choices[0].message
            logger.info(f"LLM response received: {message}")
        except Exception as e:
            logger.critical(f"Error{e}")
        # Check if tools called
        if message.tool_calls:
            logger.info(f"LLM Calling {len(message.tool_calls) }tools...")

            # 4. Execute tools sequentially
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                args = tool_call.function.arguments
                call_id = tool_call.id

                logger.info(f"   -> Execute: {func_name}({args})")
                result = await Tool.execute(func_name, args, self.agent) or "Success"
                logger.info(f"   <- Result: {result}")

                # 5. Save result as role='tool' into history
                self.chat_history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": func_name,
                    "content": result
                })

            # 6. Second round call: send tool result back to LLM to get final reply
            logger.info("Second request")
            final_completion = self.client.chat.completions.create(
                messages=self.chat_history,
                model="llama-3.3-70b-versatile",
                # Second round usually doesn't need to force tool_choice unless it's a multi-step complex task
            )
            final_response = final_completion.choices[0].message.content
            self.chat_history.append({"role": "assistant", "content": final_response})
            logger.info(f"Final response: {message.content}")
            return final_response

        else:
            # No tool call, output
            logger.info(f"Final response: {message.content}")
            return message.content

    def handle_transcript_update(self, text, is_final):
        pass  # Not Implemented or legacy

    def synthesize_and_play(self, text):
        pass  # Not Implemented

class FluxListener:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(FluxListener, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.dg_client: Optional[AsyncDeepgramClient] = None
        self.dg_connection = None
        self.input_stream = None
        self.is_running = False
        self._loop = None
        self._connection_task = None

        # Callback functions container
        self.on_speech_start: Optional[Callable] = None
        self.on_transcript_update: Optional[Callable] = None
        self.on_turn_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

        self._transcript_buffer = []
        self._initialized = True

    def initialize(self,
                   api_key: str,
                   on_speech_start: Callable = None,
                   on_turn_complete: Callable = None,
                   on_transcript_update: Callable = None,
                   device_index: int = None):
        """
        Deepgram and callback functions configuration
        """
        self.dg_client = AsyncDeepgramClient(api_key=api_key)
        self.on_speech_start = on_speech_start
        self.on_turn_complete = on_turn_complete
        self.on_transcript_update = on_transcript_update
        self.device_index = device_index

        logger.info("FluxListener initialized (Singleton).")

    async def start(self):
        """Connect to Deepgram and Microphone"""
        if self.is_running:
            logger.warning("Listener is already running.")
            return

        # Create or get the event loop
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._loop.run_forever, daemon=True).start()

        # Sounddevice input stream
        try:
            self.input_stream = sd.InputStream(
                device=self.device_index,
                channels=1,
                samplerate=16000,
                dtype="int16",
                callback=self._audio_callback,
                blocksize=1024
            )
            self.input_stream.start()
            self.is_running = True
            logger.info("Microphone listening started...")

        except Exception as e:
            logger.error(f"Microphone Error: {e}")
            self.stop()
        await self._run_connection()

    async def _run_connection(self):
        try:
            options = {
                "model": "flux-general-en",
                "encoding": "linear16",
                "sample_rate": "16000",
                "eot_timeout_ms": 1000,
            }

            # Keep connection open
            async with self.dg_client.listen.v2.connect(**options) as connection:
                self.dg_connection = connection
                self._register_events(connection)
                await connection.start_listening()

                # Keep connection active until stop() is called
                while self.is_running:
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Deepgram Connection Error: {e}")
            if self.on_error:
                self.on_error(e)

    def stop(self):
        """Stop listening and release resources"""
        self.is_running = False

        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None

        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        logger.info("FluxListener stopped.")

    def _audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice"""
        if status:
            logger.warning(f"Audio status: {status}")

        if self.dg_connection and self.is_running:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(
                        self.dg_connection.send_media(bytes(indata))
                    )
                )

    def _dispatch_callback(self, callback, *args):
        if not callback:
            return
        if asyncio.iscoroutinefunction(callback):
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(callback(*args), self._loop)
            else:
                logger.error("Event loop is not running, cannot schedule async callback")
        else:
            callback(*args)

    def _register_events(self, connection):
        """Bind the event with external callback functions"""

        def on_message(message):
            if hasattr(message, 'type'):
                if message.type == "TurnInfo":
                    if hasattr(message, 'event') and message.event=='EndOfTurn':
                        transcript = message.transcript
                        self._dispatch_callback(self.on_turn_complete, transcript)

            else:
                print(message)
        def on_speech_started():
            """Interrupt"""
            logger.info(">> User started speaking (Barge-in)")
            if self.on_speech_start:
                self.on_speech_start()

        def on_utterance_end():
            """EOT"""
            if self._transcript_buffer:
                full_text = " ".join(self._transcript_buffer).strip()
                self._transcript_buffer = []

                logger.info(f"End of turn detected. Text: {full_text}")

                if self.on_turn_complete and full_text:
                    self.on_turn_complete(full_text)

        connection.on(EventType.MESSAGE, on_message)
        connection.on(EventType.OPEN, lambda _: logger.info("Connection opened"))
        connection.on(EventType.CLOSE, lambda _: logger.info("Connection closed"))
        connection.on(EventType.ERROR, lambda error: logger.error(f"Error: {error}"))

async def init_agent_service_groq():
    # 1. Instantiate business logic
    bot = LLM()

    # 2. Get singleton auditory module
    listener = FluxListener()

    # 3. Initialize and inject dependencies (Dependency Injection)
    # Key point: pass bot methods to listener to achieve decoupling
    listener.initialize(
        api_key=DEEPGRAM_API_KEY,
        on_speech_start=bot.handle_interruption,       # Bind interruption logic
        on_turn_complete=bot.handle_user_input,        # Bind conversation logic
        on_transcript_update=bot.handle_transcript_update # Bind UI logic
    )

    # 4. Start
    print("System starting... (Press Ctrl+C to exit)")
    await listener.start()