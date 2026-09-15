from asm.core.bus import EventBus
from asm.core.events import AvatarCommand, DialogState, StartTurn, StateChanged, ToolCall
from asm.core.interfaces import PromptContext
from embodiment.service import EmbodimentService


async def test_set_emotion_publishes_avatar_command() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(ToolCall("t1", 0, "set_emotion", {"emotion": "agree"}))
    assert seen
    assert seen[-1].motion == "nod"
    assert seen[-1].turn_id == "t1"


async def test_explicit_motion_overrides_default() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(ToolCall("t1", 0, "set_emotion", {"emotion": "happy", "motion": "wave"}))
    assert seen[-1].expression == "happy"
    assert seen[-1].motion == "wave"


async def test_motion_only_does_not_reset_face() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(ToolCall("t1", 0, "set_emotion", {"motion": "wave"}))
    assert seen[-1].expression is None
    assert seen[-1].motion == "wave"


async def test_user_ask_wave_plays_immediately() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(
        StartTurn(turn_id="t1", text="挥挥手", speculative=False, context=PromptContext())
    )
    assert seen[-1].motion == "wave"
    assert seen[-1].immediate is True
    assert seen[-1].expression is None


async def test_speculative_turn_does_not_wave() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(
        StartTurn(turn_id="t1", text="挥挥手", speculative=True, context=PromptContext())
    )
    assert seen == []


async def test_state_pose_is_immediate() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(StateChanged(DialogState.LISTENING))
    assert seen[-1].immediate is True
    assert seen[-1].expression == "listening"


async def test_speaking_does_not_override_sentence_face() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(StateChanged(DialogState.SPEAKING))
    assert seen == []


async def test_idle_does_not_reset_sentence_face() -> None:
    bus = EventBus()
    seen: list[AvatarCommand] = []

    async def capture(event: AvatarCommand) -> None:
        seen.append(event)

    bus.subscribe(AvatarCommand, capture)
    EmbodimentService(bus)
    await bus.publish(StateChanged(DialogState.IDLE))
    assert seen == []

