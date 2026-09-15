import * as PIXI from "pixi.js";
import {
  expressionNames,
  isSentenceCommand,
  shouldApplyImmediate,
  type AvatarCmd,
} from "./avatar_policy";

export { expressionNames, isSentenceCommand, shouldApplyImmediate };
export type { AvatarCmd };

type FaceParam = { id: string; val: number; calc?: string };

type FaceMap = {
  lipsync_param?: string;
  fallback_expression?: string;
  expressions?: Record<string, string>;
  expression_params?: Record<string, FaceParam[]>;
  param_defaults?: Record<string, number>;
  motions?: Record<string, { group?: string; index?: number }>;
  idle?: { group?: string; index?: number };
};

type Candidate = { dir: string; settings: string; cubism: 2 | 4 };

const CANDIDATES: Candidate[] = [
  { dir: "/models/kei/", settings: "Kei.model3.json", cubism: 4 },
  { dir: "/models/kei/", settings: "kei.model3.json", cubism: 4 },
  { dir: "/models/epsilon/", settings: "Epsilon2.1.model.json", cubism: 2 },
];

const DEBUG_FACES = ["neutral", "happy", "shy", "sad", "surprised", "angry", "thinking"] as const;
const DEBUG_MOTIONS: Record<string, string> = {
  n: "nod",
  t: "tilt",
  h: "shake_head",
  w: "wave",
  l: "laugh",
};
const IDLE_MOTION_PRIORITY = 1;
const GESTURE_MOTION_PRIORITY = 3;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }
    const el = document.createElement("script");
    el.src = src;
    el.async = false;
    el.onload = () => resolve();
    el.onerror = () => reject(new Error(`failed to load ${src}`));
    document.head.append(el);
  });
}

async function isModelJson(url: string): Promise<boolean> {
  const res = await fetch(url).catch(() => null);
  if (!res?.ok) return false;
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("text/html")) return false;
  const text = await res.text();
  const trimmed = text.trim();
  return trimmed.startsWith("{") && (trimmed.includes("\"model\"") || trimmed.includes("FileReferences"));
}

