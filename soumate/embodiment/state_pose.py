from __future__ import annotations

from asm.core.events import AvatarCommand, DialogState, StateChanged

STATE_POSES = {
    DialogState.LISTENING: AvatarCommand(
        None, None, "listening", (), None, None, True
    ),
    DialogState.THINKING: AvatarCommand(
        None, None, "thinking", (), None, None, True
    ),
    DialogState.SPECULATING: AvatarCommand(
        None, None, "thinking", (), None, None, True
    ),
}


def command_for(event: StateChanged) -> AvatarCommand | None:
    if event.state is DialogState.SPEAKING:
        return None
    return STATE_POSES.get(event.state)
