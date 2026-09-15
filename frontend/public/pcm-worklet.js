class PcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buf = [];
    this._ratio = sampleRate / 16000;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i += this._ratio) {
      const idx = Math.floor(i);
      this._buf.push(channel[idx] || 0);
      if (this._buf.length >= 320) {
        const frame = this._buf.splice(0, 320);
        const pcm = new Int16Array(320);
        for (let j = 0; j < 320; j++) {
          const s = Math.max(-1, Math.min(1, frame[j]));
          pcm[j] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
      }
    }
    return true;
  }
}

registerProcessor("pcm-worklet", PcmWorklet);
