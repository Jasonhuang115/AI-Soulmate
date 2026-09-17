from __future__ import annotations

from asm.core.bus import EventBus
from asm.core.events import AvatarCommand, StateChanged, ToolCall
from asm.core.interfaces import ToolSpec

from .catalog import motion_face
from .resolve import classify, log_unresolved
from .rules import apply_rule
from .state_pose import command_for
from .vocab import MOTIONS


class EmbodimentService:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(ToolCall, self.handle)
        bus.subscribe(StateChanged, self._on_state)

    def tools(self) -> list[ToolSpec]:
        return []

    async def handle(self, call: ToolCall) -> None:
        if call.name != "set_emotion":
            return
        emotion = _as_str(call.arguments.get("emotion"))
        control = _resolve_control(call.arguments.get("control"))
        motions = _resolve_motions(call.arguments)
        if not emotion and not motions and not control:
            return
        applied = apply_rule(emotion, motion=motions[0] if motions else None)
        if motions:
            chosen = motions
        elif applied.motion:
            chosen = (applied.motion,)
        else:
            chosen = ()
        expression = applied.expression
        if expression is None and chosen:
            expression = motion_face(chosen[0])
        await self._bus.publish(
            AvatarCommand(
                turn_id=call.turn_id,
                sentence_idx=call.sentence_idx,
                expression=expression,
                motions=chosen,
                control=control,
                immediate=bool(call.arguments.get("immediate")),
            )
        )

    async def _on_state(self, event: StateChanged) -> None:
        command = command_for(event)
        if command is not None:
            await self._bus.publish(command)


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_control(value: object) -> str | None:
    raw = _as_str(value)
    if not raw:
        return None
    hit = classify(raw)
    if hit and hit[0] == "control":
        return hit[1]
    log_unresolved(raw)
    return None


def _resolve_motions(arguments: dict) -> tuple[str, ...]:
    raw = arguments.get("motions")
    names: list[str] = []
    if isinstance(raw, (list, tuple)):
        names.extend(str(item) for item in raw)
    single = _as_str(arguments.get("motion"))
    if single:
        names.append(single)
    out: list[str] = []
    for name in names:
        hit = classify(name)
        if hit and hit[0] == "motion" and hit[1] in MOTIONS:
            if hit[1] not in out:
                out.append(hit[1])
            continue
        if name:
            log_unresolved(name)
    return tuple(out[:3])
