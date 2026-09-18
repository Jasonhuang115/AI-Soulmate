from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from asm.brain.deepseek_client import DeepSeekClient
from asm.brain.mock import MockBrain
from asm.brain.prompt import load_prompt_fragments, resolve_prompts_dir
from asm.brain.runtime import BrainRuntime
from asm.core.bus import EventBus
from asm.core.clock import SystemClock
from asm.core.config import Settings
from asm.core.latency_log import LatencyLogger
from asm.core.orchestrator import Orchestrator
from asm.core.session import Session
from asm.gateway.ws_server import handle_socket
from asm.emotion.now import NowStore
from asm.impulse.scheduler import ImpulseScheduler
from embodiment.service import EmbodimentService
from memory_agent.agent import MemoryAgent
from asm.perception.service import SpeechPerceiver
from asm.voice.mock import MockTTS
from asm.voice.service import VoiceService
from asm.voice.volcengine_tts import VolcengineTTS

logger = logging.getLogger(__name__)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    load_prompt_fragments(resolve_prompts_dir(settings.prompts_dir))
    bus = EventBus()
    clock = SystemClock()
    session = Session()
    brain_client = DeepSeekClient(settings) if settings.deepseek_api_key else None
    memory_llm = DeepSeekClient(settings) if settings.deepseek_api_key else None
    memory = MemoryAgent(
        root=repo_root() / settings.memory_dir,
        bus=bus,
        client=memory_llm,
        completer=memory_llm,
    )
    embodiment = EmbodimentService(bus)
    now_store = NowStore(repo_root() / settings.memory_dir / "self_state.md")
    if brain_client is not None:
        brain = BrainRuntime(
            bus,
            clock,
            brain_client,
            settings,
            now_store=now_store,
            last_chat_fn=memory.last_seen,
        )
    else:
        brain = MockBrain(bus, clock)
    if settings.volc_tts_ready():
        engine = VolcengineTTS(settings)
    else:
        engine = MockTTS()
    VoiceService(bus, engine)
    LatencyLogger(bus, repo_root() / "data" / "logs" / "latency.jsonl")
    Orchestrator(
        bus=bus,
        session=session,
        clock=clock,
        brain=brain,
        settings=settings,
        now_store=now_store,
    )
    perceiver = SpeechPerceiver.maybe(bus)
    listen = "sherpa" if perceiver.listening else "off"
    speak = "volc" if settings.volc_tts_ready() else "mock"
    brain_kind = "deepseek" if brain_client is not None else "mock"
    if listen == "off":
        logger.warning(
            "listen is off: pip install -e '.[asr]' && bash scripts/download_asr_models.sh"
        )
    if speak == "mock":
        logger.warning("speak is mock beeps: set VOLC_TTS_SPEAKER and a Volc TTS key in .env")
    impulse = (
        ImpulseScheduler(
            bus, clock, notes=memory, idle_s=settings.idle_companion_s, now_store=now_store
        )
        if settings.impulse_enabled
        else None
    )

    app = FastAPI(title="ASM")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.bus = bus
    app.state.settings = settings
    app.state.perceiver = perceiver
    app.state.memory = memory
    app.state.impulse = impulse

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"ok": "1", "brain": brain_kind, "speak": speak, "listen": listen}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await handle_socket(websocket, bus, perceiver)

    return app


app = create_app()
