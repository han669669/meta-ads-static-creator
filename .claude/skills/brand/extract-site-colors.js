/*
 * extract-site-colors.js — brand-agnostic site colour sampler.
 *
 * Purpose: given a brand homepage already loaded in a real browser
 * (Claude-in-Chrome MCP), read the site's ACTUAL branding colours from computed
 * styles — not a guess. Tallies the colours the page really renders (weighted by
 * how much screen area each covers) and the colours of the elements that carry
 * brand meaning (header/nav, primary buttons/CTAs, links, headings, body
 * background), then proposes a role-mapped palette ready for color-palette.json.
 *
 * HOW TO USE:
 *   1. navigate the browser tab to the brand homepage; wait ~2-3s for load.
 *   2. Run this whole file's body via the javascript_tool on that tab.
 *      The last expression is the return value.
 *   3. Use the returned `suggested` palette as the starting point for
 *      color-palette.json (see the brand SKILL.md Step 2). Refine names/use, drop
 *      obvious junk, then write the file — the user can edit it afterward.
 *
 * Returns:
 *   {
 *     url,
 *     suggested: { background, primary, accent, neutral: [...], text },  // role guesses, hex
 *     ranked:   [ { hex, weight, kind } ],   // every distinct colour by visual dominance
 *     signals:  { headerBg, bodyBg, buttonBg, linkColor, headingColor }  // raw element reads
 *   }
 * Every hex is uppercase 6-digit (#RRGGBB). Treat `suggested` as a best-effort
 * first pass, never as ground truth.
 */

