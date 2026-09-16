export type GestureSpec = {
  file?: string;
  label?: string;
  group?: string;
  phase?: number;
  prompt?: boolean;
  mixamo?: string;
};

export type GestureCatalog = {
  prompt_phase?: number;
  default_model?: string;
  idle?: string;
  gestures?: Record<string, GestureSpec>;
};

const FACE: Record<string, string> = {
  neutral: "neutral",
  listening: "neutral",
  happy: "happy",
  playful: "happy",
  shy: "relaxed",
  sad: "sad",
  surprised: "surprised",
  angry: "angry",
  thinking: "relaxed",
};

export function mapExpression(logic: string | null | undefined): string | null {
  if (!logic) return null;
  return FACE[logic] ?? (logic === "neutral" ? "neutral" : logic);
}

export function gestureUrl(file: string): string {
  const name = file.replace(/^\/+/, "");
  if (name.startsWith("gestures/")) return `/${name}`;
  return `/gestures/${name}`;
}

export function pickModelUrl(catalog: GestureCatalog, queryModel: string | null): string {
  if (queryModel) {
    if (queryModel.startsWith("/") || queryModel.startsWith("blob:")) return queryModel;
    if (queryModel.endsWith(".vrm")) return `/models/vrm/${queryModel}`;
    return `/models/vrm/${queryModel}.vrm`;
  }
  return catalog.default_model || "/models/vrm/default.vrm";
}

export async function loadCatalog(): Promise<GestureCatalog> {
  const res = await fetch("/gestures/catalog.json");
  if (!res.ok) return { gestures: {} };
  return (await res.json()) as GestureCatalog;
}

export function debugMotionKeys(catalog: GestureCatalog): Record<string, string> {
  const keys = ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "a", "s", "d", "f", "g"];
  const names = Object.keys(catalog.gestures ?? {}).filter((name) => {
    const phase = catalog.gestures?.[name]?.phase ?? 1;
    return phase <= (catalog.prompt_phase ?? 1);
  });
  const out: Record<string, string> = {};
  names.slice(0, keys.length).forEach((name, i) => {
    out[keys[i]] = name;
  });
  return out;
}
