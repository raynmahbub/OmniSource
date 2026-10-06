"use client";

import { useState } from "react";
import { safeExternalUrl } from "@/lib/url";

interface ScreenshotGalleryProps {
  appName: string;
  urls: string[];
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
  url,
  index,
  screenshotLabel,
  unavailableLabel,
}: {
  appName: string;
  url: string;
  index: number;
  screenshotLabel: string;
  unavailableLabel: string;
}) {
  const [failed, setFailed] = useState(false);
  const label = `${screenshotLabel} ${index + 1}`;

  return (
    <li className="w-[min(75vw,250px)] shrink-0 snap-start">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="group block rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-violet-600"
        aria-label={`${appName} — ${label}; open original image`}
      >
        <span className="grid h-[360px] w-full place-items-center overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-100 p-2 transition-colors group-hover:border-violet-300 dark:border-zinc-800 dark:bg-zinc-900 dark:group-hover:border-violet-700">
          {failed ? (
            <span className="px-5 text-center text-sm text-zinc-500">{unavailableLabel}</span>
          ) : (
            // These are the original screenshot URLs declared by the app's
            // official project source; we never synthesize or substitute art.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={url}
              alt={`${appName} interface — ${label}`}
              width={250}
              height={360}
              loading="lazy"
              decoding="async"
              onError={() => setFailed(true)}
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
  urls,
  projectURL,
  title,
  description,
  emptyMessage,
  unavailableLabel,
  screenshotLabel,
  officialProjectLabel,
}: ScreenshotGalleryProps) {
  // Do not allow feed data to turn into a javascript:, data: or same-origin
  // mockup URL. Catalog validation additionally checks upstream ownership.
  const screenshots = Array.from(
    new Set(
      urls
        .map((value) => safeExternalUrl(value))
        .filter((value): value is string => Boolean(value && /^https?:\/\//i.test(value))),
    ),
  );
  const officialProject = safeExternalUrl(projectURL);

  return (
    <section
      aria-labelledby="official-screenshots-title"
      className="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900 sm:p-6"
    >
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
            className="inline-flex min-h-10 shrink-0 items-center rounded-xl border border-zinc-300 px-3 text-sm font-semibold transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 dark:border-zinc-700 dark:hover:border-violet-700 dark:hover:bg-violet-950 dark:hover:text-violet-200"
          >
            {officialProjectLabel} <span className="ml-1" aria-hidden="true">↗</span>
          </a>
        )}
      </div>

      {screenshots.length ? (
        <ul className="mt-5 flex snap-x snap-mandatory gap-4 overflow-x-auto overscroll-x-contain pb-3">
          {screenshots.map((url, index) => (
            <ScreenshotTile
              key={url}
              appName={appName}
              url={url}
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
