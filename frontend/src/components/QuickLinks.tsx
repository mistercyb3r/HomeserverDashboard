import type { QuickLink } from "../types";

interface QuickLinksProps {
  links: QuickLink[];
}

export function QuickLinks({ links }: QuickLinksProps) {
  if (!links.length) return null;

  return (
    <section className="px-4 sm:px-6 lg:px-8">
      <div className="mb-3">
        <h2 className="text-sm font-semibold tracking-tight text-ink">Quick links</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {links.map((link) => (
          <a
            key={`${link.id}:${link.url}`}
            href={link.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-border/70 bg-surface/55 px-3 py-2 text-sm text-ink transition hover:border-border hover:bg-surface"
          >
            {link.label}
          </a>
        ))}
      </div>
    </section>
  );
}
