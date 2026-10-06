/*
 * extract-site-fonts.js — brand-agnostic site typography sampler.
 *
 * Purpose: given a brand homepage already loaded in a real browser
 * (Claude-in-Chrome MCP), read the site's ACTUAL typefaces from computed styles —
 * not a guess. This is the same read the "WhatFont" extension performs (the real
 * rendered font-family on each element), but done across the whole page at once
 * and weighted by where each face is used: headings, body copy, nav, buttons.
 * It also harvests the hard evidence of which fonts are loaded — @font-face
 * declarations and the webfont provider links (Google Fonts, Adobe Fonts /
 * Typekit) — so the families can later be downloaded into the fonts/ folder.
 *
 * HOW TO USE:
 *   1. navigate the browser tab to the brand homepage; wait ~2-3s for load.
 *   2. Run this whole file's body via the javascript_tool on that tab.
 *      The last expression is the return value.
 *   3. Use the returned `suggested` role map as the starting point for
 *      typography.json (see the brand SKILL.md Step 2b). Cross-check `loaded`
 *      and `links` to record each family's source + downloadable URL.
 *
 * Returns:
 *   {
 *     url,
 *     suggested: { heading, body, accent, mono },  // role -> primary family name
 *     ranked:   [ { family, weight, role } ],       // every face by usage dominance
 *     signals:  { headingFont, bodyFont, navFont, buttonFont, linkFont },
 *     loaded:   [ { family, src, weights:[...] } ],  // @font-face the page declared
 *     links:    { google:[...], adobe:[...], other:[...] }  // webfont provider URLs
 *   }
 * Treat `suggested` as a best-effort first pass, never as ground truth — the
 * stack's FIRST family is reported (the face the browser actually paints when the
 * webfont is available), generic fallbacks (sans-serif, serif, etc.) stripped.
 */

(() => {
  // --- font-family helpers --------------------------------------------------
  const GENERICS = new Set([
    "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-sans-serif", "ui-serif", "ui-monospace", "ui-rounded", "math", "emoji",
    "-apple-system", "blinkmacsystemfont", "inherit", "initial", "unset",
  ])

  // First real (non-generic, non-system) family in a font-family stack.
  function firstFamily(stack) {
    if (!stack) return null
    for (let part of stack.split(",")) {
      part = part.trim().replace(/^["']|["']$/g, "")
      if (!part) continue
      if (GENERICS.has(part.toLowerCase())) continue
      return part
    }
    return null
  }

  const norm = (f) => (f ? f.toLowerCase() : f)

  // --- gather weighted faces from every visible element ---------------------
  const tally = new Map() // family -> { family, weight }
  const add = (family, w) => {
    if (!family) return
    const k = norm(family)
    const e = tally.get(k)
    if (e) e.weight += w
    else tally.set(k, { family, weight: w })
  }

  const els = Array.from(document.body.querySelectorAll("*")).slice(0, 6000)
  for (const el of els) {
    const rect = el.getBoundingClientRect()
    if (rect.width < 4 || rect.height < 4) continue
    const textLen = (el.textContent || "").trim().length
    if (textLen === 0) continue
    const cs = getComputedStyle(el)
    const fam = firstFamily(cs.fontFamily)
    if (!fam) continue
    // weight text by amount shown and by type size (display type carries identity)
    const px = parseFloat(cs.fontSize) || 16
    add(fam, Math.min(textLen, 400) * (px / 16))
  }

  const ranked = [...tally.values()]
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 12)
    .map((m) => ({ family: m.family, weight: Math.round(m.weight), role: null }))

  // --- read the brand-meaning signals directly ------------------------------
  const pick = (sel) => document.querySelector(sel)
  const famOf = (el) => (el ? firstFamily(getComputedStyle(el).fontFamily) : null)

  const heading = pick("h1, .hero h1, [class*=hero] h1, h2")
  const para = (() => {
    // the body paragraph with the most text wins
    let best = null, bestLen = 0
    for (const p of Array.from(document.querySelectorAll("p, li, article")).slice(0, 600)) {
      const len = (p.textContent || "").trim().length
      if (len > bestLen) { bestLen = len; best = p }
    }
    return best
  })()
  const nav = pick("header a, nav a, [role=banner] a")
  const button = pick("button, a[class*=btn], a[class*=button], [role=button]")
  const link = pick("a[href]")

  const signals = {
    headingFont: famOf(heading),
    bodyFont: famOf(para) || famOf(document.body),
    navFont: famOf(nav),
    buttonFont: famOf(button),
    linkFont: famOf(link),
  }

  // --- harvest hard evidence: @font-face + provider links --------------------
  const loadedMap = new Map() // family -> { family, src, weights:Set }
  for (const sheet of Array.from(document.styleSheets)) {
    let rules
    try { rules = sheet.cssRules } catch (e) { continue } // cross-origin sheet — skip
    if (!rules) continue
    for (const rule of Array.from(rules)) {
      if (rule.type !== CSSRule.FONT_FACE_RULE) continue
      const fam = (rule.style.getPropertyValue("font-family") || "").trim().replace(/^["']|["']$/g, "")
      if (!fam) continue
      const srcRaw = rule.style.getPropertyValue("src") || ""
      const urlMatch = srcRaw.match(/url\(([^)]+)\)/)
      const src = urlMatch ? urlMatch[1].replace(/^["']|["']$/g, "") : null
      const wght = (rule.style.getPropertyValue("font-weight") || "").trim()
      const k = norm(fam)
      const e = loadedMap.get(k) || { family: fam, src, weights: new Set() }
      if (src && !e.src) e.src = src
      if (wght) e.weights.add(wght)
      loadedMap.set(k, e)
    }
  }
  const loaded = [...loadedMap.values()].map((e) => ({
    family: e.family, src: e.src, weights: [...e.weights],
  }))

  const links = { google: [], adobe: [], other: [] }
  for (const l of Array.from(document.querySelectorAll('link[rel=stylesheet], link[as=font], link[rel=preconnect]'))) {
    const href = l.href || ""
    if (!href) continue
    if (/fonts\.googleapis\.com|fonts\.gstatic\.com/i.test(href)) links.google.push(href)
    else if (/use\.typekit\.net|typekit\.com|use\.fonts\.adobe\.com|fonts\.adobe\.com/i.test(href)) links.adobe.push(href)
    else if (/font|typeface/i.test(href)) links.other.push(href)
  }
  // dedupe
  for (const k of Object.keys(links)) links[k] = [...new Set(links[k])]

  // --- map to roles (best-effort) -------------------------------------------
  const suggested = {
    heading: signals.headingFont || (ranked[0] && ranked[0].family) || null,
    body: signals.bodyFont || (ranked[1] && ranked[1].family) || (ranked[0] && ranked[0].family) || null,
    accent: signals.buttonFont || signals.navFont || null,
    mono: (ranked.find((r) => /mono|code|consol|courier/i.test(r.family)) || {}).family || null,
  }
  // drop accent if it just duplicates heading or body
  if (suggested.accent && (norm(suggested.accent) === norm(suggested.heading) || norm(suggested.accent) === norm(suggested.body))) {
    suggested.accent = null
  }

  // annotate ranked roles for readability
  for (const r of ranked) {
    if (norm(r.family) === norm(suggested.heading)) r.role = "heading"
    else if (norm(r.family) === norm(suggested.body)) r.role = "body"
    else if (norm(r.family) === norm(suggested.accent)) r.role = "accent"
    else if (norm(r.family) === norm(suggested.mono)) r.role = "mono"
  }

  return { url: location.href, suggested, ranked, signals, loaded, links }
})()
