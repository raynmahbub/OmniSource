import type { ReactNode } from "react";

export default function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="os-empty-state" role="status">
      <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4M8.5 11h5" />
      </svg>
      <p>{children}</p>
    </div>
  );
}
