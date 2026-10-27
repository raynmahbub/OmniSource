import PageHeader from "@/components/PageHeader";
import { getLangDict } from "@/lib/lang";

export default async function AboutPage() {
  const { dict } = await getLangDict();
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title={dict.sections.aboutTitle} />
      <div className="os-panel prose-omni space-y-4 p-6 text-[15px] text-zinc-700 dark:text-zinc-300">
        <p>
          <strong>OmniSource</strong> curates an app catalog for AltStore, SideStore, Feather, ESign and
          LiveContainer. Automated jobs track releases, check metadata and probe links; maintainers review the catalog
          and any suggested repairs.
        </p>
        <p>
          Listings identify official, community or unknown sources where known. A recorded hash is not the same as
          a byte comparison or independent publisher verification. Automated checks and past link probes do not
          guarantee a binary is safe or currently available.
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
