import type { PlaybackSession } from "../types";

export function nowPlayingEmptyLabel(): string {
  return "No active streams";
}

/** Compact secondary line: "S01 E03 · 42m" or "1h 18m" / "Paused · 12m". */
export function formatNowPlayingLine(session: PlaybackSession): string | null {
  const bits: string[] = [];
  if (session.subtitle) bits.push(session.subtitle);
  if (session.paused && session.progress) {
    bits.push(`Paused · ${session.progress}`);
  } else if (session.progress) {
    bits.push(session.progress);
  } else if (session.paused) {
    bits.push("Paused");
  }
  return bits.length ? bits.join(" · ") : null;
}

export function hasNowPlayingSection(
  nowPlaying: PlaybackSession[] | null | undefined,
): nowPlaying is PlaybackSession[] {
  return Array.isArray(nowPlaying);
}
