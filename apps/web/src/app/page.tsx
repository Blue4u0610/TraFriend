import Link from "next/link";
import {
  ArrowUpRight,
  Calculator,
  ChartNoAxesCombined,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  ShieldCheck,
} from "lucide-react";

import { ApiStatus } from "@/components/api-status";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { interpolate } from "@/i18n/dictionaries";
import { getDictionary } from "@/i18n/server";
import { cn } from "@/lib/utils";

export default async function DashboardPage() {
  const t = await getDictionary();
  const tools = [
    {
      href: "/tools/leverage",
      ...t.dashboard.tools.leverage,
      icon: Calculator,
      accent: "text-primary",
      detail: "QQQ · TQQQ · SQQQ",
    },
    {
      href: "/tools/profit-ratio",
      ...t.dashboard.tools.profitRatio,
      icon: ChartNoAxesCombined,
      accent: "text-violet-300",
      detail: "NVDA · 7",
    },
  ];

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-5 border-b border-white/[0.07] pb-8 md:flex-row md:items-end md:justify-between">
        <div className="max-w-3xl">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Badge className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/10">
              {t.dashboard.phase}
            </Badge>
            <ApiStatus />
          </div>
          <p className="data-label mb-3">{t.dashboard.eyebrow}</p>
          <h1 className="text-balance text-4xl font-semibold tracking-[-0.055em] sm:text-5xl">
            {t.dashboard.headline}
            <span className="text-muted-foreground">{t.dashboard.headlineMuted}</span>
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
            {t.dashboard.intro}
          </p>
        </div>
        <div className="grid shrink-0 grid-cols-2 gap-2 sm:w-auto">
          <div className="rounded-xl border border-white/[0.08] bg-card/70 px-4 py-3">
            <p className="data-label">{t.dashboard.mode}</p>
            <p className="mt-1 font-mono text-sm text-primary">
              {t.dashboard.modeValue}
            </p>
          </div>
          <div className="rounded-xl border border-white/[0.08] bg-card/70 px-4 py-3">
            <p className="data-label">{t.dashboard.storage}</p>
            <p className="mt-1 font-mono text-sm">{t.dashboard.storageValue}</p>
          </div>
        </div>
      </section>

      <section aria-labelledby="toolkit-heading">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="data-label">{t.dashboard.availableNow}</p>
            <h2 id="toolkit-heading" className="mt-1 text-2xl font-semibold tracking-tight">
              {t.dashboard.toolkit}
            </h2>
          </div>
          <span className="hidden font-mono text-xs text-muted-foreground sm:block">
            {t.dashboard.toolsOnline}
          </span>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {tools.map(({ href, eyebrow, title, description, icon: Icon, accent, detail }) => (
            <Card
              key={href}
              className="surface-glow group border-white/[0.08] bg-card/80 py-0 transition-colors hover:border-primary/25"
            >
              <CardHeader className="gap-5 p-6 sm:p-7">
                <div className="flex items-start justify-between gap-4">
                  <span
                    className={`grid size-11 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.035] ${accent}`}
                  >
                    <Icon className="size-5" aria-hidden="true" />
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{detail}</span>
                </div>
                <div>
                  <CardDescription className="data-label mb-2">{eyebrow}</CardDescription>
                  <CardTitle className="text-2xl tracking-[-0.035em]">{title}</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="flex items-end justify-between gap-5 border-t border-white/[0.07] p-6 sm:p-7">
                <p className="max-w-md leading-6 text-muted-foreground">{description}</p>
                <Link
                  href={href}
                  aria-label={interpolate(t.dashboard.openTool, { title })}
                  className={cn(
                    buttonVariants({ variant: "outline", size: "icon" }),
                    "shrink-0 rounded-full border-white/[0.1] bg-white/[0.03] group-hover:border-primary/30 group-hover:text-primary",
                  )}
                >
                  <ArrowUpRight className="size-4" />
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section
        className="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]"
        aria-label={t.dashboard.dataPolicyAria}
      >
        <Card className="surface-glow border-white/[0.08] bg-card/75">
          <CardHeader>
            <div className="flex items-center gap-3">
              <Clock3 className="size-5 text-amber-300" aria-hidden="true" />
              <div>
                <CardTitle>{t.dashboard.referenceTitle}</CardTitle>
                <CardDescription>{t.dashboard.referenceDescription}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            {t.dashboard.referenceSteps.map(({ title, description }, index) => {
              const number = String(index + 1).padStart(2, "0");
              return (
              <div
                key={number}
                className="rounded-xl border border-white/[0.07] bg-background/35 p-4"
              >
                <span className="font-mono text-xs text-primary">{number}</span>
                <h3 className="mt-3 font-medium">{title}</h3>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
              </div>
              );
            })}
          </CardContent>
        </Card>

        <Card className="surface-glow border-white/[0.08] bg-card/75">
          <CardHeader>
            <CardTitle>{t.dashboard.foundationTitle}</CardTitle>
            <CardDescription>{t.dashboard.foundationDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              { icon: DatabaseZap, label: t.dashboard.foundations.mockProvider },
              { icon: ShieldCheck, label: t.dashboard.foundations.noCredentials },
              { icon: CheckCircle2, label: t.dashboard.foundations.decimalCore },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-3 text-sm">
                <Icon className="size-4 text-primary" aria-hidden="true" />
                <span>{label}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
