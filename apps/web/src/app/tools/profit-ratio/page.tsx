import type { Metadata } from "next";

import { Badge } from "@/components/ui/badge";
import { ProfitRatioDashboard } from "@/features/profit-ratio/profit-ratio-dashboard";
import { defaultProfitRatioRange } from "@/features/profit-ratio/display";
import { getDictionary } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { profitRatioPage } = await getDictionary();
  return {
    title: profitRatioPage.metadataTitle,
    description: profitRatioPage.metadataDescription,
  };
}

export default async function ProfitRatioPage() {
  const { profitRatioPage: t } = await getDictionary();

  return (
    <div className="flex flex-col gap-7">
      <section className="flex flex-col gap-4 border-b border-white/[0.07] pb-7 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-3 flex items-center gap-3">
            <p className="data-label">{t.eyebrow}</p>
            <Badge variant="outline" className="border-violet-300/25 text-violet-200">
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
      </section>
      <ProfitRatioDashboard initialRange={defaultProfitRatioRange()} />
    </div>
  );
}
