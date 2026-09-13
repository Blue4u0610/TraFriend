import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TraFriend",
    short_name: "TraFriend",
    description: "U.S. market analytics and leveraged ETF research tools.",
    start_url: "/",
    display: "standalone",
    background_color: "#0b1714",
    theme_color: "#0b1714",
    icons: [
      {
        src: "/brand/trafriend-mark-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/brand/trafriend-mark-512.png",
        sizes: "512x512",
        type: "image/png",
      },
    ],
  };
}
