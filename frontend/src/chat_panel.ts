import type { ServerMessage } from "./ws_client";

export class ChatPanel {
  private assistantBuf = "";
  private assistantEl: HTMLElement | null = null;
  private currentTurn: string | null = null;
  private userEl: HTMLElement | null = null;
  private userCommitted = false;

  constructor(
    private readonly log: HTMLOListElement,
    private readonly statusEl: HTMLElement,
  ) {}

  addUser(text: string): void {
    this.assistantEl = null;
    this.assistantBuf = "";
    this.userEl = this.append("user", text);
    this.userCommitted = true;
  }

  setInterimUser(text: string): void {
    if (this.userCommitted && this.userEl) {
      this.userEl = null;
      this.userCommitted = false;
    }
    if (!this.userEl) this.userEl = this.append("user", text);
    else this.userEl.textContent = text;
    this.userEl.dataset.interim = "1";
  }

  commitUser(text: string): void {
    if (!text.trim()) return;
    if (!this.userEl) this.userEl = this.append("user", text);
    else this.userEl.textContent = text;
    delete this.userEl.dataset.interim;
    this.userCommitted = true;
    this.assistantEl = null;
    this.assistantBuf = "";
  }

  onServer(msg: ServerMessage): void {
    if (msg.type === "state" && msg.state) {
      this.statusEl.dataset.state = msg.state;
      this.statusEl.textContent = msg.state;
      if ((msg.state === "speculating" || msg.state === "thinking") && this.userEl?.dataset.interim) {
        delete this.userEl.dataset.interim;
        this.userCommitted = true;
      }
    }
    if (msg.type === "cancel") {
      this.assistantEl = null;
      this.assistantBuf = "";
      this.currentTurn = null;
    }
    if (msg.type === "partial_transcript" && msg.text) {
      this.setInterimUser(msg.text);
    }
    if (msg.type === "utterance_end" && msg.text) {
      this.commitUser(msg.text);
    }
    if (msg.type === "text_delta" && msg.text) {
      if (msg.turn_id && msg.turn_id !== this.currentTurn) {
        this.currentTurn = msg.turn_id;
        this.assistantBuf = "";
        this.assistantEl = this.append("assistant", "");
      }
      this.assistantBuf += msg.text;
      if (this.assistantEl) this.assistantEl.textContent = this.assistantBuf;
    }
    if (msg.type === "error" && msg.message) {
      this.append("error", msg.message);
    }
  }

  private append(role: string, text: string): HTMLElement {
    const li = document.createElement("li");
    li.dataset.role = role;
    li.textContent = text;
    this.log.append(li);
    li.scrollIntoView({ block: "end" });
    return li;
  }
}
