from __future__ import annotations

import asyncio

from asm.brain.compact import drop_prefix_count, fill_limit, heuristic_summary
from asm.brain.prompt import assemble_framework, resolve_prompts_dir
from asm.core.bus import EventBus
from asm.core.config import Settings
from asm.core.events import (
    AudioChunk,
    Cancel,
    ClientDisconnected,
    Commit,
    CompressionNeeded,
    ContextReady,
    DialogState,
    Duck,
    LatencyMark,
    MicState,
    PartialTranscript,
    PlaybackDone,
    ProactiveTrigger,
    RecallRequested,
    SentenceEnd,
    SpeechEnded,
    SpeechStarted,
    SpokenProgress,
    StartTurn,
    StateChanged,
    SummaryReady,
    TextDelta,
    TextInput,
    TurnAborted,
    TurnClosed,
    TurnDone,
    Unduck,
    UtteranceEnd,
    VoiceError,
)
from asm.core.interfaces import (
    Brain,
    Clock,
    Message,
    TimerHandle,
    TurnRequest,
)
from asm.core.session import Session

_FILLERS = frozenset("嗯啊额哦唔。，,!?！？… \t\n　")


def meaningful_len(text: str) -> int:
    return sum(1 for ch in text if ch not in _FILLERS)


class Orchestrator:
    """Dialog state machine. No prompt, TTS, or archive policy lives here.

    Speculation / barge-in timers are owned here. Perception only emits
    raw VAD/ASR events. Thresholds come from Settings.

    While she is speaking, leftover ASR text is discarded. Echo after a
    false barge-in is ignored for barge_in_holdoff_ms. SpeechEnded during
    the duck window is kept so a real interrupt can still start a turn.
    """

    def __init__(
        self,
        bus: EventBus,
        session: Session,
        clock: Clock,
        brain: Brain,
        settings: Settings | None = None,
    ) -> None:
        self.bus = bus
        self.session = session
        self.clock = clock
        self.brain = brain
        self.settings = settings or Settings()
        self._assistant_buf: dict[str, list[str]] = {}
        self._marks: dict[str, dict[str, float]] = {}
        self._partial = ""
        self._speculative = False
        self._suppress_abort_idle = False
        self._mic_open = False
        self._speculate_timer: TimerHandle | None = None
        self._commit_timer: TimerHandle | None = None
        self._barge_timer: TimerHandle | None = None
        self._hang_timer: TimerHandle | None = None
        self._ducking = False
        self._speech_ended_while_ducking = False
        self._barge_holdoff_until = 0.0
        self._proactive = False
        self._compacting = False
        self._framework: str | None = None
        self._expect_audio = False
        self._llm_done = False
        self._playback_done = False
        self._audio_s = 0.0
        self._first_audio_at: float | None = None
        self._done_raw = ""
        self._playback_timer: TimerHandle | None = None

        bus.subscribe(TextInput, self._on_text)
        bus.subscribe(TextDelta, self._on_text_delta)
        bus.subscribe(SentenceEnd, self._on_sentence)
        bus.subscribe(SpokenProgress, self._on_spoken)
        bus.subscribe(AudioChunk, self._on_audio)
        bus.subscribe(VoiceError, self._on_voice_error)
        bus.subscribe(TurnDone, self._on_turn_done)
        bus.subscribe(TurnAborted, self._on_turn_aborted)
        bus.subscribe(SpeechStarted, self._on_speech_started)
        bus.subscribe(SpeechEnded, self._on_speech_ended)
        bus.subscribe(PartialTranscript, self._on_partial)
        bus.subscribe(UtteranceEnd, self._on_utterance)
        bus.subscribe(MicState, self._on_mic)
        bus.subscribe(ProactiveTrigger, self._on_proactive)
        bus.subscribe(ContextReady, self._on_context)
        bus.subscribe(SummaryReady, self._on_summary)
        bus.subscribe(PlaybackDone, self._on_playback_done)
        bus.subscribe(ClientDisconnected, self._on_client_disconnected)

    async def _set_state(self, state: DialogState) -> None:
        if self.session.state == state:
            return
        self.session.state = state
        await self.bus.publish(StateChanged(state))

    def _clear_timer(self, handle: TimerHandle | None) -> None:
        if handle is not None:
            handle.cancel()

    def _clear_endpoint_timers(self) -> None:
        self._clear_timer(self._speculate_timer)
        self._clear_timer(self._commit_timer)
        self._speculate_timer = None
        self._commit_timer = None

    def _clear_barge_timer(self) -> None:
        self._clear_timer(self._barge_timer)
        self._barge_timer = None

    def _clear_hang_timer(self) -> None:
        self._clear_timer(self._hang_timer)
        self._hang_timer = None

    def _clear_playback_timer(self) -> None:
        self._clear_timer(self._playback_timer)
        self._playback_timer = None

    def _reset_playback(self) -> None:
        self._expect_audio = False
        self._llm_done = False
        self._playback_done = False
        self._audio_s = 0.0
        self._first_audio_at = None
        self._done_raw = ""
        self._clear_playback_timer()

    def _kick_playback_watchdog(self) -> None:
        self._clear_playback_timer()
        slack = self.settings.playback_watchdog_slack_ms / 1000
        if self._first_audio_at is None:
            delay = slack
        else:
            remain = self._audio_s - (self.clock.now() - self._first_audio_at)
            delay = max(remain, 0.0) + slack
        self._playback_timer = self.clock.call_later(delay, self._on_playback_watchdog)

    def _kick_hang_timer(self) -> None:
        self._clear_hang_timer()
        self._hang_timer = self.clock.call_later(
            self.settings.partial_hang_ms / 1000,
            self._on_partial_hang,
        )

    async def _cancel_current(self, *, record_interrupt: bool = True) -> str | None:
        turn_id = self.session.current_turn_id
        if turn_id is None or self.session.state == DialogState.IDLE:
            return None
        if self.session.state == DialogState.LISTENING and not self._speculative:
            return None
        await self.bus.publish(Cancel(turn_id))
        self._suppress_abort_idle = True
        try:
            await self.brain.cancel(turn_id)
        finally:
            self._suppress_abort_idle = False
        self._ducking = False
        if record_interrupt:
            self.session.mark_interrupted(turn_id)
            self._observe_bg(turn_id, True)
        self._speculative = False
        self._proactive = False
        self._reset_playback()
        return turn_id

    async def _start_brain_turn(self, text: str, *, speculative: bool) -> None:
        turn_id = self.session.begin_turn()
        if speculative and self.session.messages and self.session.messages[-1].role == "user":
            self.session.messages[-1] = Message(role="user", content=text)
            self.session.last_user_text = text
        else:
            self.session.append_user(text)
        self._hard_trim_if_needed()
        self._assistant_buf[turn_id] = []
        self._marks[turn_id] = {"t_start_turn": self.clock.now()}
        self._speculative = speculative
        self._reset_playback()
        bundle = self.session.last_context
        await self.bus.publish(
            StartTurn(turn_id=turn_id, text=text, speculative=speculative, context=bundle)
        )
        if not speculative:
            await self.bus.publish(Commit(turn_id=turn_id))
            marks = self._marks[turn_id]
            marks["t_commit"] = self.clock.now()
        await self.brain.start_turn(
            TurnRequest(
                turn_id=turn_id,
                text=text,
                speculative=speculative,
                context=bundle,
                messages=tuple(self.session.messages),
                session_summary=self.session.session_summary,
            )
        )

    def _schedule_recall(self, text: str) -> None:
        asyncio.create_task(self._recall_bg(text))

    async def _recall_bg(self, text: str) -> None:
        await self.bus.publish(
            RecallRequested(
                text=text,
                recent=tuple(self.session.messages[-8:]),
                deadline_ms=self.settings.recall_deadline_ms,
            )
        )

    def _observe_bg(self, turn_id: str, interrupted: bool) -> None:
        user = self.session.last_user_text
        pending = self.session.pending_sentences.get(turn_id, [])
        spoken_idx = self.session.spoken_upto.get(turn_id, -1)
        spoken = [s for s in pending[: spoken_idx + 1] if s] if spoken_idx >= 0 else [s for s in pending if s]
        asyncio.create_task(
            self.bus.publish(
                TurnClosed(
                    turn_id=turn_id,
                    user_text=user,
                    assistant_text="".join(spoken) or "".join(self._assistant_buf.get(turn_id, [])),
                    interrupted=interrupted,
                )
            )
        )

    async def _on_text(self, event: TextInput) -> None:
        text = event.text.strip()
        if not text:
            return
        self._clear_endpoint_timers()
        self._clear_barge_timer()
        self._clear_hang_timer()
        if self.session.state != DialogState.IDLE:
            await self._cancel_current(record_interrupt=True)
        self._proactive = False
        self._partial = ""
        self._schedule_recall(text)
        self._marks_submit = self.clock.now()
        await self._set_state(DialogState.THINKING)
        await self._start_brain_turn(text, speculative=False)
        self._marks.setdefault(self.session.current_turn_id or "", {})["t_submit"] = self._marks_submit

    async def _on_text_delta(self, event: TextDelta) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        if self.session.state == DialogState.IDLE:
            return
        self._assistant_buf.setdefault(event.turn_id, []).append(event.text)

    async def _on_sentence(self, event: SentenceEnd) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        if self.session.state == DialogState.IDLE:
            return
        self.session.record_sentence(event.turn_id, event.sentence_idx, event.text)
        self._expect_audio = True
        marks = self._marks.setdefault(event.turn_id, {})
        marks.setdefault("t_first_sentence", self.clock.now())

    async def _on_spoken(self, event: SpokenProgress) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        self.session.append_assistant_spoken(event.turn_id, event.sentence_idx)

    async def _finalize_turn(
        self, turn_id: str, *, interrupted: bool, raw_text: str = ""
    ) -> None:
        pending = self.session.pending_sentences.get(turn_id, [])
        if not interrupted:
            history = raw_text.strip() or "".join(self._assistant_buf.get(turn_id, []))
            if history:
                self.session.messages.append(Message(role="assistant", content=history))
            elif any(pending):
                self.session.finalize_assistant(turn_id)
        marks = self._marks.get(turn_id)
        if marks:
            await self.bus.publish(LatencyMark(turn_id=turn_id, marks=dict(marks)))
        self._observe_bg(turn_id, interrupted)
        self._speculative = False
        self._reset_playback()
        await self._set_state(DialogState.IDLE)
        self._schedule_compact()

    async def _on_turn_done(self, event: TurnDone) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        self._llm_done = True
        self._done_raw = event.raw_text
        if self._playback_done or not self._expect_audio:
            await self._finalize_turn(
                event.turn_id, interrupted=False, raw_text=event.raw_text
            )
            return
        self._kick_playback_watchdog()

    async def _on_playback_done(self, event: PlaybackDone) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        if self.session.state not in (
            DialogState.SPEAKING,
            DialogState.THINKING,
            DialogState.SPECULATING,
        ):
            return
        self._playback_done = True
        if self._llm_done:
            await self._finalize_turn(
                event.turn_id, interrupted=False, raw_text=self._done_raw
            )

    async def _on_playback_watchdog(self) -> None:
        self._playback_timer = None
        turn_id = self.session.current_turn_id
        if turn_id is None or self.session.state == DialogState.IDLE:
            return
        if not self._llm_done:
            self._kick_playback_watchdog()
            return
        self._playback_done = True
        await self._finalize_turn(turn_id, interrupted=False, raw_text=self._done_raw)

    async def _on_client_disconnected(self, event: ClientDisconnected) -> None:
        del event
        if self.session.state == DialogState.IDLE:
            return
        turn_id = self.session.current_turn_id
        if turn_id is not None and self._llm_done:
            await self._finalize_turn(turn_id, interrupted=False, raw_text=self._done_raw)
            return
        await self._cancel_current(record_interrupt=True)
        await self._set_state(DialogState.IDLE)

    async def _on_audio(self, event: AudioChunk) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        if self.session.state == DialogState.IDLE:
            return
        self._expect_audio = True
        self._playback_done = False
        rate = event.sample_rate or 1
        self._audio_s += (len(event.pcm16) / 2) / rate
        if self._first_audio_at is None:
            self._first_audio_at = self.clock.now()
        if self._llm_done:
            self._kick_playback_watchdog()
        marks = self._marks.setdefault(event.turn_id, {})
        marks.setdefault("t_first_audio", self.clock.now())
        if self.session.state in (DialogState.THINKING, DialogState.SPECULATING) and not self._speculative:
            await self._enter_speaking()
        elif self.session.state == DialogState.SPECULATING and self._marks.get(event.turn_id, {}).get("t_commit"):
            await self._enter_speaking()

    async def _enter_speaking(self) -> None:
        self._partial = ""
        self._speech_ended_while_ducking = False
        await self._set_state(DialogState.SPEAKING)

    async def _arm_endpoint_timers(self, *, force: bool = False) -> None:
        if self.session.state in (
            DialogState.SPECULATING,
            DialogState.THINKING,
            DialogState.SPEAKING,
        ):
            return
        await self._set_state(DialogState.LISTENING)
        self._clear_endpoint_timers()
        spec_s, commit_s = self._endpoint_delays(force=force)
        self._speculate_timer = self.clock.call_later(spec_s, self._on_speculate_due)
        self._commit_timer = self.clock.call_later(commit_s, self._on_commit_due)

    def _endpoint_delays(self, *, force: bool = False) -> tuple[float, float]:
        spec = self.settings.speculate_after_ms / 1000
        commit = self.settings.commit_after_ms / 1000
        extra = (self.settings.commit_after_ms - self.settings.speculate_after_ms) / 1000
        if not force and meaningful_len(self._partial) < 2:
            spec = self.settings.partial_hang_ms / 1000
            commit = spec + max(extra, 0.0)
        return spec, commit

    async def _confirm_barge_in(self) -> None:
        self._clear_barge_timer()
        await self._cancel_current(record_interrupt=True)
        self._ducking = False
        ended = self._speech_ended_while_ducking
        self._speech_ended_while_ducking = False
        await self._set_state(DialogState.LISTENING)
        if not ended:
            if self._partial.strip():
                self._kick_hang_timer()
            await self._arm_endpoint_timers()
            return
        if self._partial.strip():
            await self._on_speculate_due()
            if self.session.state == DialogState.SPECULATING:
                remain = (self.settings.commit_after_ms - self.settings.speculate_after_ms) / 1000
                self._commit_timer = self.clock.call_later(max(remain, 0.0), self._on_commit_due)
            return
        await self._arm_endpoint_timers()

    async def _unduck_continue(self) -> None:
        self._clear_barge_timer()
        if not self._ducking:
            return
        await self.bus.publish(Unduck())
        self._ducking = False
        self._speech_ended_while_ducking = False
        self._barge_holdoff_until = self.clock.now() + self.settings.barge_in_holdoff_ms / 1000

    async def _on_voice_error(self, event: VoiceError) -> None:
        del event

    async def _on_turn_aborted(self, event: TurnAborted) -> None:
        if event.turn_id != self.session.current_turn_id:
            return
        if not self._suppress_abort_idle:
            self._observe_bg(event.turn_id, True)
            self._reset_playback()
            await self._set_state(DialogState.IDLE)
            self._schedule_compact()

    async def _on_speech_started(self, event: SpeechStarted) -> None:
        del event
        self._clear_endpoint_timers()
        state = self.session.state
        if state == DialogState.LISTENING:
            if self._partial.strip():
                self._kick_hang_timer()
            return
        if state == DialogState.IDLE:
            await self._set_state(DialogState.LISTENING)
            return
        if state == DialogState.THINKING:
            await self._cancel_current(record_interrupt=True)
            await self._set_state(DialogState.LISTENING)
            return
        if state == DialogState.SPECULATING:
            await self._cancel_current(record_interrupt=False)
            await self._set_state(DialogState.LISTENING)
            return
        if state == DialogState.SPEAKING:
            if self._ducking:
                return
            if self.clock.now() < self._barge_holdoff_until:
                return
            self._partial = ""
            self._speech_ended_while_ducking = False
            await self.bus.publish(Duck())
            self._ducking = True
            self._clear_barge_timer()
            self._barge_timer = self.clock.call_later(
                self.settings.barge_in_confirm_ms / 1000,
                self._barge_timeout,
            )
            return

    async def _on_speech_ended(self, event: SpeechEnded) -> None:
        del event
        if self.session.state == DialogState.SPEAKING and self._ducking:
            self._speech_ended_while_ducking = True
            if meaningful_len(self._partial) >= self.settings.barge_in_min_chars:
                await self._confirm_barge_in()
            return
        if self.session.state not in (DialogState.LISTENING, DialogState.IDLE):
            return
        await self._arm_endpoint_timers()

    async def _on_partial(self, event: PartialTranscript) -> None:
        if self.session.state == DialogState.SPEAKING and not self._ducking:
            return
        self._partial = event.text
        marks = self._marks.setdefault(self.session.current_turn_id or "_listen", {})
        marks.setdefault("t_first_partial", self.clock.now())
        self._schedule_recall(event.text)
        if self.session.state == DialogState.IDLE:
            await self._set_state(DialogState.LISTENING)
        if self.session.state in (DialogState.LISTENING, DialogState.IDLE):
            self._kick_hang_timer()
            if self._speculate_timer is not None or self._commit_timer is not None:
                await self._arm_endpoint_timers()
        if self.session.state == DialogState.SPEAKING and self._ducking:
            if meaningful_len(event.text) >= self.settings.barge_in_min_chars:
                await self._confirm_barge_in()

    async def _on_utterance(self, event: UtteranceEnd) -> None:
        if self.session.state == DialogState.SPEAKING and not self._ducking:
            return
        self._partial = event.text or self._partial
        if self.session.current_turn_id:
            self._marks.setdefault(self.session.current_turn_id, {})["t_utterance_end"] = self.clock.now()
        if self.session.state == DialogState.SPEAKING and self._ducking:
            if meaningful_len(self._partial) >= self.settings.barge_in_min_chars:
                await self._confirm_barge_in()
            elif self._speech_ended_while_ducking:
                await self._unduck_continue()
            return
        if self.session.state == DialogState.IDLE:
            await self._set_state(DialogState.LISTENING)
        if (
            self.session.state in (DialogState.LISTENING, DialogState.IDLE)
            and self._speculate_timer is None
            and self._commit_timer is None
            and self._partial.strip()
        ):
            await self._arm_endpoint_timers()
        elif self.session.state == DialogState.LISTENING:
            self._kick_hang_timer()

    async def _on_mic(self, event: MicState) -> None:
        self._mic_open = event.open
        if event.open:
            return
        if self.session.state == DialogState.LISTENING and self._partial.strip():
            if self._speculate_timer is None and self._commit_timer is None:
                await self._arm_endpoint_timers(force=True)

    async def _on_partial_hang(self) -> None:
        self._hang_timer = None
        if self.session.state != DialogState.LISTENING:
            return
        if not self._partial.strip():
            return
        if self._speculate_timer is not None:
            return
        await self._on_speculate_due()
        if self.session.state == DialogState.SPECULATING:
            remain = (self.settings.commit_after_ms - self.settings.speculate_after_ms) / 1000
            self._commit_timer = self.clock.call_later(max(remain, 0.0), self._on_commit_due)

    async def _on_speculate_due(self) -> None:
        self._speculate_timer = None
        if self.session.state != DialogState.LISTENING:
            return
        text = self._partial.strip()
        if not text:
            return
        await self._set_state(DialogState.SPECULATING)
        self._clear_hang_timer()
        await self._start_brain_turn(text, speculative=True)

    async def _on_commit_due(self) -> None:
        self._commit_timer = None
        turn_id = self.session.current_turn_id
        if turn_id is None or self.session.state != DialogState.SPECULATING:
            return
        await self.bus.publish(Commit(turn_id=turn_id))
        self._marks.setdefault(turn_id, {})["t_commit"] = self.clock.now()
        self._speculative = False
        if "t_first_audio" in self._marks.get(turn_id, {}):
            await self._enter_speaking()
        else:
            await self._set_state(DialogState.THINKING)

    async def _barge_timeout(self) -> None:
        self._barge_timer = None
        if not self._ducking or self.session.state != DialogState.SPEAKING:
            return
        if self._speech_ended_while_ducking:
            if meaningful_len(self._partial) >= self.settings.barge_in_min_chars:
                await self._confirm_barge_in()
            else:
                await self._unduck_continue()
            return
        await self._confirm_barge_in()

    async def _on_proactive(self, event: ProactiveTrigger) -> None:
        if self.session.state != DialogState.IDLE:
            return
        self._proactive = True
        text = f"[系统：你想主动说点什么，原因：{event.reason}。提示：{event.hint}]"
        await self._set_state(DialogState.THINKING)
        await self._start_brain_turn(text, speculative=False)

    async def _on_context(self, event: ContextReady) -> None:
        self.session.last_context = event.context

    async def _on_summary(self, event: SummaryReady) -> None:
        self.session.session_summary = event.text
        self._compacting = False

    def _framework_text(self) -> str:
        if self._framework is None:
            self._framework = assemble_framework(resolve_prompts_dir(self.settings.prompts_dir))
        return self._framework

    def _fill_limit(self) -> int:
        return fill_limit(self.settings.context_window_tokens, self.settings.context_reserve_ratio)

    def _needed_drop(self) -> int:
        return drop_prefix_count(
            framework=self._framework_text(),
            context=self.session.last_context,
            summary=self.session.session_summary,
            messages=self.session.messages,
            limit=self._fill_limit(),
        )

    def _hard_trim_if_needed(self) -> None:
        drop = self._needed_drop()
        if drop <= 0:
            return
        discarded = tuple(self.session.messages[:drop])
        self.session.drop_matching_prefix(drop, discarded)
        if not self.session.session_summary.strip():
            self.session.session_summary = heuristic_summary("", discarded)
        self._kick_compact(discarded)

    def _schedule_compact(self) -> None:
        if self._compacting:
            return
        drop = self._needed_drop()
        if drop <= 0:
            return
        discarded = tuple(self.session.messages[:drop])
        self.session.drop_matching_prefix(drop, discarded)
        self._kick_compact(discarded)

    def _kick_compact(self, discarded: tuple[Message, ...]) -> None:
        if self._compacting or not discarded:
            return
        self._compacting = True
        asyncio.create_task(
            self.bus.publish(
                CompressionNeeded(
                    discarded=discarded,
                    previous_summary=self.session.session_summary,
                    drop_prefix=len(discarded),
                )
            )
        )
