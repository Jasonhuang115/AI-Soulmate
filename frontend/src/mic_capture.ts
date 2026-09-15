export class MicCapture {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private sink: MediaStreamAudioDestinationNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private boot: Promise<void> | null = null;

  constructor(private readonly onFrame: (pcm: ArrayBuffer) => void) {}

  get open(): boolean {
    return this.stream !== null;
  }

  async start(): Promise<void> {
    if (this.stream) return;
    if (!this.boot) this.boot = this._open();
    try {
      await this.boot;
    } finally {
      this.boot = null;
    }
  }

  private async _open(): Promise<void> {
    if (this.stream) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    try {
      this.ctx = new AudioContext({ sampleRate: 16000 });
      await this.ctx.audioWorklet.addModule("/pcm-worklet.js");
      this.source = this.ctx.createMediaStreamSource(stream);
      this.node = new AudioWorkletNode(this.ctx, "pcm-worklet");
      this.node.port.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) this.onFrame(ev.data);
      };
      // Keep the worklet running without routing mic to speakers, which would
      // defeat echoCancellation and feed her TTS back into ASR.
      this.sink = this.ctx.createMediaStreamDestination();
      this.source.connect(this.node);
      this.node.connect(this.sink);
      this.stream = stream;
      if (this.ctx.state === "suspended") await this.ctx.resume();
    } catch (err) {
      stream.getTracks().forEach((track) => track.stop());
      this.node = null;
      this.source = null;
      this.sink = null;
      void this.ctx?.close();
      this.ctx = null;
      throw err;
    }
  }

  stop(): void {
    this.node?.disconnect();
    this.source?.disconnect();
    this.sink?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.ctx?.close();
    this.node = null;
    this.source = null;
    this.sink = null;
    this.stream = null;
    this.ctx = null;
  }
}
