import { useState } from "react";
import type { PlaybackSession } from "../types";
import { formatNowPlayingLine, nowPlayingEmptyLabel } from "../lib/jellyfinNowPlaying";

interface JellyfinNowPlayingProps {
  sessions: PlaybackSession[];
}

function Poster({ session }: { session: PlaybackSession }) {
  const [failed, setFailed] = useState(false);
  if (!session.artwork_url || failed) {
    return (
      <div
        className="flex h-10 w-7 shrink-0 items-center justify-center rounded bg-surface-2 text-[9px] text-faint"
        aria-hidden
      >
        ▶
      </div>
    );
  }
  return (
    <img
      src={session.artwork_url}
      alt=""
      className="h-10 w-7 shrink-0 rounded object-cover"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export function JellyfinNowPlaying({ sessions }: JellyfinNowPlayingProps) {
  if (sessions.length === 0) {
    return <p className="text-[13px] text-faint">{nowPlayingEmptyLabel()}</p>;
  }

  return (
    <ul className="space-y-2.5">
      {sessions.map((session) => {
        const line = formatNowPlayingLine(session);
        return (
          <li key={session.id} className="flex gap-2.5">
            <Poster session={session} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-ink">{session.user}</p>
              <p className="truncate text-[13px] text-ink/85">{session.title}</p>
              {line ? <p className="truncate text-xs text-faint">{line}</p> : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
