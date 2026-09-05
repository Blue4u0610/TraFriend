import type { Metadata } from "next";
import { Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { LeverageCalculator } from "@/features/leveraged-calculator/leverage-calculator";
import { getDictionary } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { leveragePage } = await getDictionary();
  return {
    title: leveragePage.metadataTitle,
    description: leveragePage.metadataDescription,
  };
}

export default async function LeveragePage() {
  const { leveragePage: t } = await getDictionary();

  return (
    <div className="flex flex-col gap-7">
      <section className="flex flex-col gap-4 border-b border-white/[0.07] pb-7 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-3 flex items-center gap-3">
            <p className="data-label">{t.eyebrow}</p>
            <Badge variant="outline" className="border-primary/25 text-primary">
              {t.badge}
            </Badge>
          </div>
          <h1 className="text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
            {t.title}
          </h1>
          <p className="mt-3 max-w-2xl leading-7 text-muted-foreground">
            {t.description}
          </p>
        </div>
        <div className="flex max-w-md gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[0.045] p-4 text-sm leading-6 text-amber-100/80">
          <Info className="mt-0.5 size-4 shrink-0 text-amber-300" aria-hidden="true" />
          {t.warning}
        </div>
      </section>
      <LeverageCalculator />
    </div>
  );
}
