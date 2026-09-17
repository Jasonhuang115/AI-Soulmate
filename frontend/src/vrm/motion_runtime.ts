import * as THREE from "three";
import type { GestureCatalog, GestureSpec } from "./catalog";

export class MotionRuntime {
  private mode: "idle" | "pose" | "loop" | "gesture" = "idle";
  private poseName: string | null = null;
  private queue: string[] = [];
  private overlay: THREE.AnimationAction | null = null;
  private base: THREE.AnimationAction | null = null;
  private ready = false;
  private pending: Array<() => void> = [];
  private busy = false;
  private gen = 0;

  constructor(
    private catalog: GestureCatalog,
    private mixerOf: () => THREE.AnimationMixer | null,
    private loadClip: (file: string) => Promise<THREE.AnimationClip | null>,
  ) {}

  markReady(): void {
    this.ready = true;
    const jobs = this.pending.splice(0);
    for (const job of jobs) job();
  }

  resetReady(): void {
    this.ready = false;
    this.queue = [];
    this.pending = [];
    this.overlay?.stop();
    this.base?.stop();
    this.overlay = null;
    this.base = null;
    this.mode = "idle";
    this.poseName = null;
    this.busy = false;
  }

  perform(names: string[]): void {
    const run = () => {
      this.gen += 1;
      this.queue = names.slice();
      this.interruptOverlay();
      void this.kick(this.gen);
    };
    if (!this.ready) {
      this.pending.push(run);
      return;
    }
    run();
  }

  stopBody(): void {
    this.gen += 1;
    this.queue = [];
    this.pending = [];
    this.poseName = null;
    this.interruptOverlay();
    this.mode = "idle";
    void this.playBase(this.catalog.idle, true);
  }

  onFinished(action?: THREE.AnimationAction): void {
    if (action && this.overlay && action !== this.overlay) return;
    if (this.mode !== "gesture") return;
    this.overlay = null;
    this.busy = false;
    this.mode = this.poseName ? "pose" : "idle";
    void this.kick(this.gen);
  }

  private interruptOverlay(): void {
    this.overlay?.stop();
    this.overlay = null;
    this.busy = false;
    if (this.mode === "gesture") this.mode = this.poseName ? "pose" : "idle";
  }

  private canPlay(name: string): boolean {
    const kind = this.spec(name)?.kind || "gesture";
    if (this.poseName && (kind === "gesture" || kind === "loop")) return false;
    return Boolean(this.fileOf(name));
  }

  private spec(name: string): GestureSpec | undefined {
    return this.catalog.gestures?.[name];
  }

  private fileOf(name: string | undefined): string | undefined {
    if (!name) return undefined;
    if (name.endsWith(".vrma")) return name;
    return this.spec(name)?.file;
  }

  private async kick(token?: number): Promise<void> {
    const gen = token ?? this.gen;
    if (this.busy) return;
    while (this.queue.length) {
      if (gen !== this.gen) return;
      const next = this.queue.shift();
      if (!next || !this.canPlay(next)) continue;
      this.busy = true;
      await this.playName(next);
      if (gen !== this.gen) return;
      if (this.mode === "gesture") return;
      this.busy = false;
    }
    if (gen !== this.gen) return;
    await this.restoreBase();
  }

  private async restoreBase(): Promise<void> {
    if (this.poseName) {
      const hold = this.spec(this.poseName)?.holds || this.poseName;
      await this.playBase(this.fileOf(hold), true);
      this.mode = "pose";
      return;
    }
    if (this.mode === "loop") return;
    await this.playBase(this.catalog.idle, true);
    this.mode = "idle";
  }

  private async playName(name: string): Promise<void> {
    const spec = this.spec(name);
    const kind = spec?.kind || "gesture";
    const file = this.fileOf(name);
    if (!file) return;

    if (kind === "pose") {
      this.poseName = name;
      const holdFile = this.fileOf(spec?.holds || name);
      if (holdFile && holdFile !== file) {
        this.mode = "gesture";
        await this.playOverlay(file, true);
        return;
      }
      await this.playBase(holdFile || file, true);
      this.mode = "pose";
      return;
    }
    if (kind === "loop") {
      this.poseName = null;
      await this.playBase(file, true);
      this.mode = "loop";
      return;
    }
    if (kind === "transition") {
      this.poseName = null;
      this.mode = "gesture";
      await this.playOverlay(file, true);
      return;
    }
    this.mode = "gesture";
    await this.playOverlay(file, true);
  }

  private async playOverlay(file: string, fadeBase: boolean): Promise<void> {
    const mixer = this.mixerOf();
    const clip = await this.loadClip(file);
    if (!mixer || !clip) {
      this.mode = this.poseName ? "pose" : "idle";
      return;
    }
    if (fadeBase) this.base?.fadeOut(0.18);
    this.overlay?.stop();
    const action = mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = false;
    action.reset().fadeIn(0.12).play();
    this.overlay = action;
  }

  private async playBase(file: string | undefined, loop: boolean): Promise<void> {
    const mixer = this.mixerOf();
    if (!file || !mixer) return;
    const clip = await this.loadClip(file);
    if (!clip) return;
    this.base?.fadeOut(0.12);
    this.base?.stop();
    const action = mixer.clipAction(clip);
    action.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, loop ? Infinity : 1);
    action.reset().fadeIn(0.2).play();
    this.base = action;
  }
}
