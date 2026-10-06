/*
 * extract-site-logo.js — brand-agnostic site logo extractor.
 *
 * Purpose: given a brand homepage already loaded in a real browser
 * (Claude-in-Chrome MCP), find the site's ACTUAL logo mark from the rendered
 * DOM. This is the browser-assisted fallback tier: it catches what
 * brand.py --fetch-logo (a plain HTTP fetch, tried first) can't reach — a
 * logo injected by client-side JS (React/Vue headers with nothing in the raw
 * HTML), an inline <svg> logo (no downloadable URL, must be serialized out of
 * the DOM), or a site that blocks server-side requests outright.
 *
 * HOW TO USE:
 *   1. navigate the browser tab to the brand homepage; wait ~2-3s for load.
 *   2. Run this whole file's body via the javascript_tool on that tab.
 *      The last expression is the return value.
 *   3. Save the result (see brand SKILL.md Step 2c):
 *        - suggested.type === 'svg'   → write suggested.value directly to
 *          logos/logo.svg with the Write tool — it's already markup, nothing
 *          to download.
 *        - suggested.type === 'image' → download it:
 *            brand.py --logo-url "<suggested.value>"
 *      If suggested picked the wrong element, look through `candidates` for
 *      the right one instead.
 *
 * Strategy (brand-agnostic), in priority order:
 *   1. The header's own "home link" (<a href="/"> or an href matching the
 *      site's own host, inside header/nav) — whatever mark it wraps (inline
 *      <svg> or <img>) IS the logo on nearly every site. This beats guessing
 *      from alt/class text alone.
 *   2. schema.org JSON-LD Organization.logo — a purpose-built field, when a
 *      site declares it.
 *   3. Any other <img> or inline <svg> in the header/nav whose alt/class/id
 *      mentions "logo".
 *   4. The largest declared favicon / apple-touch-icon, as a last resort — a
 *      square mark, not the full wordmark, but better than nothing.
 *
 * Returns:
 *   {
 *     url,
 *     suggested: { type: 'svg'|'image', value, source } | null,
 *     candidates: [ { type, value, source } ],  // every candidate found, ranked
 *     favicons:   [ { url, sizes, rel } ],
 *   }
 * `value` is either serialized SVG markup (type 'svg') or an absolute image
 * URL (type 'image'). Treat `suggested` as a best-effort first pick.
 */

(() => {
  const abs = (u) => { try { return new URL(u, location.href).href } catch { return null } }
  const serialize = (svg) => { try { return new XMLSerializer().serializeToString(svg) } catch { return null } }

  const header = document.querySelector("header, [role=banner], nav, .header, #header, .navbar") || document.body
  const host = location.host

  const looksLikeLogo = (el) => {
    const blob = `${el.getAttribute("alt") || ""} ${el.className || ""} ${el.id || ""} ${el.getAttribute("src") || ""}`.toLowerCase()
    return /logo/.test(blob)
  }

  const candidates = []
  const seen = new Set()
  const addImage = (url, source) => {
    const a = abs(url)
    if (!a || seen.has(a)) return
    seen.add(a)
    candidates.push({ type: "image", value: a, source })
  }
  const addSvg = (svgEl, source) => {
    const markup = serialize(svgEl)
    if (!markup || seen.has(markup)) return
    seen.add(markup)
    candidates.push({ type: "svg", value: markup, source })
  }

  // --- 1. the header's own home link ------------------------------------------
  let homeLink = null
  for (const a of header.querySelectorAll("a[href]")) {
    let hrefHost, path
    try { const u = new URL(a.href, location.href); hrefHost = u.host; path = u.pathname } catch { continue }
    if (hrefHost === host && (path === "/" || path === "")) { homeLink = a; break }
  }
  if (homeLink) {
    const svg = homeLink.querySelector("svg")
    if (svg) addSvg(svg, "header-home-link")
    const img = homeLink.querySelector("img")
    if (img) addImage(img.currentSrc || img.src, "header-home-link")
  }

  // --- 2. schema.org JSON-LD Organization.logo --------------------------------
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    let data
    try { data = JSON.parse(s.textContent) } catch { continue }
    const stack = [data]
    while (stack.length) {
      const o = stack.pop()
      if (!o || typeof o !== "object") continue
      if (Array.isArray(o)) { stack.push(...o); continue }
      if (o.logo) {
        const v = typeof o.logo === "string" ? o.logo : o.logo.url
        if (v) addImage(v, "json-ld")
      }
      for (const k in o) if (o[k] && typeof o[k] === "object") stack.push(o[k])
    }
  }

  // --- 3. any other header img/svg that says "logo" ----------------------------
  for (const svg of header.querySelectorAll("svg")) {
    if (looksLikeLogo(svg) || svg.closest("a, [class*=logo], [id*=logo]")) addSvg(svg, "header-svg")
  }
  for (const img of header.querySelectorAll("img")) {
    if (looksLikeLogo(img)) addImage(img.currentSrc || img.src, "header-img")
  }

  // --- 4. favicons (always collected; only a candidate as a last resort) ------
  const favicons = []
  for (const link of document.querySelectorAll('link[rel*="icon"]')) {
    const href = link.getAttribute("href")
    if (!href) continue
    favicons.push({ url: abs(href), sizes: link.getAttribute("sizes") || "", rel: (link.getAttribute("rel") || "").toLowerCase() })
  }
  favicons.sort((a, b) => {
    const sizeOf = (f) => parseInt(f.sizes.split("x")[0] || "0", 10) || 0
    return sizeOf(b) - sizeOf(a) || (b.rel.includes("apple") - a.rel.includes("apple"))
  })
  if (favicons.length) addImage(favicons[0].url, "favicon")

  return {
    url: location.href,
    suggested: candidates[0] || null,
    candidates,
    favicons,
  }
})()
