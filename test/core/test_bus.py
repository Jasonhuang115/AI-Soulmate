from asm.core.bus import EventBus
from asm.core.events import Cancel, TextInput


async def test_bus_delivers_to_type_subscribers() -> None:
    bus = EventBus()
    seen_text: list[str] = []
    seen_cancel: list[str] = []

    async def on_text(event: TextInput) -> None:
        seen_text.append(event.text)

    async def on_text_two(event: TextInput) -> None:
        seen_text.append(f"2:{event.text}")

    async def on_cancel(event: Cancel) -> None:
        seen_cancel.append(event.turn_id)

    bus.subscribe(TextInput, on_text)
    bus.subscribe(TextInput, on_text_two)
    bus.subscribe(Cancel, on_cancel)

    await bus.publish(TextInput(text="你好"))

    assert seen_text == ["你好", "2:你好"]
    assert seen_cancel == []


async def test_bus_isolates_handler_errors() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def boom(_event: TextInput) -> None:
        raise RuntimeError("nope")

    async def ok(event: TextInput) -> None:
        seen.append(event.text)

    bus.subscribe(TextInput, boom)
    bus.subscribe(TextInput, ok)

    await bus.publish(TextInput(text="还在"))

    assert seen == ["还在"]
