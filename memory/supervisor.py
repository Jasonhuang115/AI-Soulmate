from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .tools import MemoryTools, normalize_rel

PROMPTS_DIR = Path(__file__).parent / "prompts"

KIND_TOOLS: dict[str, tuple[str, ...]] = {
    "extract": ("ls", "read", "grep", "append"),
    "recall": ("ls", "read", "grep", "write"),
    "dream": ("ls", "read", "grep", "write", "write_section"),
}

KIND_STEPS = {"extract": 6, "recall": 4, "dream": 20}
KIND_THINKING = {"extract": False, "recall": False, "dream": True}


def _fn(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required if required is not None else list(properties),
            },
        },
    }


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "ls": _fn(
        "ls",
        "List files under the memory directory.",
        {"rel": {"type": "string", "description": "Relative path, default ."}},
        required=[],
    ),
    "read": _fn("read", "Read a memory file.", {"rel": {"type": "string"}}),
    "grep": _fn(
        "grep",
        "Search memory files. Returns path:line:text hits, max 50.",
        {
            "pattern": {"type": "string"},
            "rel": {"type": "string", "description": "Relative path, default ."},
        },
        required=["pattern"],
    ),
    "write": _fn(
        "write",
        "Replace a writable memory file. MEMORY.md max 200 lines / 25KB.",
        {"rel": {"type": "string"}, "content": {"type": "string"}},
    ),
    "write_section": _fn(
        "write_section",
        "Replace one markdown ## section in a writable archive file.",
        {
            "rel": {"type": "string"},
            "heading": {"type": "string"},
            "body": {"type": "string"},
        },
    ),
    "append": _fn(
        "append",
        "Append a line to today's log. Only logs/*.md.",
        {"rel": {"type": "string"}, "text": {"type": "string"}},
    ),
}


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class CompletionMessage:
    content: str = ""
    tool_calls: tuple[ToolCallDelta, ...] = ()


class MemoryLLM(Protocol):
    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> CompletionMessage: ...


class MemorySupervisor:
    """Dedicated LLM that is the only writer of memory files."""

    def __init__(self, tools: MemoryTools, llm: MemoryLLM | None) -> None:
        self.tools = tools
        self.llm = llm
        self._lock = asyncio.Lock()

    async def run(
        self,
        kind: str,
        query: str,
        *,
        max_steps: int | None = None,
        thinking: bool | None = None,
    ) -> str:
        if self.llm is None:
            return ""
        async with self._lock:
            return await self._run_locked(kind, query, max_steps=max_steps, thinking=thinking)

    async def _run_locked(
        self,
        kind: str,
        query: str,
        *,
        max_steps: int | None,
        thinking: bool | None,
    ) -> str:
        if kind not in KIND_TOOLS:
            raise ValueError(f"unknown memory job {kind}")
        steps = max_steps if max_steps is not None else KIND_STEPS[kind]
        use_thinking = KIND_THINKING[kind] if thinking is None else thinking
        schemas = [TOOL_SPECS[name] for name in KIND_TOOLS[kind]]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": load_prompt(kind)},
            {"role": "user", "content": query},
        ]
        last = ""
        for _ in range(steps):
            turn = await self.llm.complete_with_tools(
                messages,
                schemas,
                thinking=use_thinking,
                temperature=0.4 if kind == "dream" else 0.3,
            )
            content = (getattr(turn, "content", None) or "").strip()
            calls = tuple(getattr(turn, "tool_calls", None) or ())
            if not calls:
                return content
            last = content
            serialized = []
            for index, call in enumerate(calls):
                name = getattr(call, "name", "") or ""
                arguments = getattr(call, "arguments", None) or "{}"
                call_id = getattr(call, "id", "") or f"call_{index}"
                serialized.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": serialized,
                }
            )
            for spec in serialized:
                result = self._exec(
                    kind,
                    spec["function"]["name"],
                    spec["function"]["arguments"],
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": spec["id"],
                        "content": result,
                    }
                )
        return last

    def _exec(self, kind: str, name: str, raw_args: str) -> str:
        allowed = KIND_TOOLS[kind]
        if name not in allowed:
            return _dump({"error": f"{name} not allowed during {kind}"})
        args = _parse_args(raw_args)
        try:
            if name == "ls":
                return _dump(self.tools.ls(str(args.get("rel", "."))))
            if name == "read":
                return self.tools.read(str(args.get("rel", "")))
            if name == "grep":
                return _dump(
                    self.tools.grep(str(args.get("pattern", ".")), str(args.get("rel", ".")))
                )
            if name == "write":
                rel = normalize_rel(str(args.get("rel", "")))
                if kind == "recall" and rel != "MEMORY.md":
                    return _dump({"error": "recall may only write MEMORY.md"})
                self.tools.write(rel, str(args.get("content", "")))
                return "ok"
            if name == "write_section":
                self.tools.write_section(
                    str(args["rel"]),
                    str(args["heading"]),
                    str(args["body"]),
                )
                return "ok"
            if name == "append":
                self.tools.append(str(args["rel"]), str(args["text"]))
                return "ok"
        except (KeyError, PermissionError, ValueError) as exc:
            return _dump({"error": f"{type(exc).__name__}: {exc}"})
        return _dump({"error": f"unknown tool {name}"})


def load_prompt(kind: str) -> str:
    shared = (PROMPTS_DIR / "supervisor.md").read_text(encoding="utf-8").strip()
    body = (PROMPTS_DIR / f"{kind}.md").read_text(encoding="utf-8").strip()
    return f"{shared}\n\n{body}"


def _parse_args(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _dump(result: object) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)
