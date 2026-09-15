export type ServerMessage = {
  type: string;
  turn_id?: string | null;
  text?: string;
  state?: string;
  message?: string;
  sentence_idx?: number | null;
  seq?: number;
  sample_rate?: number;
  mouth_energy?: number[];
  pcm_b64?: string;
  marks?: Record<string, number>;
  expression?: string | null;
  motion?: string | null;
  immediate?: boolean;
};

export type ClientHandler = (msg: ServerMessage) => void;

export class WsClient {
  private ws: WebSocket | null = null;
  private readonly handlers = new Set<ClientHandler>();

  constructor(private readonly url: string) {}

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.addEventListener("message", (ev) => {
      if (typeof ev.data !== "string") return;
      try {
        const msg = JSON.parse(ev.data) as ServerMessage;
        for (const handler of this.handlers) handler(msg);
      } catch {
        return;
      }
    });
  }

  onMessage(handler: ClientHandler): void {
    this.handlers.add(handler);
  }

  send(payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(payload));
  }

  sendText(text: string): void {
    this.send({ type: "text_input", text });
  }

  sendBinary(buffer: ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(buffer);
  }
}
