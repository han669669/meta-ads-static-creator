# Creative Stack: Static Ads

Created by **Joey Mulcahy** — https://joeymulcahy.com/ . Published here without his permission. Find more from Joey via his videos and newsletter.

Rights remain with Joey Mulcahy. This repository does not grant an open-source license.

Point Claude at your brand's website, get a brand brain, then recreate winning static ad formats with your own products, offers and copy. Every ad comes out as a clean photographic plate plus fully editable text and UI layers, in both 4:5 feed and 9:16 full-screen.

<!-- skills-count:start -->
Two skills. One brand context every one of them reads.
<!-- skills-count:end -->

> Looking at this folder and it seems near-empty? The skills live in `.claude/`, a hidden folder. It's there. Press `Cmd+Shift+.` in Finder to see it, or just open a Claude session here and everything works.

## Install

```bash
npx skills add han669669/meta-ads-static-creator
```

To install only the static-ad skill:

```bash
npx skills add han669669/meta-ads-static-creator --skill meta-ads-static-creator
```

Run `/brand` first to build the brand operating system before generating ads.

## What you need

- **Claude Code** or **Claude Cowork** with this folder open, so Claude can run the scripts.
- **Python 3.10+**, then `pip install -r requirements.txt`.
- An image key: a **fal.ai key** (`FAL_KEY`) **or** a **Replicate token** (`REPLICATE_API_TOKEN`, from [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens)). Copy `.env.example` to `.env` and add one. If both are present, fal is used unless you set `IMAGE_PROVIDER` or pass `--provider`. Generation is paid on your own account. Claude runs `--estimate`, shows the cost, and asks before every paid call.
- **Paper** connected to Claude, for building the editable ad layers.
- Recommended: **Claude in Chrome**, so `/brand` can read colours, fonts and your logo straight off your site.

## Start here

```bash
pip install -r requirements.txt
cp .env.example .env        # then add FAL_KEY and/or REPLICATE_API_TOKEN
```

Open a Claude session in this folder and run:

```
/brand https://your-brand.com
```

That builds your brand's operating system under `brands/[brand-name]/`: strategy, positioning, voice, colour, typography, product catalog, avatars and offers. Nothing else works before it, and every ad is personalised by it.

Then drop a winning ad you want to recreate into `brands/[brand-name]/generation/meta-ads-static-creator/ad-references/` and run:

```
/meta-ads-static-creator
```

## The skills

<!-- skills-table:start -->
| | |
|---|---|
| **`/brand`** | Point it at a URL, get a brand brain. Run this first. Also folds new products, images, docs and facts into an existing brand at any time |
| **`/meta-ads-static-creator`** | Reference-led static ads with editable copy, paired mobile formats, and source-to-overlay approval gates |
<!-- skills-table:end -->

## How a static ad gets made

1. **Read the reference.** Claude breaks the winning ad into its format devices (search bars, ratings, testimonial cards, labels, badges, proof) and writes copy from your own brand files. It never invents offers or claims.
2. **Wireframe first.** A full editable layout for each ratio, built with your real copy, before any image is generated.
3. **Generate only the photography.** A text-free photographic plate per ratio. You approve the cost before anything is spent, and you approve the plate before any copy goes on it.
4. **Editable overlays.** Text and UI are composed as separate layers in your brand fonts: a flat PNG, an editable SVG, and a layer map for building the ad in Paper.
5. **Mobile preflight.** Safe zones, platform UI rails and minimum type sizes are checked for both 4:5 and 9:16.

Copy and layout changes after that are free. Only a new photographic plate costs money.

## Choosing a provider

Both paths use **GPT Image 2.5 Sunburst**. fal is the default for existing setups that only have `FAL_KEY`.

| | fal | Replicate |
|---|---|---|
| Env | `FAL_KEY` | `REPLICATE_API_TOKEN` |
| Model | `openai/gpt-image-2.5/sunburst/{edit,text-to-image}` | `openai/gpt-image-2.5-sunburst` |
| Default quality | `low` (final render: `--final` → `high`) | same |
| Cost | token-based; `--estimate` cannot give an exact USD figure | per output image (input images free): low $0.012, medium $0.047, high $0.128 (checked 2026-10-06) |
| 4:5 | native custom size 1229×1536 | generate 1152×1536, centre-crop to 1152×1440 |
| Uploads | fal CDN (public by default) | private Files API, deleted after the run |
| Spend cap | fal account controls | Replicate tokens cannot be spend-capped; use prepaid credit with auto-reload off |

Provider resolution: `--provider` → `spec.json` `"provider"` → `IMAGE_PROVIDER` → whichever single key is set → fal.

First-pass plates and edits generate at **low**. Pass `--final` (or `--quality high`) only for a last high-quality render.

## Layout

| Path | What it is |
|---|---|
| `CLAUDE.md` | How the system works and the rules it follows |
| `.claude/skills/` | The skills. Each one is a self-contained folder |
| `brands/[brand]/` | Created by `/brand`: `intelligence/` (what the brand is) and `generation/` (the ads you make). Don't build it by hand |
