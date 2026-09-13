import type { MetadataRoute } from "next";

const siteUrl = "https://www.trafriend.xyz";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: siteUrl,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${siteUrl}/tools/leverage`,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${siteUrl}/tools/profit-ratio`,
      changeFrequency: "daily",
      priority: 0.8,
    },
  ];
}
