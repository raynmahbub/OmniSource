import Link from "next/link";
import AppIcon from "./AppIcon";
import { getCatalogIconURL, type AltApp } from "@/lib/data";

/** One catalog card with reserved media, aligned metadata and a clear target. */
export default function AppCard({ id, app }: { id: string; app: AltApp }) {
  return (
    <Link href={`/apps/${encodeURIComponent(id)}`} className="os-card group flex min-w-0 items-center gap-3 p-3.5">
      <AppIcon app={app} src={getCatalogIconURL(app)} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold tracking-[-0.01em] text-zinc-900 dark:text-zinc-100">
          {app.name}
        </span>
        <span className="mt-0.5 block truncate text-sm text-zinc-500 dark:text-zinc-400">
          {app.developerName} · v{app.version ?? "?"}
        </span>
        <span className="mt-2 inline-block max-w-full truncate rounded-full bg-zinc-100/90 px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {app.category ?? "Utilities"}
        </span>
      </span>
      <span
        aria-hidden
        className="self-start text-lg text-zinc-300 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-violet-500 motion-reduce:transition-none dark:text-zinc-600"
      >
        ↗
      </span>
    </Link>
  );
}
