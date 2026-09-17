import { AudioPlayer, type AudioChunkMsg } from "./audio_player";
import { ChatPanel } from "./chat_panel";
import { VrmRenderer } from "./vrm_renderer";
import { MicCapture } from "./mic_capture";
import { WsClient } from "./ws_client";
import "./style.css";

function must<T>(el: T | null, name: string): T {
  if (!el) throw new Error(`missing DOM node: ${name}`);
  return el;
}

const log = must(document.querySelector<HTMLOListElement>("#log"), "log");
const status = must(document.querySelector<HTMLElement>("#status"), "status");
const caps = must(document.querySelector<HTMLElement>("#caps"), "caps");
const form = must(document.querySelector<HTMLFormElement>("#composer"), "composer");
const input = must(document.querySelector<HTMLInputElement>("#input"), "input");
const micBtn = must(document.querySelector<HTMLButtonElement>("#mic"), "mic");
const face = must(document.querySelector<HTMLCanvasElement>("#face"), "face");
const faceStatus = must(document.querySelector<HTMLElement>("#face-status"), "face-status");
const faceDebug = document.querySelector<HTMLElement>("#face-debug");

const panel = new ChatPanel(log, status);
const renderer = new VrmRenderer(face, faceStatus, faceDebug);
const client = new WsClient(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
const player = new AudioPlayer(
  (turnId, idx) => {
    client.send({ type: "spoken_progress", turn_id: turnId, sentence_idx: idx });
    renderer.onSentenceStart(turnId, idx);
  },
  (value) => renderer.setMouthOpen(value),
  (turnId) => client.send({ type: "playback_done", turn_id: turnId }),
);
const mic = new MicCapture((pcm) => client.sendBinary(pcm));

client.onMessage((msg) => {
  panel.onServer(msg);
  if (msg.type === "audio_chunk" && msg.turn_id && msg.pcm_b64 && msg.sample_rate != null) {
    playingTurnId = msg.turn_id;
    player.enqueue(msg as AudioChunkMsg);
  }
  if (msg.type === "commit" && msg.turn_id) {
    playingTurnId = msg.turn_id;
    player.commit(msg.turn_id);
  }
  if (msg.type === "cancel" && msg.turn_id) {
    player.cancel(msg.turn_id);
    renderer.cancel();
    if (playingTurnId === msg.turn_id) playingTurnId = "";
  }
  if (msg.type === "duck") player.duck();
  if (msg.type === "unduck") player.unduck();
  if (msg.type === "sentence" && msg.turn_id && msg.sentence_idx != null) {
    renderer.onSentenceStart(msg.turn_id, msg.sentence_idx);
  }
  if (msg.type === "avatar_command") {
    renderer.queue({
      turn_id: msg.turn_id,
      sentence_idx: msg.sentence_idx,
      expression: msg.expression,
      motion: msg.motion,
      motions: msg.motions,
      control: msg.control,
      intensity: msg.intensity,
      immediate: msg.immediate,
    });
  }
});
client.connect();

let listenReady = false;
let micWanted = true;
let playingTurnId = "";

function setMicUi(open: boolean): void {
  micBtn.dataset.open = open ? "1" : "0";
  micBtn.textContent = open ? "关麦" : "开麦";
}

async function startMic(): Promise<boolean> {
  if (!listenReady) return false;
  micWanted = true;
  if (mic.open) return true;
  try {
    await mic.start();
    setMicUi(true);
    client.send({ type: "mic_state", open: true });
    return true;
  } catch {
    micBtn.textContent = "麦不可用";
    return false;
  }
}

function stopMic(): void {
  micWanted = false;
  if (!mic.open) return;
  client.send({ type: "mic_state", open: false });
  mic.stop();
  setMicUi(false);
}

async function refreshCaps(): Promise<void> {
  try {
    const res = await fetch("/health");
    const body = (await res.json()) as { listen?: string; speak?: string };
    listenReady = body.listen === "sherpa";
    const listen = listenReady ? "听开" : "听关";
    const speak = body.speak === "volc" ? "说出" : "说蜂鸣";
    caps.textContent = `${listen} · ${speak}`;
    micBtn.disabled = !listenReady;
    micBtn.title = listenReady
      ? "麦克风常开：她说话时也能插话。点页面任意处授权后开始听。"
      : "本地听模型未就绪：pip install -e '.[asr]' && bash scripts/download_asr_models.sh ，然后重启后端";
  } catch {
    caps.textContent = "听? · 说?";
  }
}

void refreshCaps();

async function unlockAndListen(event: Event): Promise<void> {
  player.unlock();
  if (!listenReady || !micWanted || mic.open) return;
  const target = event.target;
  if (target instanceof Node && micBtn.contains(target)) return;
  await startMic();
}

window.addEventListener("pointerdown", (event) => {
  void unlockAndListen(event);
});
window.addEventListener("keydown", () => player.unlock(), { once: true });

form.addEventListener("submit", (event) => {
  event.preventDefault();
  player.resume();
  const text = input.value.trim();
  if (!text) return;
  if (playingTurnId) {
    player.cancel(playingTurnId);
    renderer.cancel();
    playingTurnId = "";
  }
  panel.addUser(text);
  client.sendText(text);
  input.value = "";
  input.focus();
});

micBtn.addEventListener("click", async () => {
  player.resume();
  if (!listenReady) {
    panel.onServer({ type: "error", message: "听还没开：先装 ASR 模型并重启后端。" });
    return;
  }
  if (mic.open) {
    stopMic();
    return;
  }
  await startMic();
});
