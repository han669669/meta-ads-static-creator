---
name: meta-ads-static-creator
description: "Create reference-led static ads with editable copy: generate only the photographic plate, then build and quality-check independently editable text and UI for 4:5 and 9:16 delivery."
image_model: GPT Image 2.5 Sunburst
group: Ads
summary: Reference-led static ads with editable copy, paired mobile formats, and source-to-overlay approval gates
version: 2.0.0
outputs: [meta-ads-static-creator]
inboxes:
  meta-ads-static-creator/ad-references: Ad references
requires: [FAL_KEY]
optional: [intelligence/fonts/*.ttf — the brand's real typefaces; degrades to a described fallback face]
metadata:
  author: "Joey Mulcahy"
  source: "https://joeymulcahy.com/"
  published-by: "han669669"
---

# Static Ads — editable text layer

Created by Joey Mulcahy — https://joeymulcahy.com/. Published here with his permission.

Build an ad from two independent parts: a text-free photographic plate and an
editable layout. Use this skill when the copy needs to be localised, tested or
edited after delivery. Create its declared inbox and output folders before use.

## Non-negotiables

- Every run delivers two independently composed variants: **4:5** (1080×1350) and
  **9:16** (1080×1920). Never crop one finished design into the other.
- All claims, offers and product facts must be supported by
  `brands/<brand>/intelligence/`. Do not infer them from the reference.
- Before any paid call, state the exact plates, call count, base cost and maximum
  cost including one quality retry per failed plate. Get explicit approval.
- Each failed plate may use one pre-authorised retry. If that fails too, show the
  better source; do not spend again without fresh approval.
- Do not generate merely to improve editable layout. Overlay iteration is free.

## 1. Read the brief and choose a route

Read the brand's visual guidelines, typography, colour, product and offer files.
Inspect the reference and record its format-defining primitives: image treatment,
search modules, ratings, testimonial cards, comparison states, labels, badges,
rules, buttons and proof. Every primitive is `photographic`, `editable`, or an
intentional documented omission. Do not replace a recognisable format device with
generic campaign copy.

Use **layout-first** for three or more text groups, offers, comparisons, statistics,
annotated images or precise editorial hierarchy. Build the complete editable
wireframe first; photography only fills named image zones. Decide before generation
whether each image zone is a deliberate panel or a seamless bleed, and preserve that
treatment through the run.

Use **plate-first** only for a simple image-led composition with one short headline
and generous, unambiguous copy space.

## 2. Specify the system

Write `brands/<brand>/generation/meta-ads-static-creator/<output-name>/spec.json` before
generating. It contains the reference and product inputs, supported copy, both
delivery variants, image zones, source prompt, format primitives and route.

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

Make one wireframe per ratio using the real copy and component systems. It must work
with images hidden: hierarchy, lanes, UI, proof and CTA remain clear and editable.
Build one correct repeated component and duplicate it; vary content and placement,
not type, padding, box size or line style unless the reference specifically calls
for it.

Review repeated components side by side. Equal roles must share their declared
system and align to intentional lanes or anchors—not convenient empty pixels. For
leader lines, use short, non-crossing routes to distinct anchors. Keep labels,
leaders and containers clear of faces, product labels and critical copy.

Do not put photography into the wireframe until it passes this review. Save the
wireframe screenshots with the run.

## 4. Generate only the photography

Use `generate-blank-ad.py` once for each ratio. The prompt names the exact image
zone, crop, product/scale references and required clear space. Generate no ad copy,
UI, rules, dots, labels or placeholder text; printed packaging is the only permitted
text. End every prompt with: “Absolutely no typography anywhere except the printed
product packaging.”

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
retry, not shrunken type or a Paper patch.

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
finished plate in Paper. Re-render the source with approval; Paper may only crop
inside an already seamless approved image zone.

## 6. Compose editable overlays

Run `compose-text.py` once per approved variant. It outputs a flattened PNG, an
embedded-font editable SVG and `layers.json` with rendered line bounds and baselines.
Treat a shrink warning or a mobile-floor export block as a layout failure.

For Paper/Figma/SVG handoff, every text, UI, proof, rule, button and legal element is
its own editable layer. Use rendered line bounds and baselines to place text; do not
blindly copy a raster compositor's coordinates. Preserve separate lanes for prices,
labels and other independent elements.

In Paper, look up the font before styling. If the brand face is unavailable, disclose
the editable fallback and use the embedded-font SVG as the exact visual source; ask
before installing a licensed font. Create one correct repeated component, duplicate
it, then audit font size, leading, tracking, box dimensions, padding, rule weight
and alignment across all instances.

## 7. Final preflight

Review each ratio at actual delivery scale and beside the reference. The design is a
draft, not a completed handoff, if any check fails:

- reference-specific primitives are present and editable;
- repeated components read as one deliberate system;
- text, lines and anchors are clean, aligned, unclipped and non-overlapping;
- visible product bounds, 9:16 action rail and all live zones are clear;
- the image treatment remains intentionally seamless or intentionally panelled;
- mobile hierarchy and type floors pass independently for both ratios; and
- paired artboards are adjacent and in reference order.

Take a final screenshot of each artboard and the full canvas, correct any failure,
then re-review before calling the work complete.

## 8. Deliver

List both source plates, final PNGs, editable SVGs and `layers.json` files. State
font fallbacks, intentional format omissions and any ratio-specific simplification.
Offer free copy/layout iteration separately from a cost-approved source re-render.
