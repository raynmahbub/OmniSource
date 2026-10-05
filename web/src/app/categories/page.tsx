import Link from "next/link";
import { getCategories } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

export default async function CategoriesPage() {
  const { dict } = await getLangDict();
  const categories = getCategories();
  const max = Math.max(1, ...categories.map((c) => c.count));
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold">{dict.sections.categoriesTitle}</h1>
        <p className="text-zinc-600 dark:text-zinc-400">{dict.sections.categoriesSubtitle}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {categories.map((c) => (
          <Link
            key={c.name}
            href={`/apps?category=${encodeURIComponent(c.name)}`}
            className="rounded-2xl border border-zinc-200 bg-white p-4 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="flex items-center justify-between">
              <span className="font-bold">{c.name}</span>
              <span className="text-sm text-zinc-500">
                {c.count} {dict.common.apps}
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div className="h-full rounded-full bg-gradient-to-r from-indigo-600 via-violet-500 to-purple-400" style={{ width: `${(c.count / max) * 100}%` }} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
