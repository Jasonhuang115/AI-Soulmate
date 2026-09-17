export type GestureSpec = {
  file?: string;
  label?: string;
  desc?: string;
  group?: string;
  phase?: number;
  kind?: "gesture" | "pose" | "loop" | "transition";
  holds?: string;
  face?: string;
  aliases?: string[];
  mixamo?: string;
};

export type GestureCatalog = {
  prompt_phase?: number;
  default_model?: string;
  idle?: string;
  gestures?: Record<string, GestureSpec>;
};

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

export function clipFiles(catalog: GestureCatalog): string[] {
  const files = new Set<string>();
  if (catalog.idle) files.add(catalog.idle);
  for (const spec of Object.values(catalog.gestures ?? {})) {
    if (spec.file) files.add(spec.file);
    if (spec.holds) {
      const hold = catalog.gestures?.[spec.holds];
      if (hold?.file) files.add(hold.file);
    }
  }
  return [...files];
}

export function debugMotionKeys(catalog: GestureCatalog): Record<string, string> {
  const keys = ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "a", "s", "d", "f", "g"];
  const names = Object.keys(catalog.gestures ?? {});
  const out: Record<string, string> = {};
  names.slice(0, keys.length).forEach((name, i) => {
    out[keys[i]] = name;
  });
  return out;
}
