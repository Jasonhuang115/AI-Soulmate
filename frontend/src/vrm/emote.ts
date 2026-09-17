import type { VRM, VRMExpressionManager } from "@pixiv/three-vrm";
import * as THREE from "three";
import { faceWeights } from "./expressions";

const BLINK_CLOSE = 0.12;
const BLINK_OPEN_MIN = 2.2;
const BLINK_OPEN_MAX = 4.4;

export class VrmEmote {
  private readonly manager: VRMExpressionManager | null;
  private current: Record<string, number> = {};
  private mouth = 0;
  private targetMouth = 0;
  private blinkOpen = true;
  private blinkWait = 1;
  private blinkEnabled = true;

  constructor(vrm: VRM, camera: THREE.Object3D) {
    this.manager = vrm.expressionManager ?? null;
    if (vrm.lookAt) {
      const target = new THREE.Object3D();
      camera.add(target);
      vrm.lookAt.target = target;
    }
  }

  play(logic: string | null | undefined, intensity = 1): void {
    const next = faceWeights(logic, intensity);
    for (const name of Object.keys(this.current)) {
      if (!(name in next)) this.manager?.setValue(name, 0);
    }
    this.current = next;
    this.blinkEnabled = Object.keys(next).length === 0;
    for (const [name, value] of Object.entries(next)) {
      this.manager?.setValue(name, value);
    }
  }

  setMouth(value: number): void {
    this.targetMouth = Math.max(0, Math.min(1, value));
  }

  update(delta: number): void {
    this.mouth += (this.targetMouth - this.mouth) * Math.min(1, delta * 12);
    const weight = this.blinkEnabled ? this.mouth * 0.55 : this.mouth * 0.28;
    this.manager?.setValue("aa", weight);
    this.tickBlink(delta);
  }

  private tickBlink(delta: number): void {
    if (!this.manager) return;
    this.blinkWait -= delta;
    if (this.blinkWait > 0) return;
    if (this.blinkOpen && this.blinkEnabled) {
      this.blinkOpen = false;
      this.blinkWait = BLINK_CLOSE;
      this.manager.setValue("blink", 1);
      return;
    }
    this.blinkOpen = true;
    this.blinkWait = BLINK_OPEN_MIN + Math.random() * (BLINK_OPEN_MAX - BLINK_OPEN_MIN);
    this.manager.setValue("blink", 0);
  }
}
