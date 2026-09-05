"use client";

import Link from "next/link";
import { Activity, Calculator, ChartNoAxesCombined } from "lucide-react";

import { LanguageSwitcher } from "@/components/language-switcher";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/i18n/locale-provider";

export function SiteHeader() {
  const { dictionary: t } = useLocale();
  const navigation = [
    { href: "/", label: t.header.dashboard, icon: Activity },
    { href: "/tools/leverage", label: t.header.leverage, icon: Calculator },
    {
      href: "/tools/profit-ratio",
      label: t.header.profitRatio,
      icon: ChartNoAxesCombined,
    },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.07] bg-background/85 backdrop-blur-xl">
      <div className="h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent opacity-70" />
      <div className="mx-auto flex min-h-16 w-full max-w-[90rem] items-center justify-between gap-4 px-4 sm:px-6 lg:px-10">
        <Link
          href="/"
          className="group flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t.header.dashboardAria}
        >
          <span className="grid size-9 place-items-center rounded-xl border border-primary/25 bg-primary/10 text-primary shadow-[0_0_24px_color-mix(in_oklab,var(--primary)_16%,transparent)]">
            <ChartNoAxesCombined className="size-5" aria-hidden="true" />
          </span>
          <span className="hidden text-lg font-semibold tracking-[-0.03em] sm:inline">
            TraFriend
          </span>
        </Link>

        <nav className="flex items-center gap-1" aria-label={t.header.primaryNavigationAria}>
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Icon className="size-4" aria-hidden="true" />
              <span className={href === "/" ? "hidden sm:inline" : "hidden md:inline"}>
                {label}
              </span>
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="hidden border-amber-300/20 bg-amber-300/[0.06] font-mono text-xs text-amber-200 lg:inline-flex"
          >
            {t.common.mockData}
          </Badge>
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  );
}
