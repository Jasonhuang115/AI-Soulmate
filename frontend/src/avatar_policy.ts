export type AvatarCmd = {
  turn_id?: string | null;
  sentence_idx?: number | null;
  expression?: string | null;
  motion?: string | null;
  immediate?: boolean;
};

export function isSentenceCommand(cmd: AvatarCmd): boolean {
  return cmd.turn_id != null && cmd.sentence_idx != null && !cmd.immediate;
}

export function shouldApplyImmediate(cmd: AvatarCmd, sentenceHold: boolean): boolean {
  if (!sentenceHold) return true;
  return cmd.expression === "thinking" || cmd.expression === "listening";
}

export function expressionNames(mapped: string): string[] {
  const base = mapped.replace(/\.exp\.json$/i, "").replace(/\.exp3\.json$/i, "");
  return [...new Set([mapped, base, `${base}.exp.json`, `${base}.exp`])];
}
