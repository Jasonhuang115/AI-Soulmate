#!/usr/bin/env python3
"""Print how deepseek-flash interleaves tool calls and text. Needs DEEPSEEK_API_KEY."""

from __future__ import annotations

import asyncio
import os

from openai import AsyncOpenAI


async def main() -> None:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY missing")
    client = AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com")
    stream = await client.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role": "user", "content": "高兴地用一句话打招呼，并调用 set_emotion。"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "set_emotion",
                    "description": "set emotion",
                    "parameters": {
                        "type": "object",
                        "properties": {"emotion": {"type": "string"}},
                        "required": ["emotion"],
                    },
                },
            }
        ],
        stream=True,
        extra_body={"thinking": {"type": "disabled"}},
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue
        print({"content": delta.content, "tool_calls": delta.tool_calls})


if __name__ == "__main__":
    asyncio.run(main())
