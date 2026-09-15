export type AudioChunkMsg = {
  type: "audio_chunk";
  turn_id: string;
  sentence_idx: number;
  seq: number;
  sample_rate: number;
  mouth_energy: number[];
  pcm_b64: string;
};

function decodePcm16(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toAudioBuffer(ctx: AudioContext, pcm: ArrayBuffer, sampleRate: number): AudioBuffer {
  const view = new DataView(pcm);
  const count = Math.floor(pcm.byteLength / 2);
  const buffer = ctx.createBuffer(1, count, sampleRate);
  const channel = buffer.getChannelData(0);
  for (let i = 0; i < count; i++) {
    channel[i] = view.getInt16(i * 2, true) / 32768;
  }
  return buffer;
}

export class AudioPlayer {
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private committed = new Set<string>();
  private playhead = 0;
  private sources: AudioBufferSourceNode[] = [];
  private readonly queued = new Map<string, AudioChunkMsg[]>();

  constructor(
    private readonly onSentenceStart: (turnId: string, idx: number) => void,
    private readonly onMouth: (value: number) => void = () => undefined,
  ) {}

  resume(): void {
    const ctx = this.ensureCtx();
    if (ctx.state === "suspended") void ctx.resume();
  }

  unlock(): void {
    this.resume();
  }

  enqueue(chunk: AudioChunkMsg): void {
    const list = this.queued.get(chunk.turn_id) ?? [];
    list.push(chunk);
    list.sort((a, b) => a.sentence_idx - b.sentence_idx || a.seq - b.seq);
    this.queued.set(chunk.turn_id, list);
    if (this.committed.has(chunk.turn_id)) this.schedule(chunk.turn_id);
  }

  commit(turnId: string): void {
    this.committed.add(turnId);
    this.schedule(turnId);
  }

  cancel(turnId: string): void {
    this.committed.delete(turnId);
    this.queued.delete(turnId);
    const ctx = this.ctx;
    const gain = this.gain;
    if (ctx && gain) {
      const now = ctx.currentTime;
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.linearRampToValueAtTime(0.0001, now + 0.05);
    }
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
    }
    this.sources = [];
    this.playhead = 0;
    this.onMouth(0);
    if (gain && ctx) {
      gain.gain.setValueAtTime(1, ctx.currentTime + 0.06);
    }
  }

  duck(): void {
    const ctx = this.ctx;
    const gain = this.gain;
    if (!ctx || !gain) return;
        gain.gain.setTargetAtTime(0.08, ctx.currentTime, 0.02);
  }

  unduck(): void {
    const ctx = this.ctx;
    const gain = this.gain;
    if (!ctx || !gain) return;
    gain.gain.setTargetAtTime(1, ctx.currentTime, 0.05);
  }

  private ensureCtx(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.gain = this.ctx.createGain();
      this.gain.connect(this.ctx.destination);
    }
    return this.ctx;
  }

  private schedule(turnId: string): void {
    const ctx = this.ensureCtx();
    const gain = this.gain;
    if (!gain) return;
    const list = this.queued.get(turnId);
    if (!list) return;
    if (this.playhead < ctx.currentTime) this.playhead = ctx.currentTime;
    while (list.length) {
      const chunk = list.shift();
      if (!chunk) break;
      const buffer = toAudioBuffer(ctx, decodePcm16(chunk.pcm_b64), chunk.sample_rate);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gain);
      const startAt = this.playhead;
      source.start(startAt);
      const delayMs = Math.max(0, (startAt - ctx.currentTime) * 1000);
      if (chunk.seq === 0) {
        window.setTimeout(() => this.onSentenceStart(chunk.turn_id, chunk.sentence_idx), delayMs);
      }
      chunk.mouth_energy.forEach((value, i) => {
        window.setTimeout(() => this.onMouth(value), delayMs + i * 20);
      });
      this.playhead = startAt + buffer.duration;
      this.sources.push(source);
    }
  }
}
