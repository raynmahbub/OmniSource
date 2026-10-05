import type { Metadata, Viewport } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import PwaRegister from "@/components/PwaRegister";
import { getApps, getGeneratedAt, getSources } from "@/lib/data";
import { getLangDict, isRtl } from "@/lib/lang";

// Canonical origin for absolutised metadata. Deployments can override it with
// NEXT_PUBLIC_SITE_URL; the default matches where the catalog is published.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://raynmahbub.github.io/OmniSource";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "OmniSource — verified source catalog", template: "%s · OmniSource" },
  description:
    "One feed for AltStore, SideStore, Feather, ESign and LiveContainer. Every app validated, every release resolved from its official upstream.",
  applicationName: "OmniSource",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "OmniSource", statusBarStyle: "default" },
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: "OmniSource",
    title: "OmniSource — verified source catalog",
    description: "One feed for AltStore, SideStore, Feather, ESign and LiveContainer.",
    url: "/",
    images: [{ url: "/icon.svg", width: 512, height: 512, alt: "OmniSource" }],
  },
  twitter: {
    card: "summary",
    title: "OmniSource — verified source catalog",
    description: "One feed for AltStore, SideStore, Feather, ESign and LiveContainer.",
    images: ["/icon.svg"],
  },
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6fd" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { lang, dict } = await getLangDict();
  const apps = getApps().length;
  const sources = getSources().length;
  const synced = getGeneratedAt();
  return (
    <html lang={lang} dir={isRtl(lang) ? "rtl" : "ltr"}>
      <head>
        {/* Same type family as the static site: Inter for text, JetBrains
            Mono for feed URLs and identifiers. System stacks stay behind
            them in globals.css for offline PWAs. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- this is the
            App Router root layout, so the sheet loads once for every page; the
            rule describes the Pages Router's per-page <Head>. A plain <link>
            keeps `next build` working without network access to Google Fonts,
            which next/font/google would require at build time. */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap"
        />
      </head>
      <body className="min-h-screen bg-[#f7f6fd] text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100">
        <PwaRegister lang={lang} />
        <Nav dict={dict} lang={lang} />
        <main id="main" className="mx-auto w-full max-w-6xl px-4 py-8">
          {children}
        </main>
        <footer className="relative border-t border-zinc-200 py-8 text-center text-sm text-zinc-500 before:pointer-events-none before:absolute before:inset-x-0 before:-top-px before:h-px before:bg-gradient-to-r before:from-transparent before:via-violet-500/60 before:to-transparent dark:border-zinc-800 dark:text-zinc-400">
          <p>
            OmniSource · {apps} {dict.common.apps} · {sources} {dict.common.sources}
            {synced && (
              <>
                {" "}
                · {dict.common.lastSync} {synced.slice(0, 10)}
              </>
            )}
          </p>
          <p className="mt-3">
            <a
              href="https://github.com/raynmahbub"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white/70 px-3 py-1 text-xs text-zinc-600 transition-colors hover:border-violet-300 hover:text-zinc-900 dark:border-zinc-800 dark:bg-zinc-900/70 dark:text-zinc-300 dark:hover:border-violet-700 dark:hover:text-white"
            >
              <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4 fill-current">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
              </svg>
              Maintained by <strong className="font-semibold text-violet-700 dark:text-violet-300">@raynmahbub</strong>
            </a>
          </p>
        </footer>
      </body>
    </html>
  );
}
