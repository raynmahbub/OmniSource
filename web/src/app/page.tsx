import Link from "next/link";
import AppCard from "@/components/AppCard";
import SearchBox from "@/components/SearchBox";
import { getAppsWithIds, getSources, getStatus } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

const SOURCE_URL = "https://raynmahbub.github.io/OmniSource/apps.json";

const CLIENTS = [
  { name: "AltStore", href: `altstore://source?url=${SOURCE_URL}` },
  { name: "SideStore", href: `sidestore://source?url=${SOURCE_URL}` },
  { name: "FlareStore", href: `flarestore://source?url=${SOURCE_URL}` },
  { name: "Feather", href: "feather://source/raynmahbub.github.io/OmniSource/apps.json" },
  { name: "ESign", href: `esign://addsource?url=${SOURCE_URL}` },
  { name: "Ksign", href: `ksign://addsource?url=${SOURCE_URL}` },
  { name: "LiveContainer", href: `livecontainer://sources?url=${SOURCE_URL}` },
];

export default async function Home() {
  const { dict } = await getLangDict();
  const apps = getAppsWithIds().slice(0, 8);
  const total = getAppsWithIds().length;
  const sources = getSources().length;
  const status = getStatus() as { pipeline?: { status?: string } };
  const pipeline = String(status.pipeline?.status ?? "unknown");

  return (
    <div className="space-y-10">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-700 via-violet-600 to-purple-500 p-8 text-white shadow-[0_24px_80px_-24px_rgba(91,61,245,0.6)] md:p-12">
        {/* Aurora: two soft orbs and a chrome hairline, the same materials as
            the static site's Liquid Glass hero. Purely decorative. */}
        <div aria-hidden className="pointer-events-none absolute -right-24 -top-32 h-80 w-80 rounded-full bg-fuchsia-300/30 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-40 -left-20 h-96 w-96 rounded-full bg-indigo-300/25 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-white/70 to-transparent" />

        <div className="relative">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-white/90 backdrop-blur">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_10px_rgba(110,231,183,0.9)]" />
            {total} {dict.common.apps} · {sources} {dict.common.sources}
          </p>
          <h1 className="mt-4 max-w-2xl text-3xl font-extrabold tracking-tight md:text-5xl md:leading-[1.05]">
            {dict.home.tagline}
          </h1>
          <div className="mt-6">
            <SearchBox placeholder={dict.sections.searchPlaceholder} submitLabel={dict.nav.search ?? "Search"} />
          </div>

          {/* The one line that matters: the installable source URL. */}
          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl border border-white/20 bg-black/15 p-3 pl-4 backdrop-blur">
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-white/70">Source</span>
            <code className="min-w-0 flex-1 truncate font-mono text-sm text-white">{SOURCE_URL}</code>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {CLIENTS.map((c) => (
              <a
                key={c.name}
                href={c.href}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/15 px-4 py-1.5 text-sm font-semibold shadow-[inset_0_1px_0_rgba(255,255,255,0.35)] backdrop-blur transition-colors hover:bg-white/25"
              >
                <svg aria-hidden viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                {c.name}
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          { t: dict.home.why1t, d: dict.home.why1d },
          { t: dict.home.why2t, d: dict.home.why2d },
          { t: dict.home.why3t, d: dict.home.why3d },
        ].map((f) => (
          <div
            key={f.t}
            className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-violet-300 hover:shadow-[0_18px_48px_-20px_rgba(106,76,240,0.45)] motion-reduce:transition-none dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-violet-700"
          >
            <span aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-indigo-600 via-violet-500 to-purple-400 opacity-70 transition-opacity group-hover:opacity-100" />
            <h2 className="font-bold">{f.t}</h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{f.d}</p>
          </div>
        ))}
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold">{dict.sections.appsTitle}</h2>
          <Link href="/apps" className="text-sm font-semibold text-violet-700 hover:underline dark:text-violet-300">
            {dict.common.viewAll} →
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {apps.map(({ id, app }) => (
            <AppCard key={id} id={id} app={app} />
          ))}
        </div>
      </section>

      <section className="flex flex-wrap items-center gap-3 rounded-2xl border border-zinc-200 bg-white p-5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
        <span className="font-semibold">{dict.home.liveStatus}:</span>
        <span
          className={`rounded-full px-3 py-1 font-semibold ${
            pipeline === "healthy" || pipeline === "online"
              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
              : "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
          }`}
        >
          {pipeline}
        </span>
        <Link href="/status" className="font-semibold text-violet-700 hover:underline dark:text-violet-300">
          {dict.nav.status} →
        </Link>
      </section>
    </div>
  );
}
