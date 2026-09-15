from asm.core.clock import FakeClock


async def test_fake_clock_advance_wakes_sleep() -> None:
    clock = FakeClock()
    woke = False

    async def waiter() -> None:
        nonlocal woke
        await clock.sleep(0.3)
        woke = True

    import asyncio

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    assert woke is False
    await clock.advance(0.29)
    assert woke is False
    await clock.advance(0.02)
    await task
    assert woke is True
    assert clock.now() == 0.31


async def test_fake_clock_call_later() -> None:
    clock = FakeClock()
    hits: list[int] = []

    clock.call_later(0.2, lambda: hits.append(1))
    await clock.advance(0.19)
    assert hits == []
    await clock.advance(0.02)
    assert hits == [1]
