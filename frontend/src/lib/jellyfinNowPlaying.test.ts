import { describe, expect, it } from "vitest";
import {
  formatNowPlayingLine,
  hasNowPlayingSection,
  nowPlayingEmptyLabel,
} from "./jellyfinNowPlaying";
import type { PlaybackSession } from "../types";

const base: PlaybackSession = {
  id: "1",
  user: "Aurimas",
  title: "The Last of Us",
  subtitle: "S01 E03 · Long, Long Time",
  progress: "42m",
  paused: false,
  artwork_url: "/api/jellyfin/artwork/ep1",
};

describe("jellyfin now playing helpers", () => {
  it("empty label", () => {
    expect(nowPlayingEmptyLabel()).toBe("No active streams");
  });

  it("formats tv episode line", () => {
    expect(formatNowPlayingLine(base)).toBe("S01 E03 · Long, Long Time · 42m");
  });

  it("formats movie progress only", () => {
    expect(
      formatNowPlayingLine({
        ...base,
        title: "Interstellar",
        subtitle: "2014",
        progress: "1h 18m",
        artwork_url: null,
      }),
    ).toBe("2014 · 1h 18m");
  });

  it("handles missing artwork and paused", () => {
    const line = formatNowPlayingLine({
      ...base,
      subtitle: null,
      progress: "12m",
      paused: true,
      artwork_url: null,
    });
    expect(line).toBe("Paused · 12m");
  });

  it("detects now playing section presence", () => {
    expect(hasNowPlayingSection(null)).toBe(false);
    expect(hasNowPlayingSection(undefined)).toBe(false);
    expect(hasNowPlayingSection([])).toBe(true);
    expect(hasNowPlayingSection([base])).toBe(true);
  });
});
