"""
Metrics Service for tracking voice pipeline performance.

Collects and exposes metrics for:
- VAD (Voice Activity Detection) latency
- Speech-to-text timing
- LLM response time
- Text-to-speech timing
- End-to-end latency
- Conversation history
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from collections import deque
from enum import Enum
import logging


class PipelineStage(Enum):
    """Stages of the voice pipeline"""
    VAD_START = "vad_start"              # User starts speaking
    VAD_END = "vad_end"                  # User stops speaking
    STT_START = "stt_start"              # Speech-to-text begins
    STT_END = "stt_end"                  # Transcription complete
    LLM_START = "llm_start"              # LLM processing starts
    LLM_FIRST_TOKEN = "llm_first_token"  # First token received
    LLM_END = "llm_end"                  # LLM response complete
    TTS_START = "tts_start"              # Text-to-speech starts
    TTS_FIRST_AUDIO = "tts_first_audio"  # First audio chunk ready
    TTS_END = "tts_end"                  # TTS complete
    AUDIO_PLAY_START = "audio_play_start"  # Audio playback starts
    AUDIO_PLAY_END = "audio_play_end"    # Audio playback ends


@dataclass
class ConversationTurn:
    """A single conversation turn (user or agent)"""
    turn_id: str
    role: str  # "user" or "agent"
    text: str
    timestamp: float
    duration_ms: Optional[float] = None
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class PipelineMetrics:
    """Metrics for a single voice pipeline execution"""
    turn_id: str
    timestamps: Dict[str, float] = field(default_factory=dict)

    # User speech
    user_text: str = ""
    user_speech_duration_ms: float = 0

    # Agent response
    agent_text: str = ""
    agent_speech_duration_ms: float = 0

    # Computed latencies (in ms)
    vad_latency_ms: float = 0           # Time to detect speech end
    stt_latency_ms: float = 0           # Time to transcribe
    llm_time_to_first_token_ms: float = 0  # Time to first LLM token
    llm_total_latency_ms: float = 0     # Total LLM time
    tts_time_to_first_audio_ms: float = 0  # Time to first audio
    tts_total_latency_ms: float = 0     # Total TTS time

    # End-to-end
    end_to_end_latency_ms: float = 0    # VAD end to first audio out
    total_turn_time_ms: float = 0       # Total time for this turn

    def compute_latencies(self):
        """Compute latency metrics from timestamps"""
        ts = self.timestamps

        # VAD latency
        if PipelineStage.VAD_START.value in ts and PipelineStage.VAD_END.value in ts:
            self.user_speech_duration_ms = (ts[PipelineStage.VAD_END.value] - ts[PipelineStage.VAD_START.value]) * 1000

        # STT latency
        if PipelineStage.STT_START.value in ts and PipelineStage.STT_END.value in ts:
            self.stt_latency_ms = (ts[PipelineStage.STT_END.value] - ts[PipelineStage.STT_START.value]) * 1000

        # LLM latencies
        if PipelineStage.LLM_START.value in ts:
            if PipelineStage.LLM_FIRST_TOKEN.value in ts:
                self.llm_time_to_first_token_ms = (ts[PipelineStage.LLM_FIRST_TOKEN.value] - ts[PipelineStage.LLM_START.value]) * 1000
            if PipelineStage.LLM_END.value in ts:
                self.llm_total_latency_ms = (ts[PipelineStage.LLM_END.value] - ts[PipelineStage.LLM_START.value]) * 1000

        # TTS latencies
        if PipelineStage.TTS_START.value in ts:
            if PipelineStage.TTS_FIRST_AUDIO.value in ts:
                self.tts_time_to_first_audio_ms = (ts[PipelineStage.TTS_FIRST_AUDIO.value] - ts[PipelineStage.TTS_START.value]) * 1000
            if PipelineStage.TTS_END.value in ts:
                self.tts_total_latency_ms = (ts[PipelineStage.TTS_END.value] - ts[PipelineStage.TTS_START.value]) * 1000

        # Audio playback duration
        if PipelineStage.AUDIO_PLAY_START.value in ts and PipelineStage.AUDIO_PLAY_END.value in ts:
            self.agent_speech_duration_ms = (ts[PipelineStage.AUDIO_PLAY_END.value] - ts[PipelineStage.AUDIO_PLAY_START.value]) * 1000

        # End-to-end latency (user stops speaking to agent starts speaking)
        if PipelineStage.VAD_END.value in ts and PipelineStage.AUDIO_PLAY_START.value in ts:
            self.end_to_end_latency_ms = (ts[PipelineStage.AUDIO_PLAY_START.value] - ts[PipelineStage.VAD_END.value]) * 1000

        # Total turn time
        if PipelineStage.VAD_START.value in ts and PipelineStage.AUDIO_PLAY_END.value in ts:
            self.total_turn_time_ms = (ts[PipelineStage.AUDIO_PLAY_END.value] - ts[PipelineStage.VAD_START.value]) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "turn_id": self.turn_id,
            "user_text": self.user_text,
            "agent_text": self.agent_text,
            "user_speech_duration_ms": round(self.user_speech_duration_ms, 2),
            "agent_speech_duration_ms": round(self.agent_speech_duration_ms, 2),
            "stt_latency_ms": round(self.stt_latency_ms, 2),
            "llm_time_to_first_token_ms": round(self.llm_time_to_first_token_ms, 2),
            "llm_total_latency_ms": round(self.llm_total_latency_ms, 2),
            "tts_time_to_first_audio_ms": round(self.tts_time_to_first_audio_ms, 2),
            "tts_total_latency_ms": round(self.tts_total_latency_ms, 2),
            "end_to_end_latency_ms": round(self.end_to_end_latency_ms, 2),
            "total_turn_time_ms": round(self.total_turn_time_ms, 2),
            "timestamps": {k: round(v, 4) for k, v in self.timestamps.items()}
        }


class MetricsService:
    """Service for collecting and exposing voice pipeline metrics"""

    MAX_HISTORY = 100  # Keep last 100 turns

    def __init__(self):
        self._lock = threading.Lock()
        self._current_turn: Optional[PipelineMetrics] = None
        self._turn_history: deque = deque(maxlen=self.MAX_HISTORY)
        self._conversation_history: deque = deque(maxlen=self.MAX_HISTORY * 2)
        self._turn_counter = 0

        # Current state
        self._agent_state = "idle"
        self._is_user_speaking = False
        self._is_agent_speaking = False

        # Aggregate metrics
        self._total_turns = 0
        self._avg_e2e_latency_ms = 0
        self._avg_llm_ttft_ms = 0
        self._avg_tts_ttfa_ms = 0

        # LiveKit native metrics (last values)
        self._last_realtime_metrics = {}
        self._last_tts_metrics = {}
        self._last_stt_metrics = {}
        self._last_vad_metrics = {}
        self._last_eou_metrics = {}

        # Session start time
        self._session_start = time.time()

        # Token tracking
        self._session_input_tokens = 0
        self._session_output_tokens = 0
        self._total_tokens_all_time = 0  # Loaded from config
        self._load_total_tokens()

        logging.info("MetricsService initialized")

    def _load_total_tokens(self):
        """Load total tokens from config"""
        try:
            import lelamp.globals as g
            if g.CONFIG and "metrics" in g.CONFIG:
                self._total_tokens_all_time = g.CONFIG["metrics"].get("total_tokens", 0)
                logging.info(f"Loaded total tokens from config: {self._total_tokens_all_time}")
        except Exception as e:
            logging.warning(f"Could not load total tokens from config: {e}")

    def _save_total_tokens(self):
        """Save total tokens to config"""
        try:
            import lelamp.globals as g
            if g.CONFIG is not None:
                if "metrics" not in g.CONFIG:
                    g.CONFIG["metrics"] = {}
                g.CONFIG["metrics"]["total_tokens"] = self._total_tokens_all_time
                g.save_config(g.CONFIG)
        except Exception as e:
            logging.warning(f"Could not save total tokens to config: {e}")

    def record_livekit_metrics(self, metrics_obj):
        """Record LiveKit's native metrics object"""
        with self._lock:
            metric_type = getattr(metrics_obj, 'type', 'unknown')

            if metric_type == 'realtime_model_metrics':
                self._last_realtime_metrics = {
                    'ttft_ms': metrics_obj.ttft * 1000 if metrics_obj.ttft > 0 else 0,
                    'duration_ms': metrics_obj.duration * 1000,
                    'total_tokens': metrics_obj.total_tokens,
                    'input_tokens': metrics_obj.input_tokens,
                    'output_tokens': metrics_obj.output_tokens,
                    'tokens_per_second': metrics_obj.tokens_per_second,
                    'cancelled': metrics_obj.cancelled,
                    'timestamp': metrics_obj.timestamp
                }
                # Update current turn with LLM metrics
                if self._current_turn and metrics_obj.ttft > 0:
                    self._current_turn.llm_time_to_first_token_ms = metrics_obj.ttft * 1000
                    self._current_turn.llm_total_latency_ms = metrics_obj.duration * 1000

                # Accumulate tokens for session and total
                if metrics_obj.input_tokens > 0:
                    self._session_input_tokens += metrics_obj.input_tokens
                    self._total_tokens_all_time += metrics_obj.input_tokens
                if metrics_obj.output_tokens > 0:
                    self._session_output_tokens += metrics_obj.output_tokens
                    self._total_tokens_all_time += metrics_obj.output_tokens
                # Save total tokens periodically (every turn end will also save)
                self._save_total_tokens()

            elif metric_type == 'tts_metrics':
                self._last_tts_metrics = {
                    'ttfb_ms': metrics_obj.ttfb * 1000,
                    'duration_ms': metrics_obj.duration * 1000,
                    'audio_duration_s': metrics_obj.audio_duration,
                    'characters': metrics_obj.characters_count,
                    'cancelled': metrics_obj.cancelled,
                    'timestamp': metrics_obj.timestamp
                }
                if self._current_turn:
                    self._current_turn.tts_time_to_first_audio_ms = metrics_obj.ttfb * 1000
                    self._current_turn.tts_total_latency_ms = metrics_obj.duration * 1000

            elif metric_type == 'stt_metrics':
                self._last_stt_metrics = {
                    'duration_ms': metrics_obj.duration * 1000,
                    'audio_duration_s': metrics_obj.audio_duration,
                    'streamed': metrics_obj.streamed,
                    'timestamp': metrics_obj.timestamp
                }
                if self._current_turn:
                    self._current_turn.stt_latency_ms = metrics_obj.duration * 1000

            elif metric_type == 'vad_metrics':
                self._last_vad_metrics = {
                    'idle_time_s': metrics_obj.idle_time,
                    'inference_count': metrics_obj.inference_count,
                    'inference_duration_total_ms': metrics_obj.inference_duration_total * 1000,
                    'timestamp': metrics_obj.timestamp
                }

            elif metric_type == 'eou_metrics':
                self._last_eou_metrics = {
                    'end_of_utterance_delay_ms': metrics_obj.end_of_utterance_delay * 1000,
                    'transcription_delay_ms': metrics_obj.transcription_delay * 1000,
                    'on_user_turn_completed_delay_ms': metrics_obj.on_user_turn_completed_delay * 1000,
                    'timestamp': metrics_obj.timestamp
                }

    def start_turn(self) -> str:
        """Start a new conversation turn"""
        with self._lock:
            self._turn_counter += 1
            turn_id = f"turn_{self._turn_counter}"
            self._current_turn = PipelineMetrics(turn_id=turn_id)
            return turn_id

    def record_timestamp(self, stage: PipelineStage, turn_id: Optional[str] = None):
        """Record a timestamp for a pipeline stage"""
        with self._lock:
            if self._current_turn is None:
                if turn_id:
                    self._current_turn = PipelineMetrics(turn_id=turn_id)
                else:
                    return

            self._current_turn.timestamps[stage.value] = time.time()

    def set_user_text(self, text: str):
        """Set the user's transcribed text"""
        with self._lock:
            if self._current_turn:
                self._current_turn.user_text = text
                # Add to conversation history
                self._conversation_history.append(ConversationTurn(
                    turn_id=self._current_turn.turn_id,
                    role="user",
                    text=text,
                    timestamp=time.time()
                ))

    def set_agent_text(self, text: str):
        """Set the agent's response text"""
        with self._lock:
            if self._current_turn:
                self._current_turn.agent_text = text
                # Add to conversation history
                self._conversation_history.append(ConversationTurn(
                    turn_id=self._current_turn.turn_id,
                    role="agent",
                    text=text,
                    timestamp=time.time()
                ))

    def append_agent_text(self, text: str):
        """Append to the agent's response text (for streaming)"""
        with self._lock:
            if self._current_turn:
                self._current_turn.agent_text += text

    def end_turn(self):
        """End the current turn and compute metrics"""
        with self._lock:
            if self._current_turn:
                self._current_turn.compute_latencies()
                self._turn_history.append(self._current_turn)
                self._total_turns += 1

                # Update aggregates
                self._update_aggregates()

                logging.debug(f"Turn {self._current_turn.turn_id} completed: E2E={self._current_turn.end_to_end_latency_ms:.1f}ms")
                self._current_turn = None

    def _update_aggregates(self):
        """Update aggregate metrics"""
        if not self._turn_history:
            return

        e2e_latencies = [t.end_to_end_latency_ms for t in self._turn_history if t.end_to_end_latency_ms > 0]
        llm_ttfts = [t.llm_time_to_first_token_ms for t in self._turn_history if t.llm_time_to_first_token_ms > 0]
        tts_ttfas = [t.tts_time_to_first_audio_ms for t in self._turn_history if t.tts_time_to_first_audio_ms > 0]

        if e2e_latencies:
            self._avg_e2e_latency_ms = sum(e2e_latencies) / len(e2e_latencies)
        if llm_ttfts:
            self._avg_llm_ttft_ms = sum(llm_ttfts) / len(llm_ttfts)
        if tts_ttfas:
            self._avg_tts_ttfa_ms = sum(tts_ttfas) / len(tts_ttfas)

    def set_agent_state(self, state: str):
        """Update the current agent state"""
        with self._lock:
            self._agent_state = state
            self._is_agent_speaking = (state == "speaking")

    def set_user_speaking(self, is_speaking: bool):
        """Update whether the user is speaking"""
        with self._lock:
            self._is_user_speaking = is_speaking

    def reset_session(self):
        """Reset session metrics (called when a new session starts)"""
        with self._lock:
            self._session_input_tokens = 0
            self._session_output_tokens = 0
            self._total_turns = 0
            self._turn_history.clear()
            self._conversation_history.clear()
            self._turn_counter = 0
            self._session_start = time.time()
            self._avg_e2e_latency_ms = 0
            self._avg_llm_ttft_ms = 0
            self._avg_tts_ttfa_ms = 0
            logging.info("Session metrics reset")

    def get_token_stats(self) -> Dict[str, int]:
        """Get token statistics"""
        with self._lock:
            return {
                "session_input": self._session_input_tokens,
                "session_output": self._session_output_tokens,
                "session_total": self._session_input_tokens + self._session_output_tokens,
                "all_time_total": self._total_tokens_all_time
            }

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot for WebUI"""
        with self._lock:
            session_duration = time.time() - self._session_start

            # Get recent turns for display
            recent_turns = list(self._turn_history)[-10:]

            return {
                "session": {
                    "duration_seconds": round(session_duration, 1),
                    "total_turns": self._total_turns,
                    "start_time": self._session_start
                },
                "tokens": {
                    "session_input": self._session_input_tokens,
                    "session_output": self._session_output_tokens,
                    "session_total": self._session_input_tokens + self._session_output_tokens,
                    "all_time_total": self._total_tokens_all_time
                },
                "current_state": {
                    "agent_state": self._agent_state,
                    "is_user_speaking": self._is_user_speaking,
                    "is_agent_speaking": self._is_agent_speaking
                },
                "current_turn": self._current_turn.to_dict() if self._current_turn else None,
                "averages": {
                    "end_to_end_latency_ms": round(self._avg_e2e_latency_ms, 2),
                    "llm_time_to_first_token_ms": round(self._avg_llm_ttft_ms, 2),
                    "tts_time_to_first_audio_ms": round(self._avg_tts_ttfa_ms, 2)
                },
                "recent_turns": [t.to_dict() for t in recent_turns],
                "conversation": [
                    {
                        "role": c.role,
                        "text": c.text,
                        "timestamp": c.timestamp,
                        "turn_id": c.turn_id
                    }
                    for c in list(self._conversation_history)[-20:]
                ],
                "livekit_metrics": {
                    "realtime": self._last_realtime_metrics,
                    "tts": self._last_tts_metrics,
                    "stt": self._last_stt_metrics,
                    "vad": self._last_vad_metrics,
                    "eou": self._last_eou_metrics
                }
            }

    def get_latency_breakdown(self) -> Dict[str, Any]:
        """Get detailed latency breakdown for the last turn"""
        with self._lock:
            if not self._turn_history:
                return {}

            last_turn = self._turn_history[-1]
            return {
                "turn_id": last_turn.turn_id,
                "breakdown": {
                    "user_speech": last_turn.user_speech_duration_ms,
                    "stt": last_turn.stt_latency_ms,
                    "llm_ttft": last_turn.llm_time_to_first_token_ms,
                    "llm_total": last_turn.llm_total_latency_ms,
                    "tts_ttfa": last_turn.tts_time_to_first_audio_ms,
                    "tts_total": last_turn.tts_total_latency_ms,
                    "end_to_end": last_turn.end_to_end_latency_ms,
                    "agent_speech": last_turn.agent_speech_duration_ms,
                    "total_turn": last_turn.total_turn_time_ms
                }
            }


# Global singleton instance
_metrics_service: Optional[MetricsService] = None


def get_metrics_service() -> MetricsService:
    """Get the global metrics service instance"""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
