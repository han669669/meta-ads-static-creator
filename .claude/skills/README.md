# Creative Stack: Static Ads, skill conventions

Generate on-brand, editable static ads for your brand using Claude and the fal API.

---

## Folder structure

Every brand has **two compartments**, and `/brand` creates both. `/brand` writes `intelligence/`; every other skill writes only into `generation/`. Multiple brands can coexist in the same project.

```
brands/
  [brand-name]/

    intelligence/                  ← what the brand IS. Written by /brand.
      visual-guidelines.md              ← visual identity + PROMPT MODIFIER (brand-detection marker)
      brand-strategy.md                 ← personality/values, audience, competitive landscape
      counter-positioning.md            ← counter-position + value proposition package
      brand-voice.md                    ← how the brand writes (copy layer)
      brand-context.md                  ← one-page portable capsule
      avatars.md                        ← the 3–5 named people the brand sells to
      offers.md                         ← the closed list of offers any ad may use
      color-palette.json                ← colour tokens (accent / neutral · name·hex·use)
      typography.json                   ← typefaces (role·family·source·weights)
      products.json                     ← product CATALOG index { brand, updated, products:[…] }
      product-images/                   ← FLAT product images: [slug]-01.jpg, [slug]-02.jpg …
      logos/                            ← logo files (.svg, .png)
      fonts/                            ← font files (meta-ads-static-creator sets copy in these)
      context-uploads/                  ← raw archive of every "add this to my brand context" drop

    generation/                    ← what the brand MAKES.
      meta-ads-static-creator/
        ad-references/                  ← inbox: drop winning-ad format refs here
        [output-name]/                  spec.json · plates · final PNGs · editable SVGs · layers.json
```

**`intelligence/visual-guidelines.md` is the brand-detection marker.** Its presence is what every downstream skill uses to recognise a real brand.

There is no canonical folder list. The tree is derived from every installed skill's `outputs:` and `inboxes:` frontmatter. `python3 .claude/skills/brand/brand.py --scaffold "[brand-name]"` creates the whole tree, and each skill also creates its own folders on first use.

---

## Skills

Each skill lives in `.claude/skills/<name>/` with its `SKILL.md` and its scripts alongside it.

| Command | What it does |
|---------|-------------|
| `/brand` | Build the brand's operating system under `intelligence/`: strategy, counter-positioning, palette, typography, logo, voice, context capsule, product catalog, avatars, offers. Also scaffolds `generation/`. Re-run any time to fold in new products, assets or facts |
| `/meta-ads-static-creator` | Recreate a winning static ad format with the brand's own products and copy: a text-free photographic plate plus independently editable text and UI, in 4:5 and 9:16 |

---

## Conventions

- Always open Claude Code from the project root
- File names: lowercase, hyphens, no spaces. Example: `energy-gels-dark.png` not `Energy Gels Dark.png`
- Output versioning: reruns always increment (`_v1`, `_v2`, `_v3`). Previous outputs are never overwritten
- FAL key goes in `.env` at the project root: `FAL_KEY=your_key_here`
- Generation scripts are invoked from the project root as `python3 .claude/skills/<skill>/<script>.py brands/[brand-name]/generation/<category>/[output-name]`

### Outputs vs references

- Outputs are what a skill generates. References and uploads are what a *human drops in* for a skill to read
- Reference and upload imagery must go in a dedicated inbox folder under the relevant category: `meta-ads-static-creator/ad-references/`
- Never save a reference image as a sibling output (e.g. do NOT create `meta-ads-static-creator/my-reference/` for a reference image) — anything that isn't a named inbox folder is treated as an output
- A new skill that consumes reference imagery declares the inbox in its own `SKILL.md` frontmatter — an `inboxes:` entry like `<category>/<purpose>-references: Label` (or `<category>/uploads: Label`). Nothing else needs to know: scaffold, validation and docs all read the frontmatter

### One-shot and utility scripts

Scripts (Python, Node, shell) must never be saved at the project root. They live in the relevant generation output folder, alongside the outputs they create or operate on.

- Path: `brands/<brand>/generation/<category>/<descriptive-name>.<ext>`
- Examples:
  - A script that bulk-seeds static-ad specs for Acme → `brands/acme/generation/meta-ads-static-creator/create-specs.py`
- Name by what the script does, lowercase hyphens
- Add a one-line docstring at the top stating purpose and scope
- Cross-brand or cross-skill utilities are rare. If one is genuinely needed, ask before placing it

### Product image naming

Product images are always **flat** in `intelligence/product-images/` — never in per-product subfolders.

Pattern: `[slug]-NN.ext` — e.g. `camp-shirt-01.jpg`, `camp-shirt-02.jpg`

- `[slug]` is the product identifier: lowercase, hyphenated, 2 or more tokens (`performance-running-socks`)
- `NN` is a zero-padded sequence number per product, starting at `01`. Every angle, variant or crop of the same product shares the `[slug]` and increments `NN`
- Files that share a `[slug]` group as one product in the catalog, so identical leading tokens matter
- `products.json` is the index over this folder: each entry is `{slug, name, images:[…], product_url, …}`. Rebuild it with `python3 .claude/skills/brand/brand.py --index` after dropping files in by hand
- Avoid mixing separators within a brand folder (do not use both `_` and `-`). Stick to `-`
- Avoid concatenating slug tokens (`tongkatali-02.webp` will not group with `tongkat-ali-01.jpg`). Hyphenate identically across every file for a product
