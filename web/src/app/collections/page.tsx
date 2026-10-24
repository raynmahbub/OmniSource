import AppCard from "@/components/AppCard";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { getAppsWithIds, getCollections } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

export default async function CollectionsPage() {
  const { dict } = await getLangDict();
  const collections = getCollections();
  const entries = getAppsWithIds();
  const byId = new Map(entries.map((e) => [e.id, e]));
  const byBundle = new Map(entries.map((e) => [e.app.bundleIdentifier, e]));
  return (
    <div className="space-y-8">
      <PageHeader title={dict.sections.collectionsTitle} description={dict.sections.collectionsSubtitle} />
      {collections.map((c) => {
        const members = (c.appSlugs ?? [])
          .map((slug) => byId.get(slug) ?? byBundle.get(slug))
          .filter((e): e is { id: string; app: (typeof entries)[number]["app"] } => Boolean(e))
          .slice(0, 12);
        return (
          <section key={c.slug} className="os-panel p-5 sm:p-6">
            <h2 className="text-lg font-bold">{c.title}</h2>
            {c.description && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{c.description}</p>}
            <p className="mt-1 text-xs text-zinc-500">
              {c.appCount ?? members.length} {dict.common.apps}
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {members.map(({ id, app }) => (
                <AppCard key={id} id={id} app={app} />
              ))}
            </div>
          </section>
        );
      })}
      {!collections.length && <EmptyState>{dict.common.noResults}</EmptyState>}
    </div>
  );
}
