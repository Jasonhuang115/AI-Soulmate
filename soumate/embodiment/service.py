from __future__ import annotations

from asm.core.bus import EventBus
from asm.core.events import AvatarCommand, StartTurn, StateChanged, ToolCall
from asm.core.interfaces import ToolSpec

from .gestures import infer_motion
from .rules import apply_rule
from .state_pose import command_for
from .vocab import EMOTIONS, MOTIONS


class EmbodimentService:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(ToolCall, self.handle)
        bus.subscribe(StateChanged, self._on_state)
        bus.subscribe(StartTurn, self._on_start)

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="set_emotion",
                description="Set the companion's current emotion or attitude.",
                parameters={
                    "type": "object",
                    "properties": {
                        "emotion": {"type": "string", "enum": list(EMOTIONS)},
                        "motion": {"type": "string", "enum": list(MOTIONS)},
                        "intensity": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["emotion"],
                },
            )
        ]

    async def handle(self, call: ToolCall) -> None:
        if call.name != "set_emotion":
            return
        raw_emotion = call.arguments.get("emotion")
        raw_motion = call.arguments.get("motion")
        emotion = str(raw_emotion) if raw_emotion else None
        motion = str(raw_motion) if raw_motion else None
        if not emotion and not motion:
            return
        intensity = float(call.arguments.get("intensity", 1) or 1)
        applied = apply_rule(emotion, intensity, motion=motion)
        await self._bus.publish(
            AvatarCommand(
                turn_id=call.turn_id,
                sentence_idx=call.sentence_idx,
                expression=applied.expression,
                motion=applied.motion,
            )
        )

    async def _on_state(self, event: StateChanged) -> None:
        command = command_for(event)
        if command is not None:
            await self._bus.publish(command)

    async def _on_start(self, event: StartTurn) -> None:
        if event.speculative:
            return
        motion = infer_motion(event.text)
        if not motion:
            return
        await self._bus.publish(
            AvatarCommand(
                turn_id=event.turn_id,
                sentence_idx=None,
                expression=None,
                motion=motion,
                immediate=True,
            )
        )
