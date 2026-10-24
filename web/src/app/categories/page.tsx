import Link from "next/link";
import PageHeader from "@/components/PageHeader";
import { getCategories } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

export default async function CategoriesPage() {
  const { dict } = await getLangDict();
  const categories = getCategories();
  const max = Math.max(1, ...categories.map((c) => c.count));
  return (
    <div className="space-y-6">
      <PageHeader title={dict.sections.categoriesTitle} description={dict.sections.categoriesSubtitle} />
      <div className="grid gap-3 sm:grid-cols-2">
        {categories.map((c) => (
          <Link
            key={c.name}
            href={`/apps?category=${encodeURIComponent(c.name)}`}
            className="os-card block p-4"
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
