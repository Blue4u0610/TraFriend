"use client";

import { useLocale } from "@/i18n/locale-provider";

export function SiteFooter() {
  const { dictionary: t } = useLocale();

  return (
    <footer className="border-t border-white/[0.07]">
      <div className="mx-auto flex w-full max-w-[90rem] flex-col gap-2 px-4 pb-20 pt-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:pb-6 sm:pr-44 lg:px-10 lg:pr-48">
        <p>{t.footer.product}</p>
        <p>{t.footer.disclosure}</p>
      </div>
    </footer>
  );
}
