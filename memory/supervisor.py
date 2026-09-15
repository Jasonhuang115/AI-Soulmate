from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

from asm.brain.prompt import default_prompts_dir

from .tools import TYPE_FILES, MemoryTools, normalize_rel
from .turns import TurnStore

PROMPTS_DIR = Path(__file__).parent / "prompts"

CONSOLIDATE = "consolidate"

KIND_TOOLS: dict[str, tuple[str, ...]] = {
    CONSOLIDATE: ("search_turns", "ls", "read", "grep", "write", "write_section"),
}

KIND_STEPS = {CONSOLIDATE: 20}
KIND_THINKING = {CONSOLIDATE: True}


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
        "Replace a writable memory file. MEMORY.md only after a type file this run; max 200 lines / 25KB.",
        {"rel": {"type": "string"}, "content": {"type": "string"}},
    ),
    "write_section": _fn(
        "write_section",
        "Replace one markdown ## section in a writable memory file.",
        {
            "rel": {"type": "string"},
            "heading": {"type": "string"},
            "body": {"type": "string"},
        },
    ),
    "search_turns": _fn(
        "search_turns",
        "Search conversation turns in SQLite. Time, keyword, and speaker filters. Read-only.",
        {
            "pattern": {
                "type": "string",
                "description": "Optional substring, case-insensitive. Empty means time-only.",
            },
            "since": {
                "type": "string",
                "description": "Inclusive ISO start, e.g. 2026-09-15T17:46:00",
            },
            "until": {
                "type": "string",
                "description": "Exclusive ISO end",
            },
            "day": {
                "type": "string",
                "description": "YYYY-MM-DD; intersects since/until if both set",
            },
            "field": {
                "type": "string",
                "description": "user | assistant | both (default both). Only affects pattern.",
            },
            "n": {
                "type": "integer",
                "description": "Max rows, default 20, cap 500",
            },
            "order": {
                "type": "string",
                "description": "asc | desc (default desc). Use asc when scanning since last_run.",
            },
        },
        required=[],
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

    def __init__(
        self,
        tools: MemoryTools,
        llm: MemoryLLM | None,
        turns: TurnStore | None = None,
    ) -> None:
        self.tools = tools
        self.llm = llm
        self.turns = turns
        self._lock = asyncio.Lock()
        self._typed_written: set[str] = set()

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
        self._typed_written = set()
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
                temperature=0.4,
            )
            content = (getattr(turn, "content", None) or "").strip()
            calls = tuple(getattr(turn, "tool_calls", None) or ())
            names = [getattr(call, "name", "") or "" for call in calls]
            logger.info("memory %s tools=%s preview=%r", kind, names, content[:120])
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
                blocked = self._memory_blocked(rel)
                if blocked:
                    return blocked
                self.tools.write(rel, str(args.get("content", "")))
                self._note_typed(rel)
                return "ok"
            if name == "write_section":
                rel = normalize_rel(str(args.get("rel", "")))
                blocked = self._memory_blocked(rel)
                if blocked:
                    return blocked
                self.tools.write_section(
                    rel,
                    str(args["heading"]),
                    str(args["body"]),
                )
                self._note_typed(rel)
                return "ok"
            if name == "search_turns":
                if self.turns is None:
                    return _dump({"error": "no turn store"})
                n = args.get("n")
                return _dump(
                    self.turns.search(
                        pattern=str(args["pattern"]) if args.get("pattern") else None,
                        since=str(args["since"]) if args.get("since") else None,
                        until=str(args["until"]) if args.get("until") else None,
                        day=str(args["day"]) if args.get("day") else None,
                        field=str(args.get("field") or "both"),
                        n=int(n) if n is not None and str(n) != "" else None,
                        order=str(args.get("order") or "desc"),
                    )
                )
        except (KeyError, PermissionError, ValueError) as exc:
            return _dump({"error": f"{type(exc).__name__}: {exc}"})
        return _dump({"error": f"unknown tool {name}"})

    def _memory_blocked(self, rel: str) -> str:
        if rel == "MEMORY.md" and not self._typed_written:
            return _dump(
                {"error": "write MEMORY.md only after a type file this run"}
            )
        return ""

    def _note_typed(self, rel: str) -> None:
        if rel in TYPE_FILES:
            self._typed_written.add(rel)


def load_prompt(kind: str) -> str:
    soul = (default_prompts_dir() / "01-soul.md").read_text(encoding="utf-8").strip()
    shared = (PROMPTS_DIR / "supervisor.md").read_text(encoding="utf-8").strip()
    body = (PROMPTS_DIR / f"{kind}.md").read_text(encoding="utf-8").strip()
    return (
        "只读人设（Soul，不是记忆，你不能改）：\n"
        f"{soul}\n\n"
        f"{shared}\n\n{body}"
    )


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
