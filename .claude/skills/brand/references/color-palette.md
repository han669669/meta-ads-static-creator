# Color Palette — Format Reference

> **What this is.** The structure `/brand` writes to
> `intelligence/color-palette.json`. It captures the brand's colour tokens as
> structured data — each colour's **name**, **hex**, and **what it's used for** —
> read during `/brand` from the **web scrape of the brand's website** (live
> computed styles via `extract-site-colors.js`), or from brand docs / stated
> guidelines. If the scraper can't read the site, `/brand` asks the user for a
> **screenshot of their colour palette** and reads the hexes from that. It is a
> structured companion to the human-readable colour section in
> `visual-guidelines.md`, and is fully editable — `/brand` produces a complete
> best-effort first pass and the user corrects it.

## Schema

A single JSON object. `brand` is a string; every other key is an **array** of
colour entries. Each entry is `{ "name", "hex", "use" }`. The palette is
organised into **two real buckets** — `accent` and `neutral`; the legacy keys
`primary`, `secondary`, `background` remain in the file for backward
compatibility but are always written as empty arrays:

```json
{
  "brand": "My Brand",
  "primary": [],
  "secondary": [],
  "accent": [
    { "name": "Signal Orange", "hex": "#E87240", "use": "Signature brand colour — CTAs, badges, highlights" },
    { "name": "Mint Teal",     "hex": "#57C5BC", "use": "Cool counterpoint — product hardware, small highlights" }
  ],
  "neutral": [
    { "name": "Ink Black",  "hex": "#111111", "use": "Headlines, body text, wordmark" },
    { "name": "Mid Gray",   "hex": "#9E9E9E", "use": "Captions, metadata, dividers" },
    { "name": "Light Gray", "hex": "#F5F5F5", "use": "Card surfaces, subtle backgrounds" },
    { "name": "Canvas",     "hex": "#FAFAFA", "use": "Default page/post background" }
  ],
  "background": []
}
```

## Rules

- **Two buckets — there are no "primary" colours.**
  - `accent` — the brand's genuinely *coloured* colours: saturated signature
    hues, CTA/link colours, earth-tone or pastel brand colourways — anything
    with a real hue.
  - `neutral` — blacks and near-blacks (including near-black navies that read
    as ink), whites and off-whites, the gray ramp, and quiet surface/backdrop
    tones. The default page/canvas background belongs here. Order neutrals
    dark → light.
- **Top-level keys:** `brand` (string), then `primary`, `secondary`, `accent`,
  `neutral`, `background` (arrays). Keep all six keys — `primary`, `secondary`,
  and `background` are legacy roles and are always written as empty arrays
  `[]`; every colour goes into `accent` or `neutral`.
- **Hex:** uppercase, 6-digit, `#`-prefixed (`#C8A96E`). Prefer exact values read
  from the live site (`extract-site-colors.js`), brand docs, or a palette
  screenshot the user provides when the scrape fails. Always produce a
  complete palette — the file is editable, so a populated best-effort bucket
  beats an empty one; just flag any colour you're unsure about so the user
  knows to check it.
- **`use`:** one short phrase describing where the colour is applied (headlines,
  CTAs, dividers, body text, backgrounds, …). This is what lets a generation
  skill reason about *when* to reach for each colour.

## Relationship to visual-guidelines.md

`color-palette.json` is the **raw, exact colour-token list** (extracted by
`/brand`, machine-readable). The **Colour palette** section of
`visual-guidelines.md` is the **human-readable** version, and the **Prompt
modifier** paragraph is where the load-bearing hexes get baked into a
generation-ready instruction. Keep the two consistent: the hexes in the JSON and
the hexes named in the guidelines and prompt modifier must match.
