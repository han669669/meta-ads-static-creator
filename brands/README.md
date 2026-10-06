# Brands

Your brand folders go here, one folder per brand.

Don't create folders manually. Run `/brand` from this project root and Claude Code
will research the brand, build its operating system (visual guidelines, strategy,
positioning, voice, colour palette, typography), index the product catalog, and
scaffold the right folder structure for you. You can also say "add this to my brand
context" any time to fold a new product, asset, or fact into an existing brand — the
raw drop is archived under `intelligence/context-uploads/` and its substance is
folded into the brand's docs.

After `/brand` finishes you'll have:

```
brands/
  your-brand/
    intelligence/
      visual-guidelines.md   (visual identity + prompt modifier — brand-detection marker)
      brand-strategy.md      (personality, audience, competitive landscape)
      counter-positioning.md (counter-position + value proposition)
      brand-voice.md         (how the brand writes)
      brand-context.md       (one-page portable capsule for any AI tool)
      color-palette.json     (structured colour tokens)
      typography.json        (typefaces + design-system pointer)
      products.json          (product catalog index)
      product-images/        (flat: [slug]-01.jpg …)
      logos/
      fonts/
      context-uploads/       (raw archive of every "add this to my brand context" drop)
    generation/              (empty tree, reserved for downstream generation skills)
```

See the project root `CLAUDE.md` for the full convention list.
