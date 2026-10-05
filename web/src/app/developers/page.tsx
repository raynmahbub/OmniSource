import Link from "next/link";
import { getAppsWithIds, getDevelopers } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

export default async function DevelopersPage() {
  const { dict } = await getLangDict();
  const developers = getDevelopers();
  const apps = getAppsWithIds();
  const byDeveloper = new Map<string, Array<{ id: string; name: string }>>();
  for (const { id, app } of apps) {
    const name = app.developerName?.trim() || "Unknown developer";
    const list = byDeveloper.get(name) ?? [];
    list.push({ id, name: app.name });
    byDeveloper.set(name, list);
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-extrabold">{dict.nav.developers ?? "Developers"}</h1>
        <p className="mt-1 text-zinc-600 dark:text-zinc-400">
          Publishers represented in the validated catalog, with source-backed app records.
        </p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {developers.map((developer) => (
          <article key={developer.name} className="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="font-bold">{developer.name}</h2>
            <p className="mt-1 text-sm text-zinc-500">
              {developer.appCount} {dict.common.apps} · {developer.sourceCount} {dict.common.sources}
            </p>
            <ul className="mt-3 space-y-1 text-sm">
              {(byDeveloper.get(developer.name) ?? []).slice(0, 8).map((app) => (
                <li key={app.id}>
                  <Link className="text-violet-700 hover:underline dark:text-violet-300" href={`/apps/${encodeURIComponent(app.id)}`}>
                    {app.name}
                  </Link>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      {!developers.length && <p className="text-zinc-500">{dict.common.noResults}</p>}
    </div>
  );
}
