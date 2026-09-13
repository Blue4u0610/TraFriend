# TraFriend website icon

The shared TF mark combines the site's mint/forest-green palette with a rising
step motif. It is used for the header, browser tabs, bookmarks, search results,
and Apple home-screen shortcuts. The header's localized home-link label remains
the accessible name; the nested image is decorative.

## Files

- `apps/web/public/brand/trafriend-mark.png`: original 1254px square artwork.
- `apps/web/public/brand/trafriend-mark-96.png`: compact high-density header image.
- `apps/web/public/brand/trafriend-mark-192.png`: installable-app icon.
- `apps/web/public/brand/trafriend-mark-512.png`: high-density installable-app icon.
- `apps/web/src/app/favicon.ico`: 16, 32, 48, 64 and 96px PNG frames.
- `apps/web/src/app/icon.png`: 192px square favicon.
- `apps/web/src/app/apple-icon.png`: 180px Apple touch icon.
- `apps/web/src/app/manifest.ts`: installable-app metadata referencing the same mark.

Next.js App Router file metadata generates the icon links on every route.
The former chart-only `icon.svg` is replaced, so browsers do not select a
different brand mark. `/favicon.ico` provides a stable crawlable URL, with a
frame larger than 48px for search surfaces. The files ship with the frontend
and require no backend or market-data configuration.

Regenerate exports from the committed source in `apps/web` using the Sharp
installation supplied by Next.js:

```sh
node scripts/generate-brand-icons.mjs
```

After deployment, verify `/favicon.ico`, `/icon.png`, and `/apple-icon.png`
return images, `/manifest.webmanifest` references both installable-app icons, and
the home page advertises them. Search engines choose when to
recrawl and display a favicon; a local implementation does not update indexed
search results immediately. See [Google's favicon guidelines](https://developers.google.com/search/docs/appearance/favicon-in-search).

## Image provenance

Created on 2026-09-13 with the built-in image generation tool (`logo-brand`),
then mechanically resized and packaged without changing the artwork. No provider
data or credentials are used in these assets.

Generation brief: a bold, compact interlocking TF monogram for TraFriend, mint
`#70e5c7` on dark forest `#0b1714`, with a rising chart step, broad strokes and
balanced negative space, legible at 16/32px; one square icon with no wordmark,
border, mockup, watermark, texture or extra symbols.

Final refinement prompt:

> Refine this exact TraFriend TF logo for final website favicon use. Preserve its TF silhouette, composition and mint color. The background MUST be a visible full-bleed solid opaque dark forest green #0b1714 square, not transparency and not black. Smooth the edges into perfectly clean flat shapes and remove all turquoise edge speckles/halos. All strokes must be completely uniform flat mint #70e5c7, with no gradients, shading or texture. Do not change letter layout. Final square icon alone, no mockup, no border, no added text, no rounded outer corners. It needs a solid dark green background right to every image edge.
