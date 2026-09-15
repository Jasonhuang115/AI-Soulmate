from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import AsyncOpenAI

from asm.core.config import Settings
from asm.core.interfaces import Message, ToolSpec
from memory.supervisor import CompletionMessage, ToolCallDelta


@dataclass(frozen=True, slots=True)
class TokenEvent:
    kind: str
    text: str = ""
    tool_id: str = ""
    tool_name: str = ""
    tool_arguments: str = ""


class ChatStreamer(Protocol):
    def stream_chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[TokenEvent]: ...


class DeepSeekClient:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[TokenEvent]:
        payload: dict[str, Any] = {
            "model": self._settings.deepseek_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": 1.3,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    },
                }
                for spec in tools
            ]
        stream = await self._client.chat.completions.create(**payload)
        try:
            async for chunk in stream:
                if cancel_event.is_set():
                    return
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None or choice.delta is None:
                    continue
                delta = choice.delta
                if delta.content:
                    yield TokenEvent(kind="text", text=delta.content)
                for call in delta.tool_calls or []:
                    fn = call.function
                    yield TokenEvent(
                        kind="tool",
                        tool_id=call.id or "",
                        tool_name=fn.name if fn else "",
                        tool_arguments=fn.arguments if fn and fn.arguments else "",
                    )
        finally:
            close = getattr(stream, "close", None) or getattr(stream, "aclose", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    async def complete(self, messages: list[Message]) -> str:
        response = await self._client.chat.completions.create(
            model=self._settings.deepseek_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            stream=False,
            temperature=0.5,
            extra_body={"thinking": {"type": "disabled"}},
        )
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None) if choice is not None else None
        content = getattr(message, "content", None) if message is not None else None
        return content or ""

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> CompletionMessage:
        payload: dict[str, Any] = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "extra_body": {"thinking": {"type": "enabled" if thinking else "disabled"}},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        response = await self._client.chat.completions.create(**payload)
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None) if choice is not None else None
        if message is None:
            return CompletionMessage()
        calls: list[ToolCallDelta] = []
        for index, call in enumerate(getattr(message, "tool_calls", None) or ()):
            fn = getattr(call, "function", None)
            calls.append(
                ToolCallDelta(
                    id=getattr(call, "id", None) or f"call_{index}",
                    name=getattr(fn, "name", None) or "",
                    arguments=getattr(fn, "arguments", None) or "{}",
                )
            )
        return CompletionMessage(
            content=getattr(message, "content", None) or "",
            tool_calls=tuple(calls),
        )


@dataclass
class ScriptedStreamer:
    events: list[TokenEvent] = field(default_factory=list)
    delay_s: float = 0.0
    clock: Any = None

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[TokenEvent]:
        del messages, tools
        for event in self.events:
            if cancel_event.is_set():
                return
            if self.delay_s and self.clock is not None:
                await self.clock.sleep(self.delay_s)
            if cancel_event.is_set():
                return
            yield event
