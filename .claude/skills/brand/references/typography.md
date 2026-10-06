# Typography & Design System — Format Reference

> **What this is.** The structure `/brand` writes to
> `intelligence/typography.json`. It captures the brand's **typefaces** (which
> fonts, in which roles, from which source) and any **design-system** evidence
> found during setup. Read during `/brand` from the **web read of the brand's
> site** — live computed `font-family` plus the `@font-face` / webfont-provider
> links via `extract-site-fonts.js` (the same rendered-font read the *WhatFont*
> extension does, done page-wide) — backed by a web search for the brand's
> published design-system / typography documentation. If the automated read
> fails, `/brand` asks the user to run the **WhatFont** Chrome extension on the
> live site (or send a screenshot) and reports the families from that. It is a
> structured companion to the **Typography** section of `visual-guidelines.md`,
> and is fully editable — `/brand` produces a complete best-effort first pass and
> the user corrects it.

## Schema

A single JSON object. `brand` is a string. `fonts` is an **array** of typeface
entries, each `{ "role", "family", "description", "fallback", "source", "weights", "url" }`.
`design_system` is an object recording any published system found.

```json
{
  "brand": "My Brand",
  "note": "Auto-detected by /brand from the live site — AI can misread fonts, so please verify the typefaces, weights, and any design-system link before relying on them, and correct them in the brand files.",
  "fonts": [
    {
      "role": "heading",
      "family": "Playfair Display",
      "description": "High-contrast modern serif; fine hairlines, elegant ballpoint terminals, tall ascenders — refined and editorial.",
      "fallback": "serif",
      "source": "google-fonts",
      "weights": ["600", "700"],
      "url": "https://fonts.google.com/specimen/Playfair+Display"
    },
    {
      "role": "body",
      "family": "Inter",
      "description": "Neutral humanist sans; monoline strokes, tall x-height, open apertures — clean and highly legible at small sizes.",
      "fallback": "sans-serif",
      "source": "google-fonts",
      "weights": ["400", "500"],
      "url": "https://fonts.google.com/specimen/Inter"
    },
    {
      "role": "accent",
      "family": "unknown",
      "description": "Geometric grotesque sans in medium weight, slightly condensed, set in all-caps with wide tracking — used only for eyebrow labels. Exact family couldn't be identified; description carries the direction.",
      "fallback": "sans-serif",
      "source": "unknown",
      "weights": ["500"],
      "url": null
    }
  ],
  "design_system": {
    "exists": true,
    "name": "My Brand Design System",
    "url": "https://brand.com/design",
    "notes": "Public brand/guidelines page; type scale + logo usage documented."
  }
}
```

## Rules

- **`note` (always include):** a short verification caveat, kept verbatim, e.g.
  *"Auto-detected by /brand from the live site — AI can misread fonts, so please
  verify the typefaces, weights, and any design-system link before relying on
  them, and correct them in the brand files."* Fonts are inferred from the
  rendered page (or a screenshot / the user's report), which a model can get
  wrong — this note makes the "check me" expectation travel with the file.
- **`fonts` roles:** use `heading`, `body`, `accent`, and `mono` where they
  apply. `heading` and `body` are the load-bearing two — always fill them when
  the site reveals them. Add `accent` only when a genuinely distinct display/UI
  face is used (drop it if it just duplicates heading or body); add `mono` only
  if the brand uses a monospace face. One entry per role; omit roles the brand
  doesn't use.
- **`family`:** the exact typeface name as the site declares it (the first real
  family in the `font-family` stack — the face the browser actually paints, not
  the generic fallback). Prefer values read from `extract-site-fonts.js`
  `suggested` / `loaded`, the brand's stated guidelines, or a WhatFont read the
  user reports. If the face genuinely can't be identified, set `"unknown"` rather
  than guessing a name — and lean on `description` to carry the direction.
- **`description` (always include):** a short visual characterisation of the
  typeface — category (serif / sans / slab / mono / display), stroke contrast
  (high vs. monoline), weight and width, and any distinctive letterforms or
  treatment (all-caps, tight tracking, humanist vs. geometric). Write it for
  every role, but it is **load-bearing when the font is missing** — either its
  name can't be pinned (`family: "unknown"`) or the file can't be downloaded (a
  licensed/foundry face). Downstream image and ad skills read this description to
  keep type on-brand when the actual name and file aren't available, so make it
  concrete enough to brief a designer, not just "a nice serif".
- **`fallback`:** the generic family the stack falls back to (`sans-serif`,
  `serif`, `monospace`).
- **`source`:** where the font comes from — `google-fonts`, `adobe-fonts`
  (Typekit), `self-hosted`, `system`, or `unknown`. Derive it from the
  `links`/`loaded` evidence the extractor returns. This decides whether `/brand`
  can auto-download it: **only `google-fonts` families can be fetched into
  `fonts/`** (via `brand.py --fetch-fonts`); licensed/foundry faces must be added
  by hand.
- **`weights`:** the weights actually loaded, as strings (`"400"`, `"700"`).
  Empty array if unknown.
- **`url`:** a specimen / source URL when one exists (Google Fonts specimen,
  foundry page), else `null`.
- **`design_system`:** set `exists` true only when a real published system or
  brand-guidelines/typography page was found; record its `name`, `url`, and a
  one-line `notes`. If none was found, write
  `{ "exists": false, "name": null, "url": null, "notes": null }` rather than
  omitting the key.
- Always produce a complete best-effort first pass — the file is editable, so a
  populated `heading`+`body` pair beats an empty file; flag any role you're
  unsure about in the Step 6 summary.

## Relationship to visual-guidelines.md & the fonts folder

`typography.json` is the **raw, exact typeface list + design-system pointer**
(extracted by `/brand`, machine-readable). The **Typography** section of
`visual-guidelines.md` is the human-readable version that image and ad skills
read directly. The `fonts/` folder holds the actual font *files*: `/brand`
auto-downloads open-license (`google-fonts`) families there, and the user drops
licensed faces in by hand. Keep the font names consistent across all three.
