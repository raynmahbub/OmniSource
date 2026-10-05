import { getLangDict } from "@/lib/lang";

export default async function AboutPage() {
  const { dict } = await getLangDict();
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-extrabold">{dict.sections.aboutTitle}</h1>
      <div className="prose-omni space-y-4 rounded-3xl border border-zinc-200 bg-white p-6 text-[15px] text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
        <p>
          <strong>OmniSource</strong> is a fully autonomous AltStore, SideStore, Feather, ESign and LiveContainer
          source aggregation platform. It discovers third-party feeds, validates every app, tracks releases,
          scores reputations, monitors health around the clock — and publishes installable feeds with no human
          in the loop.
        </p>
        <p>
          Every release resolves from the developer&apos;s own upstream. Metadata-only aggregation: each entry
          discloses provenance and hashes, and the security gate blocks publication on critical findings.
        </p>
        <h2 className="pt-2 text-lg font-bold text-zinc-900 dark:text-zinc-100">Pipeline</h2>
        <p className="font-mono text-sm">
          Discovery → Validation → Deduplication → Enrichment → Reputation → Feed Generation → Website Build →
          Publish
        </p>
        <h2 className="pt-2 text-lg font-bold text-zinc-900 dark:text-zinc-100">Clients</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">feeds/apps.json</code> — unified AltStore v2
            feed
          </li>
          <li>
            <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">feeds/clients/&lt;client&gt;.json</code> —
            per-client variants (altstore, sidestore, feather, esign, livecontainer)
          </li>
          <li>
            <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">/api/v3/*</code> — paginated REST API with
            ETag + cache control
          </li>
        </ul>
        <p>
          Source code:{" "}
          <a href="https://github.com/raynmahbub/OmniSource" className="font-semibold text-violet-700 hover:underline dark:text-violet-300">
            github.com/raynmahbub/OmniSource
          </a>
        </p>
      </div>
    </div>
  );
}
