export type FaceWeights = Record<string, number>;

const FACES: Record<string, FaceWeights> = {
  neutral: {},
  listening: {},
  happy: { happy: 1 },
  playful: { happy: 0.7 },
  shy: { relaxed: 0.6, lookDown: 0.4 },
  sad: { sad: 1 },
  surprised: { surprised: 1 },
  angry: { angry: 1 },
  thinking: { relaxed: 0.3, lookUp: 0.5 },
};

export function faceWeights(logic: string | null | undefined, intensity = 1): FaceWeights {
  const key = logic || "neutral";
  const base = FACES[key] ?? (key === "neutral" ? {} : { [key]: 1 });
  const scale = Math.max(0, Math.min(1, intensity));
  const out: FaceWeights = {};
  for (const [name, value] of Object.entries(base)) {
    out[name] = value * scale;
  }
  return out;
}
