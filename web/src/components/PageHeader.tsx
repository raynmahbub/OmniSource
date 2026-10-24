import type { ReactNode } from "react";

/** Shared page introduction: one typographic rhythm on every catalog surface. */
export default function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="os-page-header">
      <div className="min-w-0">
        {eyebrow && <p className="os-eyebrow">{eyebrow}</p>}
        <h1 className="os-page-title">{title}</h1>
        {description && <p className="os-page-description">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
