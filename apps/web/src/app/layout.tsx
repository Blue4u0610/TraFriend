import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { LocaleProvider } from "@/i18n/locale-provider";
import { getDictionary, getLocale } from "@/i18n/server";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const { metadata } = await getDictionary();
  return {
    title: {
      default: metadata.defaultTitle,
      template: metadata.titleTemplate,
    },
    description: metadata.description,
  };
}

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const locale = await getLocale();

  return (
    <html lang={locale} className={`dark ${geistSans.variable} ${geistMono.variable}`}>
      <body className="min-h-screen">
        <LocaleProvider initialLocale={locale}>
          <div className="flex min-h-screen flex-col">
            <SiteHeader />
            <main className="mx-auto flex w-full max-w-[90rem] flex-1 flex-col px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
              {children}
            </main>
            <SiteFooter />
          </div>
        </LocaleProvider>
      </body>
    </html>
  );
}
