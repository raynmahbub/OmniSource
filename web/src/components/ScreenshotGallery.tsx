"use client";

import { useState } from "react";
import { safeExternalUrl } from "@/lib/url";

interface ScreenshotItem {
  url: string;
  originalURL: string;
  thumbnailURL?: string;
}

interface ScreenshotGalleryProps {
  appName: string;
  screenshots: ScreenshotItem[];
  projectURL?: string;
  title: string;
  description: string;
  emptyMessage: string;
  unavailableLabel: string;
  screenshotLabel: string;
  officialProjectLabel: string;
}

function ScreenshotTile({
  appName,
  item,
  index,
  screenshotLabel,
  unavailableLabel,
}: {
  appName: string;
  item: ScreenshotItem;
  index: number;
  screenshotLabel: string;
  unavailableLabel: string;
}) {
  const candidates = Array.from(
    new Set([item.thumbnailURL, item.url, item.originalURL].filter((value): value is string => Boolean(value))),
  );
  const [attempt, setAttempt] = useState(0);
  const failed = attempt >= candidates.length;
  const label = `${screenshotLabel} ${index + 1}`;

  return (
    <li className="w-[min(75vw,250px)] shrink-0 snap-start">
      <a
        href={item.originalURL}
        target="_blank"
        rel="noopener noreferrer"
        className="group block rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-violet-600"
        aria-label={`${appName} — ${label}`}
      >
        <span className="grid h-[360px] w-full place-items-center overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-100 p-2 transition-colors group-hover:border-violet-300 dark:border-zinc-800 dark:bg-zinc-950 dark:group-hover:border-violet-700">
          {failed ? (
            <span className="px-5 text-center text-sm text-zinc-500">{unavailableLabel}</span>
          ) : (
            // Prefer the pipeline's same-origin WebP, then its full mirror,
            // then the original project image. No substitute art is invented.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={candidates[attempt]}
              alt={`${appName} — ${label}`}
              width={250}
              height={360}
              loading="lazy"
              decoding="async"
              onError={() => setAttempt((current) => current + 1)}
              className="h-full w-full rounded-xl object-contain"
            />
          )}
        </span>
        <span className="mt-2 block text-sm font-medium text-zinc-600 group-hover:text-violet-700 dark:text-zinc-400 dark:group-hover:text-violet-300">
          {label} <span aria-hidden="true">↗</span>
        </span>
      </a>
    </li>
  );
}

/** Displays only upstream-declared screenshots, with an explicit honest gap. */
export default function ScreenshotGallery({
  appName,
  screenshots,
  projectURL,
  title,
  description,
  emptyMessage,
  unavailableLabel,
  screenshotLabel,
  officialProjectLabel,
}: ScreenshotGalleryProps) {
  // Feed data cannot introduce a javascript:, data: or same-origin mockup URL.
  // Local mirrors are generated only from the root pipeline's validated manifest.
  const items = Array.from(
    new Map(
      screenshots.flatMap((item) => {
        const originalURL = safeExternalUrl(item.originalURL);
        if (!originalURL || !/^https?:\/\//i.test(originalURL)) return [];
        const url = safeExternalUrl(item.url) ?? originalURL;
        const thumbnailURL = safeExternalUrl(item.thumbnailURL);
        return [
          [
            originalURL,
            { originalURL, url, ...(thumbnailURL ? { thumbnailURL } : {}) } satisfies ScreenshotItem,
          ] as const,
        ];
      }),
    ).values(),
  );
  const officialProject = safeExternalUrl(projectURL);

  return (
    <section aria-labelledby="official-screenshots-title" className="os-panel p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="official-screenshots-title" className="text-lg font-bold">
            {title}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
        </div>
        {officialProject && (
          <a
            href={officialProject}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-10 shrink-0 items-center rounded-xl border border-zinc-300 px-3 text-sm font-semibold transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-800 dark:border-zinc-700 dark:hover:border-violet-700 dark:hover:bg-violet-950 dark:hover:text-violet-200"
          >
            {officialProjectLabel} <span className="ml-1" aria-hidden="true">↗</span>
          </a>
        )}
      </div>

      {items.length ? (
        <ul
          tabIndex={0}
          aria-label={`${appName} — ${title}`}
          className="mt-5 flex snap-x snap-mandatory gap-4 overflow-x-auto overscroll-x-contain pb-3 focus-visible:rounded-2xl"
        >
          {items.map((item, index) => (
            <ScreenshotTile
              key={item.originalURL}
              appName={appName}
              item={item}
              index={index}
              screenshotLabel={screenshotLabel}
              unavailableLabel={unavailableLabel}
            />
          ))}
        </ul>
      ) : (
        <p className="mt-5 rounded-xl border border-dashed border-zinc-300 bg-zinc-50 px-4 py-5 text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-400">
          {emptyMessage}
        </p>
      )}
    </section>
  );
}
