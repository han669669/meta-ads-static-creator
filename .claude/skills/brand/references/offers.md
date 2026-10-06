# Offer Library — Format Reference

> **What this is.** The structure `/brand` writes to `intelligence/offers.md`.
> It is the **closed list of commercial offers** any downstream skill may put in
> front of a customer. `/meta-ads-static-creator` takes every offer from here and is
> forbidden from inventing one; any other copy draws on the same list.
> Derived during `/brand` from the product catalog, the live site (bundles,
> subscription terms, guarantees, shipping thresholds) and anything the user
> states directly. Fully editable, and expected to change as the brand's
> merchandising does.

Write clean markdown: `#` title, `##` sections, one `###` per offer. Every price,
code and term must be **real**. This file is the source of truth for what a
customer is promised, so an invented offer here becomes a promise the brand has
to honour.

---

## Output structure

```
# [Brand Name] — Offer Library

**The only offers that may appear on a page are the ones below.** Pages select
from this library; they never invent, modify, or combine offers outside the
stacking rules. [One line naming the brand-wide merchandising constraint from
brand-voice.md — e.g. offers are merchandised gently: no urgency, no countdowns,
no scarcity overlays, ever.]

## Offers

### O1 — [name], [$price]
- [What's in it, and what it would cost separately if it's a bundle.]
- **[Default offer for [context]]**: [one clause on why — AOV, one decision,
  gift-shaped, whatever is true.]

### O2 — [name]
- [Terms in plain language: price points, what's optional, how it cancels.]
- **[Default offer for [context]]**: [why]. [How to frame it, if the framing
  matters — e.g. as the brand's anti-waste stance rather than savings math.]

### O3 — [name] — code `[CODE]`
- [Eligibility and limits.] [When to use it, and how loudly.]

### O4 — [guarantee / risk reversal]
- [The promise, its window, and what the customer has to do.]
- **Not a discount — a risk reversal. Stackable with everything. Every landing
  page should carry it**, normally near the CTA and in the FAQ. [One clause on
  the objection it kills.]

## Stacking rules (hard constraints)

1. Never stack [X] + [Y] ([why — usually double-discounting]).
2. Never stack [X] + [Y].
3. [Which offer stacks with everything.]
4. One primary offer per page. The page's CTA commits to it; don't hedge with
   two competing offers above the fold.

## Selection heuristic

| Traffic / angle context | Primary offer |
|---|---|
| [Skeptical avatar name], proof-heavy page | [O1 with O4 prominent] |
| [Object/design angle, avatar name] | [O1 or O2, with the condition] |
| [Ease/speed angle, avatar name] | [O1, framed as ...] |
| [Single-product / cold traffic] | [single item + O4 loud, O3 if cold] |
```

---

## How to build it

**Source the offers, never imagine them.** In priority order: what the user
states directly; the live storefront (bundle products, subscription widgets,
guarantee and shipping pages, checkout terms); `products.json` for real prices
and SKUs. A brand with only single products and free shipping has a two-offer
library, and that is a complete answer.

**Give every offer an ID** (`O1`, `O2`, …). Downstream skills reference offers by
ID, so the IDs are stable once written — add new ones at the end rather than
renumbering.

**Mark the defaults.** For each offer, say which page context it is the default
for. This is what makes the selection heuristic mechanical instead of a judgment
call at build time.

**A risk reversal is not a discount.** Guarantees, free exchanges and trial
windows belong in the library as their own offers, marked stackable, because
almost every page should carry one.

**Stacking rules are hard constraints.** Write them as prohibitions, and cover
every pair that could plausibly be combined. A missing rule reads as permission.

**The selection heuristic maps avatars to offers.** Use the avatar names from
`intelligence/avatars.md` so the two files interlock — that table is what a page
build consults when it picks an offer for a given angle.

---

## Rules

- **Never invent an offer, a price, a discount code, or a guarantee.** Where the
  research is ambiguous — a bundle exists but its price isn't visible, a
  guarantee is implied but never stated — ask the user directly rather than
  filling the gap. This is the one file in `/brand`'s output where a plausible
  guess creates a legal and commercial liability, not just a bad document.
- **Every claim in an offer must be supportable**, same bar as
  `CLAUDE.md` guardrail 6.
- The brand-wide merchandising constraint from `brand-voice.md` (urgency,
  scarcity, discount register) is restated at the top so no page has to go
  looking for it.
- **No contrast frames** ("not a discount — a decision") in any offer copy — the
  same ban that governs ad copy. The `O4` line
  above is a structural note to the operator, not customer-facing copy.
