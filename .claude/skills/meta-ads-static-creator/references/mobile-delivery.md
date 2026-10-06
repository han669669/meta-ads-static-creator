# Mobile delivery

Every static-ad run delivers two separately composed layouts: a 1080 × 1350 4:5 feed
ad and a 1080 × 1920 9:16 full-screen ad. These are delivery specifications, not
instructions to crop the same finished design.

## Live-content zones

Use these conservative zones unless the operator supplies a platform-specific
template with stricter requirements. Decorative imagery can bleed outside them;
essential headline, offer, product identifier, CTA, proof, labels and legal text
cannot.

| Variant | Canvas | Critical-content live zone | Purpose |
|---|---:|---|---|
| 4:5 feed | 1080 × 1350 | x 54–1026; y 54–1296 | Keeps important content clear of feed crops and edge compression. |
| 9:16 full screen | 1080 × 1920 | x 90–990; y 250–1570 | Keeps important content away from common top controls and lower captions/actions. |

The 9:16 zone is deliberately conservative. Do not place a headline, CTA, price,
code, disclaimer or product wordmark in its upper 250 px or lower 350 px. If a
platform template conflicts, use the stricter zone and record the source.

### Right-side controls and product-safe stage

On short-form platforms, the reaction/share rail commonly occupies the lower-right
side of the frame. Treat **x 840–1080, y 560–1500** as an interface exclusion area
when no platform template is supplied. It may contain incidental background texture,
but not a product pack, product wordmark, CTA, proof number or required label.

For an image-led 9:16 ad, keep the primary product or key product/use moment in the
central product-safe stage: **x 120–810, y 430–1350**. This is intentionally
stricter than the text live zone. Re-crop, translate or rescale the photography to
satisfy it; the editable type grid is not a compensating mechanism. Verify this
product-safe stage separately in the Open Design preview (there is no screenshot
tool).

## Mobile legibility gate

Judge at the intended delivered size, not while zoomed into the design tool. At the
1080 px export width:

| Role | Minimum | Normal target |
|---|---:|---:|
| Headline | 88 px | 96–128 px |
| Statistic | 96 px | 112–144 px |
| CTA / price / primary offer | 34 px | 38–48 px |
| Subhead / proof caption | 30 px | 32–40 px |
| Eyebrow / label | 28 px | 30–34 px |
| Legal qualifier | 20 px | 22–24 px |

These are floors, not an excuse to make every text element equally prominent. The
message should become simpler as the canvas narrows: preserve the hook, offer and
one proof point; remove redundant supporting copy before reducing type below the
floor. Legal copy may be compact, but it may not carry the sole disclosure of a
material offer or health claim.

## 9:16 composition

- Reserve a calm upper safe area; it should breathe, not hold a critical headline.
- Treat the middle live zone as the message stage. Put the main hook and one primary
  product/proof relationship here.
- Put only secondary visual texture in the lower interface area. If there is a CTA,
  place it in the lower part of the live zone, never flush to the bottom edge.
- Re-crop image zones for the tall frame. A product that sits well in a 4:5 may need
  a different scale or vertical location in 9:16; do not use letterboxing or leave
  a large accidental void.
- Review the 9:16 design at both full frame and mobile scale. Test the worst case:
  a long headline, the visible UI chrome and a fast-scrolling viewer. Check the
  product-safe stage and the right-side exclusion separately from the text zone.
