---
name: meta-ads-static-creator
description: "Create reference-led static ads with editable copy: generate only the photographic plate, then build and quality-check independently editable text and UI for 4:5 and 9:16 delivery."
image_model: GPT Image 2.5 Sunburst
group: Ads
summary: Reference-led static ads with editable copy, paired mobile formats, and source-to-overlay approval gates
version: 3.0.1
outputs: [meta-ads-static-creator]
inboxes:
  meta-ads-static-creator/ad-references: Ad references
requires: [FAL_KEY | REPLICATE_API_TOKEN]
optional: [intelligence/fonts/*.ttf — the brand's real typefaces; degrades to a described fallback face, Open Design desktop app + MCP]
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/*)
metadata:
  author: "Joey Mulcahy"
  source: "https://joeymulcahy.com/"
  published-by: "han669669"
---

# Static Ads — editable text layer

Created by Joey Mulcahy — https://joeymulcahy.com/. Published here without his permission.

Build an ad from two independent parts: a text-free photographic plate and an
editable layout. Use this skill when the copy needs to be localised, tested or
edited after delivery. Create its declared inbox and output folders before use.

Call every bundled script through `${CLAUDE_SKILL_DIR}` (Claude Code substitutes
the folder that contains this `SKILL.md`):

```bash
python3 "${CLAUDE_SKILL_DIR}/generate-blank-ad.py" …
python3 "${CLAUDE_SKILL_DIR}/compose-text.py" …
python3 "${CLAUDE_SKILL_DIR}/layers-to-html.py" …
python3 "${CLAUDE_SKILL_DIR}/prepare-ratio-plate.py" …
```

## Bundled files, network and credentials

These files ship with the skill. They are not separate downloads.

- `generate-blank-ad.py` — `--estimate` prints provider, model, quality and cost
  with no network. After approval it generates one text-free photographic plate.
- `compose-text.py` — sets approved copy onto a plate in brand fonts. Writes the
  PNG, the embedded-font SVG and `layers.json`. No network.
- `layers-to-html.py` — turns `layers.json` into Open Design HTML (one 4:5 page,
  one 9:16 page, a review board; `--wireframe` and `--preflight`). No network.
- `prepare-ratio-plate.py` — builds a layout-first ratio plate from photography
  already named in `spec.json`. No network; it never calls an image model.
- `providers/__init__.py` — picks provider and quality from CLI, spec, env and
  keys. Loads fal or Replicate. No silent cross-provider fallback.
- `providers/_output.py` — HTTPS and host allow-list checks, Location
  resolution, and redirect chasing (5-hop cap) for output downloads. Providers
  pass their hosts, GET function, and billing. Credentials only on the same
  allow-listed host. No network on import.
- `providers/replicate_provider.py` — raw HTTP client for
  `openai/gpt-image-2.5-sunburst` on Replicate.
- `providers/fal_provider.py` — `fal_client` wrapper for GPT Image 2.5 Sunburst
  on fal.

**Hosts.** Replicate uses `https://api.replicate.com/v1` for uploads, create,
poll and delete. Output images are downloaded from `replicate.delivery` (and its
subdomains). fal goes through `fal_client` (upload + run); output images are
downloaded from fal CDN URLs on `fal.media` / `fal.run` hosts (including
`v3.fal.media` and `v3b.fal.media`).

**Keys.** The scripts use `FAL_KEY`, `REPLICATE_API_TOKEN` and `IMAGE_PROVIDER`
from the process environment. Missing names are filled from the project `.env`
(`$CLAUDE_PROJECT_DIR`, then the working directory, then a parent that contains
`.claude`) with `setdefault`, so an exported value wins. They never read
`~/.env`. They do not load any other env names from that file.

**Token scope.** `REPLICATE_API_TOKEN` is sent as `Authorization: Bearer` to
`api.replicate.com`. Output downloads start as a plain GET with no token; on
HTTP 401 or 403 the token is sent again only to an allow-listed Replicate host.
`FAL_KEY` is used by `fal_client` for fal's own API. Keys are not sent to any
other host.

**No shell.** The Python does not call `subprocess`, `os.system`, or a shell.

**Deletes.** Replicate deletes only the Files API uploads from *this* run
(`DELETE /v1/files/{id}`). It unlinks its own pending marker
`.{label}-replicate-pending.txt` after a successful plate. If writing the local
plate PNG fails after the bytes are on disk, `generate-blank-ad.py` unlinks that
partial file. Nothing else is deleted.

**Open Design.** Optional (see `optional:`). Drive it only through MCP file
tools: `create_project`, `create_artifact`, `write_file`, `get_file`,
`list_files`, `search_files`, `get_artifact`, `get_project`. Never call
`start_run`, `get_run`, or `cancel_run`.

## Non-negotiables

- Every run delivers two independently composed variants: **4:5** (1080×1350) and
  **9:16** (1080×1920). Never crop one finished design into the other.
- All claims, offers and product facts must be supported by
  `brands/<brand>/intelligence/`. Do not infer them from the reference.
- Before any paid call, run `python3 "${CLAUDE_SKILL_DIR}/generate-blank-ad.py" … --estimate` for each plate
  and state the provider, model, quality, exact plates, call count, base cost
  and maximum cost including one quality retry per failed plate. Get explicit
  approval. Replicate prices are per output image (input images free; checked
  2026-10-06: low $0.012, medium $0.047, high $0.128). fal prices are
  token-based approximations from the model page.
- Quality defaults to **low** for first-pass plates, edits and revisions. Use
  `--final` (or `--quality high`) only when the user asks for a final high
  render. Do not silently generate at high.
- Each failed plate may use one pre-authorised retry. A provider error that
  reports *not billed* does not consume that retry. *Billing unknown* counts as
  spent. If the retry fails too, show the better source; do not spend again
  without fresh approval.
- Do not generate merely to improve editable layout. Overlay iteration is free.
- Drive Open Design only through its MCP file tools. Never call `start_run`,
  `get_run` or `cancel_run`: those launch Open Design's own agent (Claude Code
  with `bypassPermissions`) and can spend OpenDesign Cloud credits.
- Before the first Open Design write in a run, name the project and the files
  you will write, then get explicit approval. Do not call `create_project`,
  `create_artifact` or `write_file` until that yes.

## 1. Read the brief and choose a route

Read the brand's visual guidelines, typography, colour, product and offer files.
Inspect the reference and record its format-defining primitives: image treatment,
search modules, ratings, testimonial cards, comparison states, labels, badges,
rules, buttons and proof. Every primitive is `photographic`, `editable`, or an
intentional documented omission. Do not replace a recognisable format device with
generic campaign copy.

Use **layout-first** for three or more text groups, offers, comparisons, statistics,
annotated images or precise editorial hierarchy. Build the complete editable
wireframe first in Open Design HTML; photography only fills named image zones.
Decide before generation whether each image zone is a deliberate panel or a
seamless bleed, and preserve that treatment through the run.

Use **plate-first** only for a simple image-led composition with one short headline
and generous, unambiguous copy space.

## 2. Specify the system

Write `brands/<brand>/generation/meta-ads-static-creator/<output-name>/spec.json` before
generating. It contains the reference and product inputs, supported copy, both
delivery variants, image zones, source prompt, format primitives and route.
Optional: `"provider": "fal"|"replicate"` and `"quality": "low"|"medium"|"high"`
(or the same keys under `provider_options`). Quality still defaults to low when
omitted; `--quality` / `--final` on the CLI override the spec.

Every photographic product plate needs two references:

1. an isolated, exact packshot for shape, finish and label; and
2. the same product held in a hand or shown against/on a body for scale.

Record these as `product_images` and `product_scale_reference`. The format reference
may be the scale reference only if it visibly shows the exact product. Otherwise use
a brand-owned scale asset or ask for one. Never substitute another SKU or a generic
hand reference.

For any visual role repeated at least twice—labels, callouts, statistics, cards,
search rows, comparison cells, offers or CTAs—add a `repeated_systems` entry. Define
the shared type, container, padding, stroke/radius/fill, baseline or alignment edge,
and permitted reference-derived variations. Connector systems also define the common
rule, endpoint and anchor treatment. Composition may be asymmetric; repeated
components may not vary arbitrarily.

For annotation formats, also record the annotation subject, supported labels and
visual anchor for each label. Labels must answer the same product question; do not
mix ingredients with founder facts, serving counts, offers or unrelated claims.

## 3. Build the wireframe before photography

Open Design is HTML-file based. There are no artboards. Make one fixed-size HTML
page per ratio: **4:5 = 1080×1350**, **9:16 = 1080×1920**. Run
`python3 "${CLAUDE_SKILL_DIR}/layers-to-html.py" … --variant … --wireframe` from the spec (or write the same
shape through MCP file tools). Each image zone is a placeholder box. Add the
`od-hide-images` class so the layout still works with images hidden: hierarchy,
lanes, UI, proof and CTA remain clear and editable.

Build one correct repeated component as a shared CSS class (`od-sys-<name>`);
vary content and placement, not type, padding, box size or line style unless the
reference specifically calls for it. One HTML element per layer, with a stable
`data-od-id` and a readable `data-od-name`.

Review repeated components side by side (the review-board HTML, or both pages
in Open Design). Equal roles must share their declared system and align to
intentional lanes or anchors—not convenient empty pixels. For leader lines, use
short, non-crossing routes to distinct anchors. Keep labels, leaders and
containers clear of faces, product labels and critical copy.

Do not put photography into the wireframe until it passes this review. Open
Design has no screenshot tool. Give the user the `previewUrl` from `get_project`
and keep the local HTML with the run.

### Open Design MCP (file tools only)

Run mode: the user's Open Design **macOS desktop app**, with their own keys. Do
not sign in to OpenDesign Cloud. The desktop app (the daemon) must be open.
Docs in this skill were checked against **Open Design v0.24.1**; MCP tool names
below were read from `apps/daemon/src/mcp.ts` on 2026-10-06.

Use only these tools (parameter names as the live MCP schema shows them):

- `create_project` (`name`, optional `id`) — once per run, after the write gate
- `create_artifact` (`name`, `content`, optional `encoding` `utf8`|`base64`) —
  first write of each HTML entry file
- `write_file` (`path`, `content`, optional `encoding`) — fonts, plate PNGs,
  later HTML overwrites (`encoding=base64` for binary)
- `get_file` / `get_artifact` / `list_files` / `search_files` — read back
  after the user edits in Open Design Edit mode
- `get_project` — `previewUrl` for the user to review
- `list_projects` / `get_active_context` — find the project if needed

Never call `start_run`, `get_run`, `cancel_run`, `collect_brief`,
`confirm_brief`, or the Cloud sign-in tools. Do not import a folder and do not
call the daemon HTTP API. Copy `intelligence/fonts/*` into the Open Design
project and load them with CSS `@font-face` (relative `od-fonts/` URLs from
`layers-to-html.py`). If a brand face file is missing, disclose the editable
fallback and use the embedded-font SVG as the exact visual source.

## 4. Generate only the photography

Choose the provider before quoting cost: `--provider`, else `spec.json`
`"provider"`, else `IMAGE_PROVIDER`, else whichever single key is set.
Replicate is the default when both keys are set, or when no key is set. fal is
used when only `FAL_KEY` is set. Never switch provider after approval without a
fresh quote.

Use `python3 "${CLAUDE_SKILL_DIR}/generate-blank-ad.py"` once for each ratio. The prompt names the exact image
zone, crop, product/scale references and required clear space. Generate no ad copy,
UI, rules, dots, labels or placeholder text; printed packaging is the only permitted
text. End every prompt with: “Absolutely no typography anywhere except the printed
product packaging.”

Run `--estimate` first (no network, no key required). Default quality is `low`.
Edits stay low unless the user asks for `--final` / `--quality high`. On Replicate,
4:5 plates are generated at 1152×1536 and centre-cropped to 1152×1440; keep
essential content out of the outer ~3% top and bottom when prompting. 9:16 is
native at 1152×2048. That centre-crop is part of generation, not a design-tool fix.

Both providers send `quality` (`low`/`medium`/`high`) to GPT Image 2.5 Sunburst.

If the reference includes a person, preserve composition, pose, crop and lighting,
but prompt a different face, hair and styling. Keep the reference available when it
is necessary to retain the intended art direction; do not use retouching or overlays
to disguise a lookalike.

Desaturate every photo by 10% before review and delivery, consistently across the
whole plate.

## 5. Source QA and approval gate

Inspect each generated plate before any editable overlay work. Reject a plate that
has invented letters, an incorrect/mirrored/rotated/cropped pack, a wrong label
orientation, implausible physical scale, or a lookalike reference subject. Compare
pack scale to the hand/body reference, not just to empty space.

Measure visible—not frame—bounds. Reconcile text and image zones against the actual
plate. A failed crop or insufficient copy space requires the one permitted source
retry, not shrunken type or an overlay patch. If Replicate reports the failed call as
*not billed* (`failed` or `aborted`), that retry is still available.

Present the selected desaturated 4:5 and 9:16 source plates, their product bounds
and safe-zone results. Do not create any copy, UI, proof, offer or other editable
overlay until the user approves the applicable source plate.

### Delivery safety

- 4:5 critical-content zone: x54–1026, y54–1296.
- 9:16 critical-content zone: x90–990, y250–1570.
- In 9:16, reserve x840–1080, y560–1500 for platform controls. Keep a product,
  wordmark, CTA, proof and required labels out of it. The product/use moment belongs
  in x120–810, y430–1350.
- Minimum type at 1080px wide: headline 88px; statistic 96px; CTA/price 34px;
  subhead/proof 30px; label 28px; legal 20px. Simplify a narrow layout before
  reducing below these floors.

Never fix a 9:16 safe-zone failure by tiling, extending, offsetting or boxing a
finished plate in the Open Design HTML. Re-render the source with approval. Crop
inside an already seamless approved image zone only, with CSS `object-fit` /
`object-position` (or the equivalent on the HTML image zone).

## 6. Compose editable overlays

Run `python3 "${CLAUDE_SKILL_DIR}/compose-text.py"` once per approved variant. It outputs a flattened PNG, an
embedded-font editable SVG and `layers.json` with rendered line bounds and baselines.
Treat a shrink warning or a mobile-floor export block as a layout failure.

Then run `python3 "${CLAUDE_SKILL_DIR}/layers-to-html.py"` once per variant (and `--board` for the side-by-side
review file). It scales `layers.json` from plate pixels (for example 1152 wide)
to 1080-wide delivery: **4:5 = 1080×1350**, **9:16 = 1080×1920**. Crop inside an
approved image zone is CSS `object-fit` / `object-position`. Repeated components
share one CSS class.

For Open Design/SVG handoff, every text, UI, proof, rule, button and legal element
is its own editable layer (one HTML element per layer, `data-od-id` + readable
name). Use rendered line bounds and baselines to place text; do not blindly copy
a raster compositor's coordinates. Preserve separate lanes for prices, labels and
other independent elements.

If the brand face file is missing from the Open Design project, disclose the
editable fallback and use the embedded-font SVG as the exact visual source.
Create one correct repeated component as a shared CSS class, then audit font
size, leading, tracking, box dimensions, padding, rule weight and alignment
across all instances.

After the Open Design write gate, push the HTML, `od-fonts/` files and plate
PNGs with `create_artifact` / `write_file`. The PNG from `python3 "${CLAUDE_SKILL_DIR}/compose-text.py"` is the
exact-size delivery master. The user exports from Open Design only after hand
edits.

## 7. Final preflight

Review each ratio at actual delivery scale and beside the reference. Open Design
has no screenshot tool and no artboards. Run `python3 "${CLAUDE_SKILL_DIR}/layers-to-html.py" … --preflight`
on the scaled layer bounds, then give the user the Open Design `previewUrl`.
The design is a draft, not a completed handoff, if any check fails:

- reference-specific primitives are present and editable;
- repeated components read as one deliberate system;
- text, lines and anchors are clean, aligned, unclipped and non-overlapping;
- visible product bounds, 9:16 action rail and all live zones are clear;
- the image treatment remains intentionally seamless or intentionally panelled;
- mobile hierarchy and type floors pass independently for both ratios at
  1080-wide delivery size; and
- the paired HTML pages (and the review board) are in reference order, 4:5
  then 9:16.

Correct any failure, then re-review before calling the work complete.

## 8. Deliver

List both source plates, final PNGs, editable SVGs, `layers.json` files and the
Open Design HTML files (each ratio plus the review board). State font fallbacks,
intentional format omissions and any ratio-specific simplification. Offer free
copy/layout iteration separately from a cost-approved source re-render.
