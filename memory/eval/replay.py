from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from memory.types import RecallContext
from memory.agent import MemoryAgent
from memory.paths import default_memdir


async def replay(transcript_dir: Path, judge: bool = False) -> None:
    del judge
    agent = MemoryAgent(default_memdir())
    files = sorted(transcript_dir.glob("*.jsonl"))
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            text = item.get("user") or item.get("text") or ""
            t0 = time.monotonic()
            bundle = await agent.recall(RecallContext(text, (), ""), 400)
            dt = (time.monotonic() - t0) * 1000
            tokens = len(bundle.index) + len(bundle.relationship) + sum(len(s) for s in bundle.snippets)
            print(f"{path.name}\t{dt:.0f}ms\t{tokens}\t{bundle.snippets[:2]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcripts", default=str(default_memdir() / "transcripts"))
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    asyncio.run(replay(Path(args.transcripts), args.judge))


if __name__ == "__main__":
    main()
