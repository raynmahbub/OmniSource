import Link from "next/link";
import { notFound } from "next/navigation";
import AppIcon from "@/components/AppIcon";
import CopyButton from "@/components/CopyButton";
import ScreenshotGallery from "@/components/ScreenshotGallery";
import {
  getAppById, getAppHealth, getAppProjectURL, getAppScreenshots, getAppVerification,
  getAppsWithIds, getCatalogIconURL, getSingleAppFeedURL,
} from "@/lib/data";
import { getLangDict } from "@/lib/lang";
import { safeExternalUrl } from "@/lib/url";

export function generateStaticParams() {
  return getAppsWithIds().map(({ id }) => ({ id }));
}

export default async function AppDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const app = getAppById(decodeURIComponent(id));
  if (!app) notFound();
  const { dict } = await getLangDict();
  const versions = Array.isArray(app.versions) ? app.versions : [];
  const downloadUrl = safeExternalUrl(app.downloadURL);
  const projectURL = safeExternalUrl(getAppProjectURL(app));
  const screenshots = getAppScreenshots(app);
  const sourceFeed = safeExternalUrl(getSingleAppFeedURL(app));
  const verification = getAppVerification(app);
  const provenance = verification?.provenance ?? "unknown";
  const sourceLabel = provenance === "official" ? "Official source" : provenance === "community" ? "Community source" : "Source unknown";
  const health = getAppHealth(app);
  const healthLabel = health.reachable === true ? "Last seen reachable" : health.reachable === false ? "Last probe failed" : "Not checked for this download";
  const compatibility = app.omnisource?.compatibility;
  const newest = versions[0] ?? {};
  const minOS = compatibility?.minOSVersion || app.minOSVersion || newest.minOSVersion;
  const maxOS = compatibility?.maxOSVersion || app.maxOSVersion || newest.maxOSVersion;
  const digest = typeof newest.sha256 === "string" ? newest.sha256 : app.sha256;
  const digestStatus = verification?.digestEvidence?.status;
  const collisions = getAppsWithIds().filter((entry) => entry.app !== app && entry.app.bundleIdentifier === app.bundleIdentifier);
  return (
    <div className="space-y-6">
      <Link href="/apps" className="text-sm font-semibold text-violet-700 hover:underline dark:text-violet-300">
        ← {dict.sections.appsTitle}
      </Link>
      <div className="os-panel flex flex-col gap-5 p-6 md:flex-row">
        <AppIcon app={app} src={getCatalogIconURL(app)} size={112} className="rounded-3xl text-4xl" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-extrabold">{app.name}</h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            {app.developerName} · {app.bundleIdentifier}
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-sm">
            <span className="rounded-full bg-zinc-100 px-3 py-1 dark:bg-zinc-800">
              {dict.common.version} {app.version} · {app.versionDate}
            </span>
            <span className="rounded-full bg-zinc-100 px-3 py-1 dark:bg-zinc-800">{app.category}</span>
            <span className="rounded-full bg-violet-50 px-3 py-1 text-violet-800 dark:bg-violet-950 dark:text-violet-200">{sourceLabel}</span>
            <span className="rounded-full bg-zinc-100 px-3 py-1 dark:bg-zinc-800">{healthLabel}</span>
            {typeof app.size === "number" && app.size > 0 && (
              <span className="rounded-full bg-zinc-100 px-3 py-1 dark:bg-zinc-800">
                {(app.size / 1048576).toFixed(1)} MB
              </span>
            )}
          </div>
          {typeof app.size === "number" && app.size >= 200 * 1024 * 1024 && <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">Large download; consider Wi-Fi or your data limits.</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            {downloadUrl && (
              <a
                href={downloadUrl}
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center rounded-xl bg-violet-600 px-5 font-semibold text-white transition-colors hover:bg-violet-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600"
              >
                ⬇ {dict.common.download} (.ipa)
              </a>
            )}
            {sourceFeed && (
              <a
                href={sourceFeed}
                className="inline-flex min-h-11 items-center rounded-xl border border-zinc-300 px-5 font-semibold transition-colors hover:bg-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                {dict.home.addSource}
              </a>
            )}
            {sourceFeed && (
              <CopyButton
                value={sourceFeed}
                label={dict.common.copyUrl ?? "Copy source URL"}
                copiedLabel={dict.common.copied ?? "Copied"}
                failedLabel={dict.common.copyFailed ?? "Copy blocked — press and hold to copy"}
              />
            )}
            {projectURL && (
              <a
                href={projectURL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center rounded-xl border border-zinc-300 px-4 font-semibold transition-colors hover:bg-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                {dict.common.officialProject ?? "Official project"} ↗
              </a>
            )}
          </div>
        </div>
      </div>
      <section className="os-panel p-5 sm:p-6" aria-labelledby="install-details">
        <h2 id="install-details" className="text-lg font-bold">Source &amp; installation details</h2>
        {verification?.integrityFailure && <p className="mt-3 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100">Integrity mismatch detected; review before installation. {verification.integrityFailure.detail}</p>}
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <div><dt className="font-semibold">Source attribution</dt><dd className="mt-1 text-zinc-600 dark:text-zinc-400">{sourceLabel} · Catalog attribution, not a safety guarantee.</dd></div>
          <div><dt className="font-semibold">Download check</dt><dd className="mt-1 text-zinc-600 dark:text-zinc-400">{healthLabel}{health.checkedAt ? ` · ${health.checkedAt}` : ""}. A past probe does not guarantee availability now.</dd></div>
          <div><dt className="font-semibold">iOS compatibility</dt><dd className="mt-1 text-zinc-600 dark:text-zinc-400">{minOS ? `iOS ${String(minOS)}${maxOS ? `–${String(maxOS)}` : "+"}` : "Minimum version not recorded"}{compatibility?.devices?.length ? ` · ${compatibility.devices.join(", ")}` : ""}</dd></div>
          <div><dt className="font-semibold">Declared clients</dt><dd className="mt-1 text-zinc-600 dark:text-zinc-400">{compatibility?.clients?.length ? compatibility.clients.join(", ") : "Not recorded"}</dd></div>
          <div className="min-w-0 sm:col-span-2"><dt className="font-semibold">Recorded SHA-256</dt><dd className="mt-1 break-all font-mono text-xs text-zinc-600 dark:text-zinc-400">{digest || "Not recorded"}</dd><dd className="mt-1 text-zinc-600 dark:text-zinc-400">{digestStatus === "mismatch" ? "Downloaded bytes did not match the recorded digest." : digestStatus === "matched" ? "Downloaded bytes matched the recorded digest." : digest ? "Digest recorded; a byte comparison has not been established." : "No digest available."} A digest alone does not establish publisher identity or safety.</dd></div>
        </dl>
        {compatibility?.notes && <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">{compatibility.notes}</p>}
      </section>
      {collisions.length > 0 && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100" aria-labelledby="bundle-collision">
          <h2 id="bundle-collision" className="font-bold">Shared bundle identifier</h2>
          <p className="mt-2">This catalog identifier is also used by {collisions.map(({ id: otherId, app: other }, i) => (
            <span key={otherId}>{i > 0 ? ", " : ""}<Link href={`/apps/${encodeURIComponent(otherId)}`} className="font-semibold underline">{other.name}</Link></span>
          ))}. Apps with the same identifier may conflict or replace one another, depending on signing. Your client may also show only one in the master feed.</p>
          <p className="mt-2">The single-app feed above isolates this listing; it does not change the on-device identifier or guarantee side-by-side installation.</p>
        </section>
      )}
      {app.localizedDescription && (
        <div className="prose-omni rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="whitespace-pre-wrap text-[15px]">{app.localizedDescription}</p>
        </div>
      )}
      <ScreenshotGallery
        appName={app.name}
        screenshots={screenshots}
        projectURL={projectURL}
        title={dict.sections.screenshotsTitle ?? "Official screenshots"}
        description={dict.sections.screenshotsIntro ?? "Original screenshots published by this app's official project."}
        emptyMessage={dict.sections.noScreenshots ?? "No official screenshots are listed for this app yet. We won't substitute mockups or logos."}
        unavailableLabel={dict.sections.screenshotUnavailable ?? "This screenshot could not be loaded."}
        screenshotLabel={dict.sections.screenshotLabel ?? "Screenshot"}
        officialProjectLabel={dict.common.officialProject ?? "Official project"}
      />
      {!!versions.length && (
        <div className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="mb-3 font-bold">
            {dict.common.version}s ({versions.length})
          </h2>
          <ul className="space-y-2 text-sm">
            {versions.slice(0, 10).map((v, i) => {
              const ver = v as Record<string, unknown>;
              return (
                <li key={i} className="flex flex-wrap items-center gap-2 border-b border-zinc-100 pb-2 dark:border-zinc-800">
                  <span className="font-mono font-semibold">{String(ver.version ?? "?")}</span>
                  <span className="text-zinc-500">{String(ver.date ?? "")}</span>
                  {safeExternalUrl(ver.downloadURL) && (
                    <a
                      href={safeExternalUrl(ver.downloadURL)}
                      rel="noopener noreferrer"
                      className="ml-auto font-semibold text-violet-700 hover:underline dark:text-violet-300"
                    >
                      {dict.common.download}
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
