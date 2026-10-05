"use client";

import { useState } from "react";
import type { AltApp } from "@/lib/data";
import { safeExternalUrl } from "@/lib/url";

export function tint(app: AltApp): string {
  const raw = (app.tintColor ?? "FF0000").replace("#", "");
  return /^[0-9A-Fa-f]{6}$/.test(raw) ? `#${raw}` : "#FF0000";
}

/**
 * App icon with a reserved box and a graceful failure path.
 *
 * The frame is fixed (`size`), so a slow or missing icon can never reflow the
 * card; `loading="lazy"` + `decoding="async"` keep a long grid cheap. Catalog
 * pages pass the same-origin copy of the reviewed upstream icon, while the
 * machine-readable feed keeps its canonical absolute URL. If the local copy
 * fails, the canonical catalog URL is retried; if both fail, a neutral error
 * glyph is shown rather than a made-up app logo. Feed URLs are validated.
 */
export default function AppIcon({
  app,
  src: sourceOverride,
  size = 56,
  className = "",
}: {
  app: AltApp;
  /** Same-origin catalog copy for website cards; feed/API URLs stay canonical. */
  src?: string;
  size?: number;
  className?: string;
}) {
  const localSrc = safeExternalUrl(sourceOverride);
  const canonicalSrc = safeExternalUrl(app.iconURL);
  const firstSrc = localSrc ?? canonicalSrc;
  const [usingCanonical, setUsingCanonical] = useState(!localSrc && Boolean(canonicalSrc));
  const [failed, setFailed] = useState(!firstSrc);
  const src = usingCanonical ? canonicalSrc : firstSrc;
  const style = { background: tint(app), width: size, height: size };

  if (failed || !src) {
    return (
      <span
        role="img"
        aria-label={`${app.name} logo unavailable`}
        className={`flex shrink-0 items-center justify-center rounded-xl bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500 ${className}`}
        style={{ width: size, height: size }}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-1/2 w-1/2" fill="none" stroke="currentColor" strokeWidth="1.7">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <circle cx="8.5" cy="9" r="1.5" />
          <path d="m21 15-5-5L5 20" />
        </svg>
      </span>
    );
  }
  return (
    // Icons are arbitrary third-party URLs, so next/image optimisation is off
    // (see next.config.ts) and the dimensions are reserved by the fixed box.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => {
        if (!usingCanonical && canonicalSrc && canonicalSrc !== src) {
          setUsingCanonical(true);
          return;
        }
        setFailed(true);
      }}
      className={`shrink-0 rounded-xl object-contain ${className}`}
      style={style}
    />
  );
}