(() => {
  // --- colour helpers -------------------------------------------------------
  const toHex = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0").toUpperCase()

  function parseColor(str) {
    if (!str) return null
    const m = str.match(/rgba?\(([^)]+)\)/i)
    if (!m) return null
    const parts = m[1].split(",").map((s) => parseFloat(s.trim()))
    const [r, g, b] = parts
    const a = parts.length > 3 ? parts[3] : 1
    if ([r, g, b].some((v) => Number.isNaN(v))) return null
    if (a < 0.06) return null // fully/near transparent — ignore
    return { r, g, b, a, hex: `#${toHex(r)}${toHex(g)}${toHex(b)}` }
  }

  const lum = (c) => (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255
  const sat = (c) => {
    const mx = Math.max(c.r, c.g, c.b), mn = Math.min(c.r, c.g, c.b)
    return mx === 0 ? 0 : (mx - mn) / mx
  }
  const isGrayish = (c) => sat(c) < 0.12
  const key = (c) => c.hex

  // Merge near-identical hexes (within a small RGB distance) so #111 and #121212
  // don't both survive.
  function dist(a, b) {
    return Math.abs(a.r - b.r) + Math.abs(a.g - b.g) + Math.abs(a.b - b.b)
  }

  // --- gather weighted colours from every visible element -------------------
  const tally = new Map() // hex -> { color, weight }
  const add = (c, w) => {
    if (!c) return
    const e = tally.get(c.hex)
    if (e) e.weight += w
    else tally.set(c.hex, { color: c, weight: w })
  }

  const els = Array.from(document.body.querySelectorAll("*")).slice(0, 6000)
  const vw = window.innerWidth || 1280
  const vh = window.innerHeight || 900
  for (const el of els) {
    const rect = el.getBoundingClientRect()
    if (rect.width < 4 || rect.height < 4) continue
    // visual-area weight (cap so one huge hero doesn't dominate everything)
    const area = Math.min(rect.width, vw) * Math.min(rect.height, vh * 3)
    if (area <= 0) continue
    const cs = getComputedStyle(el)
    const bg = parseColor(cs.backgroundColor)
    if (bg) add(bg, area)                    // surfaces weighted by area
    const fg = parseColor(cs.color)
    const textLen = (el.textContent || "").trim().length
    if (fg && textLen > 0) add(fg, Math.min(textLen, 400) * 40) // text weighted by amount
    const bc = parseColor(cs.borderTopColor)
    if (bc && parseFloat(cs.borderTopWidth) > 0) add(bc, area * 0.05)
  }

  // collapse near-duplicates into the heavier representative
  const merged = []
  for (const entry of [...tally.values()].sort((a, b) => b.weight - a.weight)) {
    const near = merged.find((m) => dist(m.color, entry.color) <= 16)
    if (near) near.weight += entry.weight
    else merged.push({ ...entry })
  }
  merged.sort((a, b) => b.weight - a.weight)

  const ranked = merged.slice(0, 16).map((m) => ({
    hex: m.color.hex,
    weight: Math.round(m.weight),
    kind: isGrayish(m.color) ? (lum(m.color) > 0.5 ? "light-neutral" : "dark-neutral") : "chromatic",
  }))

  // --- read the brand-meaning signals directly ------------------------------
  const pick = (sel) => document.querySelector(sel)
  const csOf = (el, prop) => (el ? parseColor(getComputedStyle(el)[prop]) : null)

  const header = pick("header, [role=banner], nav, .header, #header, .navbar")
  const heading = pick("h1, h2, .hero h1, [class*=hero] h1")
  const link = pick("a[href]")
  // A "primary button"-ish element: button or CTA-styled link with a real bg.
  let button = null
  for (const b of Array.from(document.querySelectorAll("button, a, [role=button], input[type=submit]")).slice(0, 400)) {
    const bg = csOf(b, "backgroundColor")
    const r = b.getBoundingClientRect()
    if (bg && !isGrayish(bg) && r.width > 40 && r.height > 18) { button = b; break }
  }
  // fallback: any button with a non-transparent bg
  if (!button) {
    for (const b of Array.from(document.querySelectorAll("button, a[class*=btn], a[class*=button]")).slice(0, 400)) {
      const bg = csOf(b, "backgroundColor")
      const r = b.getBoundingClientRect()
      if (bg && r.width > 40 && r.height > 18) { button = b; break }
    }
  }

  const bodyBg = csOf(document.body, "backgroundColor") || csOf(document.documentElement, "backgroundColor")
  const signals = {
    headerBg: csOf(header, "backgroundColor")?.hex || null,
    bodyBg: bodyBg?.hex || null,
    buttonBg: csOf(button, "backgroundColor")?.hex || null,
    linkColor: csOf(link, "color")?.hex || null,
    headingColor: csOf(heading, "color")?.hex || null,
  }

  // --- map to roles (best-effort) -------------------------------------------
  const chromatic = merged.filter((m) => !isGrayish(m.color))
  const neutrals = merged.filter((m) => isGrayish(m.color))

  // background = dominant surface (prefer the actual body background)
  const background = signals.bodyBg || (neutrals[0]?.color.hex) || (ranked[0]?.hex) || null

  // accent = the saturated CTA/link colour, else most-dominant chromatic that
  // isn't the background.
  const accent =
    (button && csOf(button, "backgroundColor") && !isGrayish(csOf(button, "backgroundColor")) ? signals.buttonBg : null) ||
    (chromatic.find((m) => m.color.hex !== background)?.color.hex) ||
    signals.linkColor ||
    null

  // primary = the brand's dominant ink/identity colour: heading colour if strong,
  // else the heaviest dark neutral or the top chromatic that isn't the accent.
  const headingC = csOf(heading, "color")
  const primary =
    (headingC ? headingC.hex : null) ||
    (neutrals.find((m) => lum(m.color) < 0.4)?.color.hex) ||
    (chromatic.find((m) => m.color.hex !== accent)?.color.hex) ||
    null

  // text = the body text colour (heaviest text-weighted neutral) — used for the
  // neutral ramp / readability.
  const text = signals.headingColor || (neutrals.find((m) => lum(m.color) < 0.5)?.color.hex) || null

  // neutral ramp: distinct grays light→dark, up to 4
  const ramp = []
  for (const m of neutrals.sort((a, b) => lum(b.color) - lum(a.color))) {
    if (!ramp.some((h) => dist(parseColor(`rgb(${parseInt(h.slice(1,3),16)},${parseInt(h.slice(3,5),16)},${parseInt(h.slice(5,7),16)})`), m.color) <= 28)) {
      ramp.push(m.color.hex)
    }
    if (ramp.length >= 4) break
  }

  return {
    url: location.href,
    suggested: { background, primary, accent, neutral: ramp, text },
    ranked,
    signals,
  }
})()
