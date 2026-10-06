# Creative Stack: Static Ads

On-brand static ads, grounded in the brand's full business context. `/brand` builds the brand's operating system from its website; `/meta-ads-static-creator` recreates winning static ad formats with the brand's own products, offers and copy, delivered as a text-free photographic plate plus independently editable text and UI in 4:5 and 9:16.

It is not much of a codebase on purpose. The skills are the product; the brand's own files are the substrate they read.

## Modularity

**Each skill describes itself. Nothing outside a skill keeps a list of skills.**

- Every skill's `SKILL.md` frontmatter declares its `outputs:` and `inboxes:` (folders under `brands/<brand>/generation/`), `requires:` (hard needs like `FAL_KEY` or `REPLICATE_API_TOKEN`), `optional:` (soft needs it degrades without), and a `version:`. Scaffolding, validation and the docs tables all derive from these declarations.
- **Skills create their own folders on first use** (`mkdir -p` for each declared path). `/brand`'s scaffold is a convenience, not a prerequisite.
- Everything reads the brand intelligence `/brand` writes. The shapes of the `intelligence/` files are the system's internal API; change them only deliberately.
- `python3 .claude/skills/brand/brand.py --validate` checks every declaration; `--docs` regenerates the skill tables between markers in `README.md` and this file.

## How this system thinks

- Every ad is grounded in the brand's whole operation (`brands/[brand]/intelligence/`): voice, products, offers, positioning, avatars. Not just the prompt that triggered it.
- Claude does the judgment (angles, copy, layout, art direction). Scripts do the mechanical work and checks. Don't script the judgment.

## Repository map

- `.claude/skills/brand/`: point it at a URL, get a brand brain: strategy, counter-positioning, voice, colour, typography, logo, product catalog, avatars, offers. **Run this first**; nothing else works without it. It also scaffolds the folders the other skills read and write.
- `.claude/skills/meta-ads-static-creator/`: reference-led static ads with editable copy. Conventions for all skills in `.claude/skills/README.md`.

<!-- skills-table:start -->
| | |
|---|---|
| **`/brand`** | Point it at a URL, get a brand brain. Run this first. Also folds new products, images, docs and facts into an existing brand at any time |
| **`/meta-ads-static-creator`** | Reference-led static ads with editable copy, paired mobile formats, and source-to-overlay approval gates |
<!-- skills-table:end -->

- `brands/[brand]/`: the context substrate: `intelligence/` (identity, strategy, commercial files) and `generation/` (versioned outputs). Created by `/brand`, never by hand. See `brands/README.md`.

## Generation

The generation skill reads the brand context and writes versioned output into `brands/[brand]/generation/`. The brand's **prompt modifier** (`visual-guidelines.md`) is what makes output look like the brand rather than like stock AI. Folder structure, version numbering and reference-image conventions are in `.claude/skills/README.md`.

Generation costs real money through fal or Replicate. The skill runs `--estimate`, states the provider, model, quality and cost, and gets explicit approval before any paid call. Quality defaults to low; a final high render is explicit (`--final`). There is no free stub mode: without `FAL_KEY` or `REPLICATE_API_TOKEN` the image step stops with a clear message.

## Guardrails (non-negotiable)

1. **Image generation (fal or Replicate) spends only behind an explicit gate.** Show the provider, model, quality and cost (from `--estimate`) before the first network call and get a yes.
2. Offers come from `intelligence/offers.md`; claims must be supportable by `brands/[brand]/intelligence/` content. Compliance rules in `brand-voice.md` are hard constraints, and no style or conversion rule may harden a health claim past what `intelligence/` supports. Truth outranks voice, which outranks everything else.
3. Reference ads contribute format and structure only, never another brand's copy, product or likeness.

## Starting state

**No brand is onboarded.** `brands/` holds nothing but its README. That is the intended starting point, not a gap.

- **First move: `/brand <url>`.** It builds the brand's operating system under `brands/[brand-name]/intelligence/` and scaffolds its folders.
- **Then `/meta-ads-static-creator`** with a reference ad dropped into `generation/meta-ads-static-creator/ad-references/`.
- Chat is plain-language, no step codes or schema names, and every step closes with a short summary plus what the user does next.
