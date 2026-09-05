"use client";

import { Languages } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { isLocale } from "@/i18n/config";
import { useLocale } from "@/i18n/locale-provider";

export function LanguageSwitcher() {
  const { dictionary: t, locale, setLocale } = useLocale();

  function handleChange(value: unknown) {
    if (isLocale(value)) setLocale(value);
  }

  return (
    <Select value={locale} onValueChange={handleChange}>
      <SelectTrigger
        className="h-9 w-[6.5rem] border-white/[0.1] bg-white/[0.035] px-2.5"
        aria-label={t.common.language}
      >
        <Languages className="size-4 text-primary" aria-hidden="true" />
        <SelectValue>
          {locale === "zh-CN" ? t.common.chinese : t.common.english}
        </SelectValue>
      </SelectTrigger>
      <SelectContent align="end" alignItemWithTrigger={false}>
        <SelectItem value="en">{t.common.english}</SelectItem>
        <SelectItem value="zh-CN">{t.common.chinese}</SelectItem>
      </SelectContent>
    </Select>
  );
}
