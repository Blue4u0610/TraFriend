export const supportedLocales = ["en", "zh-CN"] as const;

export type Locale = (typeof supportedLocales)[number];

export const defaultLocale: Locale = "en";
export const localeCookieName = "trafriend_locale";

export function isLocale(value: unknown): value is Locale {
  return supportedLocales.includes(value as Locale);
}

