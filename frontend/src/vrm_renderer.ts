import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { VRM, VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import { createVRMAnimationClip, VRMAnimationLoaderPlugin } from "@pixiv/three-vrm-animation";
import * as THREE from "three";
import {
  hasPerformable,
  isSentenceCommand,
  shouldApplyImmediate,
  type AvatarCmd,
} from "./avatar_policy";
import {
  debugMotionKeys,
  gestureUrl,
  loadCatalog,
  pickModelUrl,
  type GestureCatalog,
} from "./vrm/catalog";
import { VrmEmote } from "./vrm/emote";

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
  private idleAction: THREE.AnimationAction | null = null;
  private gestureAction: THREE.AnimationAction | null = null;
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
    if (cmd.immediate && this.sentenceHold) this.sentenceHold = false;
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
    this.restoreIdle();
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
    if (cmd.expression) this.emote?.play(cmd.expression);
    if (cmd.motion) void this.playMotion(cmd.motion);
    this.refreshDebugLabel(cmd.motion ?? undefined);
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
    const camera = new THREE.PerspectiveCamera(22, width / height, 0.1, 20);
    camera.position.set(0, 1.2, 2.4);
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
    controls.minDistance = 1.1;
    controls.maxDistance = 3.2;
    controls.target.set(0, 1.15, 0);
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
    this.setStatus("", true);
  }

  private async loadVrm(url: string): Promise<void> {
    if (!this.scene || !this.camera) return;
    this.setStatus("加载形象…");
    if (this.vrm) {
      this.scene.remove(this.vrm.scene);
      VRMUtils.deepDispose(this.vrm.scene);
      this.vrm = null;
    }
    this.mixer = null;
    this.idleAction = null;
    this.gestureAction = null;
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
    this.mixer.addEventListener("finished", () => this.restoreIdle());
    this.emote = new VrmEmote(vrm, this.camera);
    if (this.debug) {
      (window as unknown as { __asm?: unknown }).__asm = { vrm, mixer: this.mixer };
    }
    await this.playIdle();
    this.resetCamera();
    this.setStatus("", true);
  }

  private async playIdle(): Promise<void> {
    const file = this.catalog.idle;
    if (!file || !this.mixer) return;
    const clip = await this.loadClip(file);
    if (!clip) return;
    this.idleAction?.stop();
    const action = this.mixer.clipAction(clip);
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.play();
    this.idleAction = action;
  }

  private async playMotion(name: string): Promise<void> {
    const spec = this.catalog.gestures?.[name];
    const file = spec?.file;
    if (!file || !this.mixer || !this.vrm) {
      console.debug("vrm motion missing", name);
      return;
    }
    const clip = await this.loadClip(file);
    if (!clip) return;
    this.idleAction?.fadeOut(0.18);
    this.gestureAction?.stop();
    const action = this.mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = false;
    action.reset().fadeIn(0.12).play();
    this.gestureAction = action;
  }

  private restoreIdle(): void {
    this.gestureAction?.fadeOut(0.2);
    this.gestureAction = null;
    if (this.idleAction) {
      this.idleAction.reset().fadeIn(0.2).play();
    }
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
    const head = this.vrm?.humanoid.getNormalizedBoneNode("head");
    if (!head || !this.camera || !this.controls) return;
    const pos = head.getWorldPosition(new THREE.Vector3());
    this.camera.position.set(this.camera.position.x, pos.y, this.camera.position.z);
    this.controls.target.set(pos.x, pos.y, pos.z);
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
      if (motion) this.apply({ motion, immediate: true });
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
