export type AvatarCmd = {
  turn_id?: string | null;
  sentence_idx?: number | null;
  expression?: string | null;
  motion?: string | null;
  motions?: string[] | null;
  control?: string | null;
  intensity?: number | null;
  immediate?: boolean;
};

export function motionNames(cmd: AvatarCmd): string[] {
  if (cmd.motions && cmd.motions.length) return cmd.motions.filter(Boolean);
  return cmd.motion ? [cmd.motion] : [];
}

export function isSentenceCommand(cmd: AvatarCmd): boolean {
  return cmd.turn_id != null && cmd.sentence_idx != null && !cmd.immediate;
}

export function shouldApplyImmediate(cmd: AvatarCmd, sentenceHold: boolean): boolean {
  if (cmd.control === "stop" || motionNames(cmd).length) return true;
  if (!sentenceHold) return true;
  return false;
}

export function hasPerformable(cmd: AvatarCmd): boolean {
  return Boolean(cmd.expression || cmd.control || motionNames(cmd).length);
}