export class Live2DRenderer {
  private mouth = 0;
  private targetMouth = 0;
  private queued = new Map<string, AvatarCmd>();
  private pendingStart = new Set<string>();
  private map: FaceMap = {};
  private model: Live2DModelInstance | null = null;
  private app: PIXI.Application | null = null;
  private mouthParam = "PARAM_MOUTH_OPEN_Y";
  private sentenceHold = false;
  private heldFace: string | null = null;
  private debugIndex = 0;
  private readonly debug: boolean;
  private readonly debugFace: string;
  private readonly onBeforeModelUpdate = (): void => this.paintFace();

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly statusEl: HTMLElement,
    private readonly debugEl: HTMLElement | null = null,
  ) {
    const params = new URLSearchParams(location.search);
    const raw = params.get("faceDebug");
    this.debug = raw !== null;
    this.debugFace = raw && raw !== "1" ? raw : "";
    void this.start();
  }

  queue(cmd: AvatarCmd): void {
    if (cmd.motion) this.playMotion(cmd.motion);
    if (!cmd.expression) return;
    const face: AvatarCmd = { ...cmd, motion: null };
    if (isSentenceCommand(face)) {
      const key = `${face.turn_id}:${face.sentence_idx}`;
      if (this.pendingStart.has(key)) {
        this.pendingStart.delete(key);
        this.sentenceHold = true;
        this.apply(face);
        return;
      }
      this.queued.set(key, face);
      return;
    }
    if (this.debug && face.immediate) return;
    if (face.immediate && !shouldApplyImmediate(face, this.sentenceHold)) return;
    if (face.immediate && this.sentenceHold) this.sentenceHold = false;
    this.apply(face);
  }

  onSentenceStart(turnId: string, idx: number): void {
    const key = `${turnId}:${idx}`;
    const cmd = this.queued.get(key);
    if (cmd) {
      this.queued.delete(key);
      this.sentenceHold = true;
      this.apply(cmd);
      return;
    }
    this.pendingStart.add(key);
  }

  cancel(): void {
    this.queued.clear();
    this.pendingStart.clear();
    this.sentenceHold = false;
    this.heldFace = null;
    this.setMouthOpen(0);
    this.setDebugLabel("");
  }

  setMouthOpen(value: number): void {
    this.targetMouth = Math.max(0, Math.min(1, value));
  }

  destroy(): void {
    this.model?.internalModel.off("beforeModelUpdate", this.onBeforeModelUpdate);
    this.app?.destroy(false);
  }

  private apply(cmd: AvatarCmd): void {
    if (cmd.expression) this.applyExpression(cmd.expression);
    if (cmd.motion) this.playMotion(cmd.motion);
  }

  private playMotion(name: string): void {
    const model = this.model;
    if (!model) return;
    const spec = this.map.motions?.[name];
    if (!spec) {
      console.debug("live2d motion missing", name);
      return;
    }
    const group = spec.group ?? "";
    const index = spec.index ?? 0;
    void model.motion(group, index, GESTURE_MOTION_PRIORITY).then((started) => {
      if (!started) console.debug("live2d motion rejected", name, group, index);
    });
    this.refreshDebugLabel(name);
  }

  private applyExpression(logic: string): void {
    const model = this.model;
    if (!model) return;
    this.heldFace = logic;
    const mapped = this.map.expressions?.[logic] ?? logic;
    const names = expressionNames(mapped);
    console.debug("live2d expression", {
      logic,
      mapped,
      names,
      hasManager: Boolean(model.internalModel.motionManager.expressionManager),
    });
    void model.expression(mapped).catch(() => undefined);
    this.paintFace();
    this.refreshDebugLabel();
  }

  private paintFace(): void {
    const model = this.model;
    if (!model) return;
    // After the .mtn writes all params (including baked face). Only overlay
    // expression + mouth so arms/body from the motion keep moving.
    if (this.heldFace) this.applyParams(this.heldFace);
    this.mouth += (this.targetMouth - this.mouth) * 0.35;
    this.setParam(this.mouthParam, this.mouth);
  }

  private applyParams(logic: string): void {
    const defaults = this.map.param_defaults ?? {};
    for (const [id, value] of Object.entries(defaults)) {
      this.setParam(id, value);
    }
    const params = this.map.expression_params?.[logic] ?? [];
    for (const item of params) {
      this.setParam(item.id, item.val);
    }
  }

  private setParam(id: string, value: number): void {
    try {
      this.model?.internalModel.coreModel.setParamFloat(id, value);
    } catch {
      /* param missing */
    }
  }

  private async start(): Promise<void> {
    try {
      await this.mount();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("live2d failed", err);
      this.setStatus(message);
    }
  }

  private async mount(): Promise<void> {
    const picked = await this.pickModel();
    if (!picked) {
      this.setStatus("Live2D 模型未找到");
      return;
    }
    const mapRes = await fetch(`${picked.dir}avatar_map.json`).catch(() => null);
    if (mapRes?.ok) this.map = (await mapRes.json()) as FaceMap;
    this.mouthParam =
      this.map.lipsync_param ?? (picked.cubism === 4 ? "ParamMouthOpenY" : "PARAM_MOUTH_OPEN_Y");
    (window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI;
    const { Live2DModel } = picked.cubism === 4 ? await this.loadCubism4() : await this.loadCubism2();
    Live2DModel.registerTicker(PIXI.Ticker);
    this.app = new PIXI.Application({
      view: this.canvas,
      backgroundAlpha: 0,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });
    const model = await Live2DModel.from(`${picked.dir}${picked.settings}`, {
      autoInteract: false,
      motionPreload: "ALL",
    });
    this.model = model;
    model.internalModel.updateNaturalMovements = () => undefined;
    this.app.stage.addChild(model as unknown as PIXI.DisplayObject);
    this.fit();
    window.addEventListener("resize", () => this.fit());
    model.internalModel.on("beforeModelUpdate", this.onBeforeModelUpdate);
    const idle = this.map.idle;
    if (idle?.group) void model.motion(idle.group, idle.index ?? 0, IDLE_MOTION_PRIORITY);
    this.setStatus("", true);
    if (this.debug) {
      this.enableDebug();
      if (this.debugFace) this.apply({ expression: this.debugFace, immediate: true });
      else this.setDebugLabel("faceDebug: 1-7 表情，n/t/h 点头晃头，w 挥手，l 笑");
    }
  }

  private enableDebug(): void {
    window.addEventListener("keydown", (event) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      const key = event.key;
      if (key >= "1" && key <= "7") {
        const face = DEBUG_FACES[Number(key) - 1];
        if (face) this.apply({ expression: face, immediate: true });
        return;
      }
      if (key === "e" || key === "E") {
        const face = DEBUG_FACES[this.debugIndex % DEBUG_FACES.length];
        this.debugIndex += 1;
        this.apply({ expression: face, immediate: true });
        return;
      }
      const motion = DEBUG_MOTIONS[key];
      if (motion) this.apply({ motion, immediate: true });
    });
  }

  private async loadCubism2() {
    await loadScript("/live2d.min.js");
    return import("pixi-live2d-display/cubism2");
  }

  private async loadCubism4() {
    await loadScript("https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js");
    return import("pixi-live2d-display/cubism4");
  }

  private async pickModel(): Promise<Candidate | null> {
    for (const item of CANDIDATES) {
      if (await isModelJson(item.dir + item.settings)) return item;
    }
    return null;
  }

  private fit(): void {
    const app = this.app;
    const model = this.model;
    if (!app || !model) return;
    const parent = this.canvas.parentElement;
    const w = parent?.clientWidth || 320;
    const h = parent?.clientHeight || 420;
    app.renderer.resize(w, h);
    const sx = model.scale.x || 1;
    const sy = model.scale.y || 1;
    const mw = (model.width || 1) / sx;
    const mh = (model.height || 1) / sy;
    const logical = mw < 20 && mh < 20;
    const scale = logical
      ? Math.min(w, h) / 2.35
      : Math.min(w / mw, h / mh) * 0.88;
    if (!Number.isFinite(scale) || scale <= 0) return;
    model.scale.set(scale);
    model.anchor.set(0.5, logical ? 0.28 : 0.45);
    model.x = w / 2;
    model.y = logical ? h * 0.46 : h * 0.52;
  }

  private setStatus(text: string, ok = false): void {
    this.statusEl.textContent = text;
    this.statusEl.dataset.ok = ok ? "1" : "0";
    this.statusEl.hidden = ok || !text;
  }

  private refreshDebugLabel(motion?: string): void {
    const parts = [this.heldFace ? `face: ${this.heldFace}` : "", motion ? `motion: ${motion}` : ""].filter(Boolean);
    this.setDebugLabel(parts.join(" · "));
  }

  private setDebugLabel(text: string): void {
    const el = this.debugEl;
    if (!el || !this.debug) return;
    el.textContent = text;
    el.hidden = !text;
  }
}
