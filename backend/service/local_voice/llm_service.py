"""
Local LLM service using Ollama with tool calling support.

Adapted from ~/Faster-Local-Voice-AI-Whisper/server.py with tool calling added.
"""

import asyncio
import json
import re
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable

try:
    import aiohttp
except ImportError:
    aiohttp = None

logger = logging.getLogger(__name__)


def clean_response(text: str) -> str:
    """Clean LLM response for TTS."""
    # Normalize quotes
    text = text.replace("'", "'").replace("'", "'").replace("`", "'").replace("''", "'")
    # Remove emojis
    text = re.sub(
        r"[\U0001F000-\U0001FFFF\U00002700-\U000027BF\U00002600-\U000026FF]+", "", text
    )
    # Remove markdown formatting
    text = re.sub(r"[*]+", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"<.*?>", "", text)
    # Normalize whitespace
    text = text.replace("\n", " ").strip()
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.?!])", r"\1", text)
    text = re.sub(r"(\w+)\s*'\s*(\w+)", r"\1'\2", text)
    text = re.sub(r"([.!?])([^\s.!?])", r"\1 \2", text)
    return text


def split_sentences(text: str) -> List[str]:
    """Split text into sentences for streaming TTS."""
    text = text.replace("\n", " ").replace("—", ", ").replace("--", ", ")

    # Split on sentence endings
    sentence_endings = (
        r"(?<=[.!?])(?:\s+|$)(?!(?:Mr|Mrs|Ms|Dr|Sr|Jr|Prof|St|Ave|Inc|Corp|[0-9])\.)"
    )
    sentences = [s.strip() for s in re.split(sentence_endings, text) if s.strip()]

    # Further split long sentences on commas
    result = []
    for sentence in sentences:
        if len(sentence) > 80 and "," in sentence:
            parts = re.split(r",\s+", sentence)
            for j, part in enumerate(parts):
                part = part.strip()
                if part:
                    if j < len(parts) - 1:
                        part += ","
                    result.append(part)
        else:
            result.append(sentence)

    return result


class LocalLLMService:
    """Local LLM service using Ollama with tool calling support."""

    def __init__(
        self,
        model: str = "llama3.2:3b",
        ollama_url: str = "http://localhost:11434",
        context_length: int = 2048,
        temperature: float = 0.7,
        history_length: int = 10,
    ):
        if aiohttp is None:
            raise ImportError("aiohttp not installed. Run: pip install aiohttp")

        self.model = model
        self.ollama_url = ollama_url
        self.context_length = context_length
        self.temperature = temperature
        self.history_length = history_length

        self.chat_history: List[Dict[str, str]] = []
        self.system_prompt = ""

        # Tool registry
        self.tools: List[Dict[str, Any]] = []
        self.tool_handlers: Dict[str, Callable] = {}

        # Metrics
        self.last_ttft: float = 0  # Time to first token
        self.last_total_time: float = 0

    def set_system_prompt(self, prompt: str):
        """Set the system prompt."""
        self.system_prompt = prompt

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
    ):
        """
        Register a function tool that Ollama can call.

        Args:
            name: Tool function name
            description: Description for the LLM
            parameters: JSON schema for parameters
            handler: Async function to call
        """
        self.tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
        self.tool_handlers[name] = handler
        logger.debug(f"Registered tool: {name}")

    def register_tools_from_list(self, tools: List[Dict[str, Any]]):
        """
        Register multiple tools from a list.

        Args:
            tools: List of tool dicts with name, description, parameters, handler
        """
        for tool in tools:
            self.register_tool(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["parameters"],
                handler=tool["handler"],
            )

    async def warm_up(self):
        """Warm up the Ollama model with a simple query."""
        logger.info(f"Warming up Ollama model: {self.model}")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello"},
                    ],
                    "stream": False,
                }
                async with session.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    await response.json()
            logger.info("Ollama model warmed up")
        except Exception as e:
            logger.warning(f"Ollama warm-up failed: {e}")

    async def generate_response(
        self, user_text: str, include_tools: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response from Ollama.

        Handles tool calls automatically and yields text tokens.

        Args:
            user_text: User's input text
            include_tools: Whether to include registered tools

        Yields:
            Text tokens from the response
        """
        import time

        if user_text:
            self.chat_history.append({"role": "user", "content": user_text})

        # Build messages with history limit
        messages = [{"role": "system", "content": self.system_prompt}]
        if self.history_length > 0:
            messages.extend(self.chat_history[-self.history_length :])
        else:
            messages.extend(self.chat_history)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_ctx": self.context_length,
                "temperature": self.temperature,
            },
        }

        # Add tools if available and requested
        if include_tools and self.tools:
            payload["tools"] = self.tools

        llm_start = time.time()
        first_token_time = None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    full_response = ""
                    tool_calls = []

                    async for line in response.content:
                        if not line:
                            continue

                        try:
                            chunk = json.loads(line.decode().strip())
                        except json.JSONDecodeError:
                            continue

                        # Check for tool calls
                        message = chunk.get("message", {})
                        if "tool_calls" in message:
                            tool_calls.extend(message["tool_calls"])

                        # Yield text tokens
                        token = message.get("content", "")
                        if token:
                            if first_token_time is None:
                                first_token_time = time.time()
                                self.last_ttft = (first_token_time - llm_start) * 1000
                                logger.debug(f"LLM TTFT: {self.last_ttft:.0f}ms")

                            # Clean token
                            token = clean_response(token)
                            if token:
                                full_response += token
                                yield token

                    self.last_total_time = (time.time() - llm_start) * 1000

                    # Handle tool calls
                    if tool_calls:
                        for tool_call in tool_calls:
                            func_name = tool_call.get("function", {}).get("name")
                            func_args = tool_call.get("function", {}).get(
                                "arguments", {}
                            )

                            if func_name in self.tool_handlers:
                                logger.info(f"Executing tool: {func_name}({func_args})")
                                try:
                                    # Execute the tool
                                    handler = self.tool_handlers[func_name]
                                    if asyncio.iscoroutinefunction(handler):
                                        result = await handler(**func_args)
                                    else:
                                        result = handler(**func_args)

                                    # Add tool result to history
                                    self.chat_history.append(
                                        {
                                            "role": "tool",
                                            "content": str(result),
                                            "name": func_name,
                                        }
                                    )

                                    logger.info(f"Tool result: {str(result)[:100]}")

                                    # Generate follow-up response with tool result
                                    async for token in self.generate_response(
                                        "", include_tools=False
                                    ):
                                        yield token
                                    return

                                except Exception as e:
                                    logger.error(f"Tool execution error: {e}")
                                    # Add error to history
                                    self.chat_history.append(
                                        {
                                            "role": "tool",
                                            "content": f"Error: {str(e)}",
                                            "name": func_name,
                                        }
                                    )
                            else:
                                logger.warning(f"Unknown tool: {func_name}")

                    # Add assistant response to history
                    if full_response:
                        self.chat_history.append(
                            {"role": "assistant", "content": full_response}
                        )

        except asyncio.TimeoutError:
            logger.error("Ollama request timed out")
            yield "Sorry, I'm having trouble responding right now."
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield "Sorry, something went wrong."

    async def generate_simple(self, prompt: str) -> str:
        """
        Generate a simple non-streaming response.

        Args:
            prompt: Direct prompt (not added to history)

        Returns:
            Complete response text
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                result = await response.json()
                return result.get("message", {}).get("content", "")

    def clear_history(self):
        """Clear chat history."""
        self.chat_history = []
