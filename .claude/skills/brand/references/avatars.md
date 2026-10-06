# Avatars — Format Reference

> **What this is.** The structure `/brand` writes to
> `intelligence/avatars.md`. Where `brand-strategy.md` sketches the target
> audience in the abstract, this file names the **three to five specific people**
> the brand sells to, in enough detail to write copy at one of them. It is the
> file `/meta-ads-static-creator` writes ad copy against, and the one that decides an
> ad's point of view. Derived during `/brand` from the research
> (reviews, ad-library comments, the About page, the brand's own segment
> language) and fully editable.

Write clean markdown: `#` title, `##` per avatar, tight bullets, real language.
**Quote the customer, never paraphrase them.** An avatar written in marketing
abstractions ("busy professionals seeking convenience") is useless downstream —
the pain words are what end up in headlines.

---

## Output structure

```
# [Brand Name] — Avatars

[N] named avatars. WinningAngle.avatar should resolve to one of these names; a
creative speaking to someone genuinely new is a finding worth reporting.

## 1. [The Descriptive Type] — "[Name]", [age range]

- **Morning:** [or **Life:** — one concrete vignette of the moment the product
  matters. A time, a place, an object. Never a demographic summary.]
- **Pain words (use verbatim):** ["exact phrases this person uses", "in their
  own words", lowercase if that's how they type it]
- **Wants:** [the outcome in their terms, not the product's features]
- **Objections:** ["the doubt, quoted" (→ the honest rebuttal); "the second
  doubt" (→ its rebuttal)]
- **Emotional driver:** [the feeling that moves the click — relief, control,
  taste, self-respect, desire — plus a clause on why]
- **Congruent ad POV:** [what an ad for this person leads with, and
  what it proves first]

## 2. [The Descriptive Type] — "[Name]", [age range]
[same six bullets]
```

---

## How to write each field

**The type + name.** A descriptive label ("The One-Step Minimalist", "The Cream
Convert") plus a first name in quotes. The name is how every downstream skill
refers to this person, so keep them distinct and unmistakable.

**Morning / Life.** One concrete scene. The test: could someone film it? "Out
the door in 20 minutes; owns makeup she never uses because it needs a mirror, a
brush, and ten minutes she doesn't have" passes. "Values efficiency" fails.

**Pain words.** The highest-value lines in the file — they become headlines
verbatim. Pull them from reviews, comments and support threads where possible.
Keep the customer's own register, including lowercase and fragments. Where the
research didn't surface real quotes, write the two or three most plausible and
**mark the file's gap** rather than presenting invention as evidence.

**Wants.** The outcome, in their language. Not "a refillable aluminium tube" but
"one object, thirty seconds, fingertips, done".

**Objections.** Each doubt quoted, each with a `→` rebuttal the brand can
actually support from `intelligence/`. These drive `primary_objection` on every
page and the FAQ that answers it. An objection with no honest rebuttal is worth
recording anyway — it tells the operator what not to promise.

**Emotional driver.** One phrase plus a clause. It sets the register of every
section written for this person.

**Congruent ad POV.** The one-line brief for an ad aimed here: what leads,
what proves, how much copy it needs.

---

## Rules

- **Three to five avatars.** Fewer than three and the segmentation isn't doing
  work; more than five and nobody can hold them in their head.
- **Avatars are distinct on *why*, not on demographics.** Two people the same
  age who buy for different reasons are two avatars. Two ages buying for one
  reason are one.
- **Never invent research.** Where a field rests on inference rather than a real
  quote or a real review, say so in the file. The whole system reads this file as
  fact, so a guess presented as a finding propagates into ad copy and page copy.
- **No contrast frames** ("that wasn't convenience, that was control") anywhere
  in the file — the same ban that governs ad copy.
- When a new avatar appears later — a winning ad speaks to someone unlisted —
  it's added here through the incremental "add this to my brand context" path,
  with the ad that revealed them noted.
