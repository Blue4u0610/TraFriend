"use client";

import { useEffect, useState } from "react";
import { CircleAlert, Radio } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getHealth } from "@/lib/api/client";
import type { Health } from "@/lib/api/types";
import { useLocale } from "@/i18n/locale-provider";

export function ApiStatus() {
  const { dictionary: t } = useLocale();
  const [health, setHealth] = useState<Health | null>(null);
  const [isUnavailable, setIsUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((result) => {
        if (active) setHealth(result);
      })
      .catch(() => {
        if (active) setIsUnavailable(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!health && !isUnavailable) {
    return <Skeleton className="h-7 w-36 rounded-full" />;
  }

  if (isUnavailable) {
    return (
      <Badge variant="outline" className="gap-2 border-amber-400/25 text-amber-300">
        <CircleAlert className="size-3.5" aria-hidden="true" />
        {t.apiStatus.offline}
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="gap-2 border-primary/25 bg-primary/5 text-primary">
      <Radio className="size-3.5" aria-hidden="true" />
      {t.apiStatus.connected}
    </Badge>
  );
}
