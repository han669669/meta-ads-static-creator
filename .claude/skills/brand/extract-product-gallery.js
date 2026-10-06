/*
 * extract-product-gallery.js — brand-agnostic product-gallery extractor.
 *
 * Purpose: given a product detail page (PDP) already loaded in a real browser
 * (Claude-in-Chrome MCP), pull EVERY product image for that product at high
 * resolution. This is the "open each image in a new tab and save it" workaround,
 * automated — used when a site blocks server-side scraping (Akamai/Cloudflare,
 * e.g. nike.com) but the image CDN itself is open to plain downloads.
 *
 * HOW TO USE (per product URL the user provides):
 *   1. navigate the browser tab to the product URL; wait for load.
 *   2. Run this whole file's body via the javascript_tool on that tab.
 *      It returns { name, count, image_urls } — top-level await is supported and
 *      the last expression is the return value.
 *   3. Append { name, product_url, image_urls } to products-to-ingest.json.
 *   4. After all products: brand.py --ingest-file products-to-ingest.json
 *      (the image CDN downloads fine server-side even when the page was walled).
 *
 * Strategy (brand-agnostic): scroll to trigger lazy-loading, gather candidates
 * from JSON-LD Product schema + og:image + every <img>/<picture>, keep only the
 * product's own CDN host, drop UI junk + video posters, then choose the gallery
 * by the strongest signal:
 *   (a) JSON-LD Product.image[] if it lists several, OR
 *   (b) the largest group of images that share a filename (a product's angles are
 *       usually the same asset name repeated — true on Nike-style CDNs where the
 *       browser route is actually needed; Shopify sites already return all images
 *       via brand.py --product-urls, so they rarely reach this script).
 * Dedupe is by the PHOTO id (the LAST uuid before the filename) — important on
 * Nike, whose URLs also carry a shared logo-overlay uuid that must be ignored.
 * High-res upgrade is per known CDN with a safe default.
 *
 * Verified live on nike.com (Akamai-walled): returns all 8 gallery images for the
 * ACG Radical AirFlow NXT colorway.
 */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let y = 0; y <= document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await sleep(120); }
  window.scrollTo(0, 0); await sleep(300);

  const abs = (u) => { try { return new URL(u, location.href).href; } catch { return null; } };
  const fromSrcset = (ss) => ss.split(',').map((s) => s.trim().split(/\s+/)[0]).filter(Boolean).pop();
  const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

  const name = (document.querySelector('meta[property="og:title"]') || {}).content
    || (document.querySelector('h1') || {}).textContent?.trim()
    || document.title;

  // ---- collect JSON-LD product images separately (canonical when present) ----
  const jsonld = new Set();
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    let data; try { data = JSON.parse(s.textContent); } catch { continue; }
    const stack = [data];
    while (stack.length) {
      const o = stack.pop();
      if (!o || typeof o !== 'object') continue;
      if (o.image) (Array.isArray(o.image) ? o.image : [o.image]).forEach((v) => {
        if (typeof v === 'string') jsonld.add(v); else if (v && v.url) jsonld.add(v.url);
      });
      for (const k in o) if (o[k] && typeof o[k] === 'object') stack.push(o[k]);
    }
  }

  // ---- collect every <img>/<source> candidate ----
  const cands = new Set();
  const og = (document.querySelector('meta[property="og:image"]') || {}).content;
  if (og) cands.add(og);
  for (const img of document.querySelectorAll('img')) {
    if (img.srcset) cands.add(fromSrcset(img.srcset));
    if (img.currentSrc) cands.add(img.currentSrc); else if (img.src) cands.add(img.src);
    if (img.dataset && (img.dataset.src || img.dataset.original)) cands.add(img.dataset.src || img.dataset.original);
  }
  for (const src of document.querySelectorAll('picture source[srcset]')) {
    const u = fromSrcset(src.srcset); if (u) cands.add(u);
  }

  const host = og && abs(og) ? new URL(abs(og)).host : null;
  const junk = /(sprite|icon|logo|swatch|placeholder|spinner|loading|flag|badge|\.svg($|\?)|^data:)/i;

  const upgrade = (u) => {
    if (/static\.nike\.com\/a\/images\//.test(u)) return u.replace(/\/a\/images\/[^/]+\//, '/a/images/t_PDP_1728_v1/'); // Nike
    if (/\/image\/upload\//.test(u)) return u.replace(/\/image\/upload\/[^/]*\//, '/image/upload/w_1800,q_auto/');       // Cloudinary
    if (/\/images\/stencil\/\d+x\d+\//.test(u)) return u.replace(/\/stencil\/\d+x\d+\//, '/stencil/1280x1280/');         // BigCommerce
    if (/cdn\.shopify\.com/.test(u) || /[?&]width=\d+/.test(u)) {                                                         // Shopify
      if (/[?&]width=\d+/.test(u)) return u.replace(/([?&]width=)\d+/, '$12048');
      return u.replace(/_(\d+x\d*|\d*x\d+)(?=\.[a-z]+)/i, '_2048x');
    }
    return u;
  };
  // dedupe key = PHOTO id (last uuid before filename), else the filename
  const photoKey = (u) => {
    const m = u.match(new RegExp('/(' + UUID.source + ')/[^/]+$', 'i'));
    if (m) return m[1].toLowerCase();
    return (u.split('?')[0].split('/').pop() || u).toLowerCase();
  };
  const filename = (u) => (u.split('?')[0].split('/').pop() || '').toLowerCase();

  const keep = (u) => u && !junk.test(u) && !/\/(videos?|video)\//.test(u) && (!host || (() => { try { return new URL(u).host === host; } catch { return false; } })());

  // (a) JSON-LD set
  const jsonldOut = new Map();
  for (let u of jsonld) { u = abs(u); if (!keep(u)) continue; const k = photoKey(u); if (!jsonldOut.has(k)) jsonldOut.set(k, upgrade(u)); }

  // (b) largest same-filename group among DOM candidates
  const groups = new Map(); // filename -> Map(photoKey -> hiResUrl)
  for (let u of cands) {
    u = abs(u); if (!keep(u)) continue;
    const fn = filename(u);
    if (!groups.has(fn)) groups.set(fn, new Map());
    const g = groups.get(fn);
    const k = photoKey(u);
    if (!g.has(k)) g.set(k, upgrade(u));
  }
  let largest = new Map();
  for (const g of groups.values()) if (g.size > largest.size) largest = g;

  // choose whichever signal yields more images
  const chosen = jsonldOut.size >= largest.size && jsonldOut.size > 0 ? jsonldOut : largest;
  return { name, count: chosen.size, image_urls: [...chosen.values()] };
})()
