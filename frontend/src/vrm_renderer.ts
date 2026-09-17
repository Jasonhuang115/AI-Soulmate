import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { VRM, VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import { createVRMAnimationClip, VRMAnimationLoaderPlugin } from "@pixiv/three-vrm-animation";
import * as THREE from "three";
import {
  hasPerformable,
  isSentenceCommand,
  motionNames,
  shouldApplyImmediate,
  type AvatarCmd,
} from "./avatar_policy";
import {
  clipFiles,
  debugMotionKeys,
  gestureUrl,
  loadCatalog,
  pickModelUrl,
  type GestureCatalog,
} from "./vrm/catalog";
import { VrmEmote } from "./vrm/emote";
import { MotionRuntime } from "./vrm/motion_runtime";

const DEBUG_FACES = ["neutral", "happy", "shy", "sad", "surprised", "angry", "thinking"] as const;

export class VrmRenderer {
  private readonly queued = new Map<string, AvatarCmd>();
  private readonly pendingStart = new Set<string>();
  private sentenceHold = false;
  private catalog: GestureCatalog = { gestures: {} };
  private app: THREE.WebGLRenderer | null = null;
  private scene: THREE.Scene | null = null;
  private camera: THREE.PerspectiveCamera | null = null;
  private controls: OrbitControls | null = null;
  private clock = new THREE.Clock();
  private mixer: THREE.AnimationMixer | null = null;
  private vrm: VRM | null = null;
  private emote: VrmEmote | null = null;
  private motions: MotionRuntime | null = null;
  private clipCache = new Map<string, THREE.AnimationClip>();
  private debugKeys: Record<string, string> = {};
  private readonly debug: boolean;
  private running = false;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly statusEl: HTMLElement,
    private readonly debugEl: HTMLElement | null = null,
  ) {
    const params = new URLSearchParams(location.search);
    this.debug = params.get("faceDebug") !== null;
    void this.start();
  }

  queue(cmd: AvatarCmd): void {
    if (!hasPerformable(cmd)) return;
    if (isSentenceCommand(cmd)) {
      const key = `${cmd.turn_id}:${cmd.sentence_idx}`;
      if (this.pendingStart.has(key)) {
        this.pendingStart.delete(key);
        this.sentenceHold = true;
        this.apply(cmd);
        return;
      }
      this.queued.set(key, cmd);
      return;
    }
    if (this.debug && cmd.immediate) return;
    if (cmd.immediate && !shouldApplyImmediate(cmd, this.sentenceHold)) return;
    if (cmd.immediate && this.sentenceHold && motionNames(cmd).length) {
      // keep sentence face; body may interrupt
    } else if (cmd.immediate && this.sentenceHold) {
      this.sentenceHold = false;
    }
    this.apply(cmd);
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
    this.setMouthOpen(0);
    this.motions?.stopBody();
    this.setDebugLabel("");
  }

  setMouthOpen(value: number): void {
    this.emote?.setMouth(value);
  }

  destroy(): void {
    this.running = false;
    this.controls?.dispose();
    this.app?.dispose();
  }

  private apply(cmd: AvatarCmd): void {
    if (cmd.control === "stop") this.motions?.stopBody();
    if (cmd.expression) this.emote?.play(cmd.expression, cmd.intensity ?? 1);
    const names = motionNames(cmd);
    if (names.length) this.motions?.perform(names);
    this.refreshDebugLabel(names[0]);
  }

  private async start(): Promise<void> {
    try {
      this.catalog = await loadCatalog();
      this.debugKeys = debugMotionKeys(this.catalog);
      await this.mount();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("vrm failed", err);
      this.setStatus(message);
    }
  }

  private async mount(): Promise<void> {
    const parent = this.canvas.parentElement;
    const width = parent?.clientWidth || 640;
    const height = parent?.clientHeight || 720;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, width / height, 0.05, 40);
    camera.position.set(0, 0.9, 3.6);
    const renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: true,
    });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    const dir = new THREE.DirectionalLight(0xffffff, 1.15);
    dir.position.set(1, 1.4, 1).normalize();
    scene.add(dir);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.minDistance = 1.2;
    controls.maxDistance = 8;
    controls.target.set(0, 0.85, 0);
    controls.update();

    this.scene = scene;
    this.camera = camera;
    this.app = renderer;
    this.controls = controls;
    window.addEventListener("resize", () => this.resize());

    const params = new URLSearchParams(location.search);
    const modelUrl = pickModelUrl(this.catalog, params.get("model"));
    await this.loadVrm(modelUrl);
    this.bindDrop();
    if (this.debug) this.enableDebug();
    this.running = true;
    this.clock.start();
    this.loop();
  }

  private async loadVrm(url: string): Promise<void> {
    if (!this.scene || !this.camera) return;
    this.setStatus("加载形象…");
    this.motions?.resetReady();
    if (this.vrm) {
      this.scene.remove(this.vrm.scene);
      VRMUtils.deepDispose(this.vrm.scene);
      this.vrm = null;
    }
    this.mixer = null;
    this.clipCache.clear();

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    const gltf = await loader.loadAsync(url);
    const vrm = gltf.userData.vrm as VRM | undefined;
    if (!vrm) throw new Error("VRM 模型无效");
    VRMUtils.removeUnnecessaryVertices(gltf.scene);
    VRMUtils.combineSkeletons(gltf.scene);
    VRMUtils.rotateVRM0(vrm);
    vrm.scene.traverse((obj) => {
      obj.frustumCulled = false;
    });
    this.scene.add(vrm.scene);
    this.vrm = vrm;
    this.mixer = new THREE.AnimationMixer(vrm.scene);
    this.mixer.addEventListener("finished", (event) => {
      const action = (event as { action?: THREE.AnimationAction }).action;
      this.motions?.onFinished(action);
    });
    this.emote = new VrmEmote(vrm, this.camera);
    this.motions = new MotionRuntime(
      this.catalog,
      () => this.mixer,
      (file) => this.loadClip(file),
    );
    if (this.debug) {
      (window as unknown as { __asm?: unknown }).__asm = { vrm, mixer: this.mixer };
    }
    await this.preloadClips();
    this.motions.markReady();
    this.motions.perform([]);
    this.resetCamera();
    this.setStatus("", true);
  }

  private async preloadClips(): Promise<void> {
    const files = clipFiles(this.catalog);
    const total = files.length;
    if (!total) return;
    let done = 0;
    const limit = 6;
    const queue = files.slice();
    const worker = async () => {
      while (queue.length) {
        const file = queue.shift();
        if (!file) break;
        await this.loadClip(file);
        done += 1;
        this.setStatus(`加载动作 ${done}/${total}`);
      }
    };
    await Promise.all(Array.from({ length: Math.min(limit, total) }, () => worker()));
  }

  private async loadClip(file: string): Promise<THREE.AnimationClip | null> {
    const cached = this.clipCache.get(file);
    if (cached) return cached;
    if (!this.vrm) return null;
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMAnimationLoaderPlugin(parser));
    const url = gestureUrl(file);
    const gltf = await loader.loadAsync(url).catch((err) => {
      console.debug("vrma missing", url, err);
      return null;
    });
    const animation = gltf?.userData?.vrmAnimations?.[0];
    if (!animation) return null;
    const clip = createVRMAnimationClip(animation, this.vrm);
    this.clipCache.set(file, clip);
    return clip;
  }

  private resetCamera(): void {
    if (!this.vrm || !this.camera || !this.controls) return;
    this.vrm.scene.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(this.vrm.scene);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    if (!Number.isFinite(size.y) || size.y < 0.2) return;

    const fov = (this.camera.fov * Math.PI) / 180;
    const margin = 1.12;
    const distH = ((size.y * margin) / 2) / Math.tan(fov / 2);
    const distW = ((size.x * margin) / 2) / Math.tan(fov / 2) / Math.max(this.camera.aspect, 0.1);
    const distance = Math.max(distH, distW, 1.6);

    this.camera.near = 0.05;
    this.camera.far = Math.max(40, distance * 10);
    this.camera.updateProjectionMatrix();
    this.camera.position.set(center.x, center.y + size.y * 0.06, center.z + distance);
    this.controls.target.set(center.x, center.y - size.y * 0.06, center.z);
    this.controls.minDistance = Math.max(distance * 0.4, 0.9);
    this.controls.maxDistance = distance * 3;
    this.controls.update();
  }

  private resize(): void {
    if (!this.app || !this.camera) return;
    const parent = this.canvas.parentElement;
    const w = parent?.clientWidth || 640;
    const h = parent?.clientHeight || 720;
    this.app.setPixelRatio(window.devicePixelRatio);
    this.app.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private loop = (): void => {
    if (!this.running) return;
    requestAnimationFrame(this.loop);
    const delta = this.clock.getDelta();
    this.mixer?.update(delta);
    this.emote?.update(delta);
    this.vrm?.update(delta);
    this.controls?.update();
    if (this.app && this.scene && this.camera) this.app.render(this.scene, this.camera);
  };

  private bindDrop(): void {
    const canvas = this.canvas;
    canvas.addEventListener("dragover", (event) => event.preventDefault());
    canvas.addEventListener("drop", (event) => {
      event.preventDefault();
      const file = event.dataTransfer?.files?.[0];
      if (!file || !file.name.toLowerCase().endsWith(".vrm")) return;
      const url = URL.createObjectURL(file);
      void this.loadVrm(url);
    });
  }

  private enableDebug(): void {
    window.addEventListener("keydown", (event) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      const key = event.key;
      if (key >= "1" && key <= "7") {
        const face = DEBUG_FACES[Number(key) - 1];
        if (face) this.apply({ expression: face, immediate: true });
        return;
      }
      const motion = this.debugKeys[key];
      if (motion) this.apply({ motions: [motion], immediate: true });
    });
    this.setDebugLabel("faceDebug: 1-7 表情，q/w/e… 动作；拖入 .vrm 换人");
  }

  private setStatus(text: string, ok = false): void {
    this.statusEl.textContent = text;
    this.statusEl.dataset.ok = ok ? "1" : "0";
    this.statusEl.hidden = ok || !text;
  }

  private refreshDebugLabel(motion?: string): void {
    if (!this.debug) return;
    const parts = [motion ? `motion: ${motion}` : ""].filter(Boolean);
    this.setDebugLabel(parts.join(" · ") || "faceDebug");
  }

  private setDebugLabel(text: string): void {
    const el = this.debugEl;
    if (!el || !this.debug) return;
    el.textContent = text;
    el.hidden = !text;
  }
}
