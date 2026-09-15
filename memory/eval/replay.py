from __future__ import annotations

import argparse
import asyncio
import time

from memory.types import RecallContext
from memory.agent import MemoryAgent
from memory.paths import default_memdir


async def replay(judge: bool = False) -> None:
    del judge
    agent = MemoryAgent(default_memdir())
    for item in agent.store.all_turns():
        text = item.get("user") or ""
        t0 = time.monotonic()
        bundle = await agent.recall(RecallContext(text, (), ""), 2500)
        dt = (time.monotonic() - t0) * 1000
        tokens = len(bundle.index)
        print(f"{item.get('ts')}\t{dt:.0f}ms\t{tokens}\t{bundle.index[:80]!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcripts", default="", help="ignored; turns come from SQLite")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    del args
    asyncio.run(replay())


if __name__ == "__main__":
    main()
