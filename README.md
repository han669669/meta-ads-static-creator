# Creative Stack: Static Ads

**Joey Mulcahy** made this skill (https://joeymulcahy.com/). This repository contains the skill without his permission. You can get more information from Joey through his videos and his newsletter.

Joey Mulcahy keeps all rights. This repository does not give an open-source license.

You give Claude the website of your brand. Claude makes a brand operating system. Then the skill makes static ads in the format of your reference ads. The ads use your products, your offers, and your copy.

Each ad has a clean photographic plate with no text. Each ad has text layers and UI layers that you can change. The skill makes each ad in 4:5 feed format and in 9:16 full-screen format.

<!-- skills-count:start -->
This repository contains two skills. Each skill reads the same brand context.
<!-- skills-count:end -->

> [!NOTE]
> You do not see many files in this folder. The skills are in `.claude/`. `.claude/` is a hidden folder.
>
> In Finder, `Cmd+Shift+.` shows hidden folders. A Claude session in this folder can use the skills.

## Install

Type this command:

```bash
npx skills add han669669/meta-ads-static-creator
```

If you want only the static-ad skill, type this command:

```bash
npx skills add han669669/meta-ads-static-creator --skill meta-ads-static-creator
```

Before you make ads, type `/brand`.

This command makes the brand operating system.

<a id="what-you-need"></a>

## Necessary items

These items are necessary:

- **Claude Code** or **Claude Cowork** is necessary. The Claude session uses this folder. Then Claude can start the scripts.
- **Python 3.10+** (Python 3.10 or a subsequent version) is necessary. Type `pip install -r requirements.txt`.
- An image key is necessary. The key is a **fal.ai** key (`FAL_KEY`) or a **Replicate** token (`REPLICATE_API_TOKEN`). You can get a Replicate token from [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens). Copy `.env.example` to `.env`. Add one key. If you set both keys, the skill uses fal unless you set `IMAGE_PROVIDER` or pass `--provider`.
- **Paper** (connected to Claude) is necessary. You use Paper to make the ad layers that you can change.
- **Claude in Chrome** is not necessary, but it helps `/brand` read colors, fonts, and your logo from your site.

> [!CAUTION]
> Approve each paid call before it starts. Image generation has a cost on your own account. Claude uses `--estimate` and shows the cost. Claude does not start a paid call before you approve it.

## Start here

Type these commands:

```bash
pip install -r requirements.txt
cp .env.example .env        # then add FAL_KEY and/or REPLICATE_API_TOKEN
```

Open a Claude session in this folder.

Then type this command:

```
/brand https://your-brand.com
```

This command makes the brand operating system in `brands/[brand-name]/`. The brand system contains strategy, positioning, voice, color, typography, the product catalog, avatars, and offers. No other skill operates before this step. Each ad uses this brand system.

Then copy the reference ad that you want to make again to `brands/[brand-name]/generation/meta-ads-static-creator/ad-references/`.

Then type this command:

```
/meta-ads-static-creator
```

## The skills

<!-- skills-table:start -->
| | |
|---|---|
| **`/brand`** | `/brand` makes a brand system from a URL. This is the first command. You can add new products, images, documents, and facts to a brand at any time. |
| **`/meta-ads-static-creator`** | This skill makes static ads from a reference. You can change the copy. The skill makes paired mobile formats. The skill has source-to-overlay approval gates. |
<!-- skills-table:end -->

<a id="how-a-static-ad-gets-made"></a>

## How the skill makes a static ad

1. **Read the reference.** Claude reads the reference ad. Claude finds the format devices (search bars, ratings, testimonial cards, labels, badges, proof). Claude writes copy from your brand files. Claude does not make offers or claims that are not in your brand files.
2. **Wireframe first.** The skill makes a full layout that you can change for each ratio first. The layout uses copy from your brand files. The skill makes the layout before it makes any image.
3. **Make only the photography.** The skill makes one photographic plate with no text for each ratio. You approve the cost before the skill makes a paid call. You approve the plate before the skill adds copy.
4. **Overlays that you can change.** The skill makes text and UI as separate layers in your brand fonts. The output is a flat PNG, an SVG that you can change, and a layer map. You use the layer map to make the ad in Paper.
5. **Mobile preflight.** The skill does a check of safe zones, platform UI rails, and minimum type sizes. The skill does this check for 4:5 and for 9:16.

Changes to copy and to layout after this step have no cost. Only a new photographic plate has a cost.

<a id="choosing-a-provider"></a>

## Image providers

Both providers use **GPT Image 2.5 Sunburst**. fal is the default when you set only `FAL_KEY`.

| | fal | Replicate |
|---|---|---|
| Env | `FAL_KEY` | `REPLICATE_API_TOKEN` |
| Model | `openai/gpt-image-2.5/sunburst/{edit,text-to-image}` | `openai/gpt-image-2.5-sunburst` |
| Default quality | `low` (final render: `--final` → `high`) | same |
| Cost | Cost is token-based. `--estimate` cannot give an exact USD figure. | Per output image (input images have no cost): low $0.012, medium $0.047, high $0.128 (checked 2026-10-06) |
| 4:5 | native custom size 1229×1536 | Replicate makes 1152×1536, then a centre-crop to 1152×1440 |
| Uploads | fal CDN (public by default) | Replicate uses a private Files API. Replicate deletes the files after the run. |
| Spend cap | fal account controls | Refer to the caution below. |

> [!CAUTION]
> Use prepaid credit with auto-reload off. Replicate tokens cannot have a spend cap.

The skill selects the provider in this order:

1. `--provider`
2. `spec.json` `"provider"`
3. `IMAGE_PROVIDER`
4. The single key that you set
5. fal.

The skill makes first-pass plates and subsequent renders at **low**. Pass `--final` (or `--quality high`) only for a last high-quality render.

## Layout

| Path | What it is |
|---|---|
| `CLAUDE.md` | How the system operates and the rules that it follows |
| `.claude/skills/` | The skills. Each skill is in one folder that contains all of its files. |
| `brands/[brand]/` | `/brand` makes this folder. It contains `intelligence/` (what the brand is) and `generation/` (the ads that you make). Do not make this folder without `/brand`. |
