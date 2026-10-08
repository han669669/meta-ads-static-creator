#!/usr/bin/env python3
"""
brand.py — Build a brand's product catalog (and collect logos + open-license
webfonts).

Scrapes product images from a brand website, writing them FLAT into
`product-images/` (`[slug]-01.jpg`, `[slug]-02.jpg`, …) and indexing every
product in `products.json` — the brand's catalog. Tries Shopify's products.json
API first, falls back to HTML scraping, and supports a WebFetch/browser ingest
path for bot-protected sites.

Flat image naming is deliberate: every skill reads `product-images/` as a flat
folder and groups variants by their shared leading filename tokens, so
`camp-shirt-01.jpg` and `camp-shirt-02.jpg` group as one product. Per-product
subfolders would break that grouping.

When --products is given, those named products are prioritised and downloaded
first, then the top best-sellers fill the remaining slots.

--index rebuilds products.json from whatever is actually on disk in
`product-images/` (catches manually dropped files), preserving any catalog
enrichment (price, category, description, claims) already recorded for a product.

--fetch-logo fetches the brand's homepage HTML and downloads its logo into
logos/ — tries schema.org JSON-LD Organization.logo, then a header/nav <img>,
then the largest declared favicon, in that priority order. HTTP-only, no
browser needed; when the header is client-rendered or the logo is inline SVG,
use the browser fallback (extract-site-logo.js) and hand its result to
--logo-url.

--fetch-fonts resolves Google Fonts family names to their font files (ttf/woff,
whichever the open Google Fonts CSS2 endpoint serves, no API key) and saves them
into the fonts/ folder — the concrete collection step for typography discovered
during brand setup.

--save-context archives raw "add this to my brand context" source material —
a guidelines PDF, a positioning deck, a screenshot, any dropped document — into
intelligence/context-uploads/ as dated, collision-safe copies, so the brand keeps
an audit trail of everything it was built from even as each drop's substance is
folded into the derived docs.

--scaffold creates a brand's folder tree — both compartments, intelligence/ and
generation/ — and is the one command that runs before the brand folder exists,
from the project root rather than from inside intelligence/.

Every other command runs from inside the intelligence/ folder so outputs land in
the right place.

Usage:
  # Create the folder tree first, from the project root:
  python3 .claude/skills/brand/brand.py --scaffold "Blue Elephant"

  # Then, from ./brands/[brand-name]/intelligence:

  # Download top best-sellers only:
  python3 ../../../.claude/skills/brand/brand.py --scrape https://brand.com

  # Download specific products by exact URL (preferred):
  python3 ../../../.claude/skills/brand/brand.py --scrape https://brand.com \
      --product-urls "https://brand.com/products/camp-shirt,https://brand.com/products/chino"

  # WebFetch/browser fallback for bot-protected sites (Akamai/Cloudflare, e.g. Nike):
  # gather names + CDN image URLs, write them to a JSON file, then:
  python3 ../../../.claude/skills/brand/brand.py --ingest-file products-to-ingest.json

  # Rebuild the catalog index from images already on disk:
  python3 ../../../.claude/skills/brand/brand.py --index

  # Fetch the site's logo into logos/ (JSON-LD → header <img> → favicon):
  python3 ../../../.claude/skills/brand/brand.py --fetch-logo https://brand.com

  # Download a logo URL already found via the browser fallback or WebFetch:
  python3 ../../../.claude/skills/brand/brand.py --logo-url "https://brand.com/logo.svg"

  # Download open-license fonts the site uses into fonts/ (Google Fonts families):
  python3 ../../../.claude/skills/brand/brand.py --fetch-fonts "Inter,Playfair Display"

  # Archive dropped brand-context files into context-uploads/ (the raw-input trail):
  python3 ../../../.claude/skills/brand/brand.py --save-context "~/Downloads/1720-guidelines.pdf" --move

Outputs:
  ./product-images/[slug]-01.jpg  [slug]-02.jpg ...   (flat)
  ./products.json — product catalog { brand, updated, products: [...] }
  ./logos/logo.[ext] (+ logo-icon.[ext] if a distinct favicon was also found)
  ./fonts/[family]/[family]-[weight].ttf|.woff — downloaded open-license fonts
  ./context-uploads/[YYYY-MM-DD]-[slug].[ext] — archived raw context drops
"""

import argparse
import html
import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError as exc:
    raise SystemExit(
        f"Error: missing dependency '{exc.name}'.\n"
        "Install the project requirements first, from the project root:\n"
        "  pip install -r requirements.txt"
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Logos are far more often vector than product photos, and favicons are
# sometimes served as .ico — both are worth keeping, unlike for product images.
LOGO_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}

# Enrichment fields carried on every catalog entry. brand.py fills what the
# source exposes (Shopify gives price/category/description); the /brand skill
# enriches the rest (claims, better category) by reading the product page.
ENRICH_FIELDS = ("price", "category", "description", "claims")

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# A brand folder has two compartments: intelligence/ (what /brand writes) and
# generation/ (what every other skill produces from it). --scaffold creates both
# up front, so a brand's shape on day one matches its shape after fifty shoots.
INTELLIGENCE_DIRS = (
    "product-images",
    "logos",
    "fonts",
    # Raw-input archive: every "add this to my brand context" drop (guidelines
    # PDF, positioning deck, screenshot, stray fact) is preserved here verbatim,
    # even as its substance is folded into the derived docs. See save_context().
    "context-uploads",
)

# There is no list of skills or output folders here. Each skill declares its own
# outputs and inboxes in its SKILL.md frontmatter, and everything below —
# scaffold, validate, docs — derives from those declarations. Drop a skill
# folder in and it is part of the system; delete one and nothing else notices.
#
# The frontmatter is a deliberately restricted YAML subset so it can be parsed
# with no dependency: single-line `key: value` scalars, inline string lists
# `key: [a, b]`, and one level of nested `path: Label` map under a bare `key:`
# line. --validate enforces that contract, so run it before packaging.
#
# Declaration keys (paths are relative to brands/<brand>/generation/):
#   outputs: [folder, ...]        folders the skill writes into
#   inboxes:                      folders a human drops files into, with labels
#     folder/subfolder: Label
#   requires: [FAL_KEY, ...]      hard needs the skill checks before running
#   optional: [shopify-cli, ...]  soft needs the skill degrades without
#   version, group, summary       packaging, docs table grouping, docs one-liner
FRONTMATTER_KEYS = {
    "name", "description", "version", "group", "summary",
    "image_model", "video_model", "outputs", "inboxes", "requires", "optional",
    "metadata", "allowed-tools",
}


def _skills_root() -> Path:
    """The .claude/skills/ folder this file lives under."""
    return Path(__file__).resolve().parents[1]


def _parse_frontmatter(text: str):
    """Parse a SKILL.md's frontmatter (the restricted subset above).

    Returns (data, errors). Anything outside the subset — multi-line scalars,
    deeper nesting, tabs — is an error, not a guess.
    """
    data, errors = {}, []
    if not text.startswith("---\n"):
        return data, ["no frontmatter block (file must start with ---)"]
    body = text[4:]
    end = body.find("\n---")
    if end == -1:
        return data, ["frontmatter never closes (missing ---)"]
    current_map = None
    for raw in body[:end].split("\n"):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw:
            errors.append(f"tab character in line: {raw.strip()[:40]!r}")
            continue
        if raw.startswith("  "):
            if current_map is None:
                errors.append(f"indented line outside a map: {raw.strip()[:40]!r}")
                continue
            key, sep, val = raw.strip().partition(":")
            if not sep or not val.strip():
                errors.append(f"map entry needs 'path: Label': {raw.strip()[:40]!r}")
                continue
            current_map[key.strip()] = val.strip()
            continue
        key, sep, val = raw.partition(":")
        key, val = key.strip(), val.strip()
        if not sep or not key:
            errors.append(f"not a 'key: value' line: {raw.strip()[:40]!r}")
            continue
        if not val:
            current_map = {}
            data[key] = current_map
            continue
        current_map = None
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            data[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        else:
            data[key] = val
    return data, errors


def load_skill_manifests():
    """Read every skill's SKILL.md declaration.

    Returns {skill_folder_name: manifest}. Each manifest carries the parsed
    frontmatter plus '_errors' (parse or contract problems, empty when clean).
    A broken SKILL.md yields a manifest with errors, never a crash — one bad
    skill must not take the system down.
    """
    manifests = {}
    for skill_dir in sorted(_skills_root().iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.exists():
            continue
        try:
            data, errors = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        except OSError as e:
            data, errors = {}, [f"unreadable: {e}"]
        data.setdefault("outputs", [])
        data.setdefault("inboxes", {})
        data.setdefault("requires", [])
        manifests[skill_dir.name] = data
        data["_errors"] = errors
    return manifests


def generation_dirs(manifests=None):
    """Every generation/ folder the installed skills declare, scaffold-ready.

    Derived, ordered (each skill's outputs, then its inboxes), deduped. Inboxes
    exist here so they're droppable before the skill has ever run. packshots/
    takes its product-references/ per output (packshots/[name]/product-references/),
    so that one is created by the skill at run time, not scaffolded.
    """
    manifests = manifests if manifests is not None else load_skill_manifests()
    dirs = []
    for name in sorted(manifests):
        m = manifests[name]
        for d in list(m.get("outputs", [])) + list(m.get("inboxes", {})):
            if d and d not in dirs:
                dirs.append(d)
    return tuple(dirs)


def validate_skills() -> bool:
    """Check every skill's declaration. Run before packaging a release.

    A problem here is a typo waiting to become a junk folder or an invisible
    output — this is where it gets caught instead. Prints a report; returns
    True when everything is clean.
    """
    manifests = load_skill_manifests()
    problems = []
    outputs_seen = {}

    for name, m in manifests.items():
        where = f"{name}/SKILL.md"
        for e in m["_errors"]:
            problems.append(f"{where}: {e}")
        if m.get("name") != name:
            problems.append(f"{where}: frontmatter name {m.get('name')!r} != folder name {name!r}")
        if not m.get("description"):
            problems.append(f"{where}: missing description")
        version = m.get("version", "")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
            problems.append(f"{where}: version {version!r} is not MAJOR.MINOR.PATCH")
        if not m.get("summary"):
            problems.append(f"{where}: missing summary (used by --docs)")
        if not m.get("group"):
            problems.append(f"{where}: missing group (used by --docs)")
        for key in m:
            if not key.startswith("_") and key not in FRONTMATTER_KEYS:
                problems.append(f"{where}: unknown key {key!r} — typo, or extend FRONTMATTER_KEYS")
        if not isinstance(m.get("outputs"), list):
            problems.append(f"{where}: outputs must be a list, e.g. outputs: [static-ads]")
            continue
        for d in m["outputs"]:
            if not re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)?", d):
                problems.append(f"{where}: output {d!r} is not a plain kebab-case folder path")
            if d in outputs_seen:
                problems.append(f"{where}: output {d!r} already claimed by {outputs_seen[d]}")
            outputs_seen[d] = name
        for d in m.get("inboxes", {}):
            top = d.split("/")[0]
            if top not in m["outputs"]:
                problems.append(
                    f"{where}: inbox {d!r} is not under one of this skill's outputs {m['outputs']}"
                )

    n = len(manifests)
    if problems:
        print(f"✗ {len(problems)} problem(s) across {n} skills:\n")
        for p in problems:
            print(f"  - {p}")
        return False
    print(f"✓ {n} skills, all declarations valid")
    print(f"  {len(outputs_seen)} output folders, no collisions")
    return True


# Cosmetic ordering for the generated docs table. Unknown groups append at the
# end alphabetically — a new skill with a new group still shows up.
DOCS_GROUP_ORDER = ("Core", "Shopify", "Models & styling", "Product", "UGC", "Ads", "Video editing")

DOCS_MARK_TABLE = ("<!-- skills-table:start -->", "<!-- skills-table:end -->")
DOCS_MARK_COUNT = ("<!-- skills-count:start -->", "<!-- skills-count:end -->")

_COUNT_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
).split()


def _replace_between(text: str, start: str, end: str, replacement: str, path) -> str:
    i, j = text.find(start), text.find(end)
    if i == -1 or j == -1 or j < i:
        raise SystemExit(f"{path}: markers {start} … {end} missing or out of order")
    return text[: i + len(start)] + "\n" + replacement + "\n" + text[j:]


def generate_docs() -> None:
    """Rewrite the generated blocks in README.md and CLAUDE.md.

    Everything between the skills-table markers becomes a grouped table built
    from each skill's own frontmatter; everything between the skills-count
    markers becomes the one-line inventory. Prose outside the markers is
    never touched. Refuses to run while --validate fails: generated docs
    from broken declarations would launder the breakage into the README.
    """
    if not validate_skills():
        raise SystemExit("Fix the declarations above, then rerun --docs.")
    manifests = load_skill_manifests()

    groups = {}
    for name, m in sorted(manifests.items()):
        groups.setdefault(m.get("group", "Other"), []).append(m)
    ordered = [g for g in DOCS_GROUP_ORDER if g in groups]
    ordered += sorted(g for g in groups if g not in DOCS_GROUP_ORDER)

    rows = ["| | |", "|---|---|"]
    for g in ordered:
        skills = groups[g]
        if len(skills) > 1:
            rows.append(f"| **{g}** | {' · '.join('`/' + s['name'] + '`' for s in skills)} |")
        for s in skills:
            label = f"**`/{s['name']}`**" if len(skills) == 1 else f"↳ `/{s['name']}`"
            rows.append(f"| {label} | {s['summary']} |")
    table = "\n".join(rows)

    n = len(manifests)
    n_word = _COUNT_WORDS[n].capitalize() if n < len(_COUNT_WORDS) else str(n)
    count = f"{n_word} skills. One brand context every one of them reads."

    root = _project_root()
    for fname in ("README.md", "CLAUDE.md"):
        path = root / fname
        text = path.read_text(encoding="utf-8")
        if DOCS_MARK_TABLE[0] in text:
            text = _replace_between(text, *DOCS_MARK_TABLE, replacement=table, path=fname)
        if DOCS_MARK_COUNT[0] in text:
            text = _replace_between(text, *DOCS_MARK_COUNT, replacement=count, path=fname)
        path.write_text(text, encoding="utf-8")
        print(f"✓ {fname} regenerated")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()


def _slugify(text: str, max_len: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len]


def _project_root() -> Path:
    """Project root, resolved from this file's own location.

    brand.py lives at .claude/skills/brand/brand.py, so parents[3] is the root.
    --scaffold runs before the brand folder exists and therefore can't use the
    cwd-relative paths the other commands rely on.
    """
    return Path(__file__).resolve().parents[3]


def _get_image_ext(url: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    return ext if ext in IMAGE_EXTENSIONS else ".jpg"


def _get_logo_ext(url: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    return ext if ext in LOGO_EXTENSIONS else ".png"


def _abs_url(url: str, base_url: str) -> str:
    """Resolve a possibly-relative URL (//host/path, /path, or bare) against the
    site's base_url, the same scheme used ad hoc elsewhere in this file."""
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{base_url}{url}"
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return f"{base_url}/{url.lstrip('/')}"
    return url


def _strip_html(text: str, max_len: int = 320) -> str:
    """Turn a product body_html into a short plain-text description."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].rstrip()


def _download_image_file(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, timeout=30, headers=SCRAPE_HEADERS)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    Download failed: {e}")
        return False


def _fuzzy_match(name: str, filters: List[str]) -> bool:
    name_lower = name.lower()
    return any(f.lower() in name_lower for f in filters)


def _blank_entry() -> dict:
    return {
        "name": "",
        "slug": "",
        "images": [],
        "product_url": "",
        "price": None,
        "category": None,
        "description": "",
        "claims": [],
        "source": "scraped",
        "added": _today(),
    }


def _save_images_flat(slug: str, image_urls: List[str], images_dir: Path) -> List[str]:
    """Download images FLAT as `[slug]-NN.ext` directly inside product-images/.
    Returns the list of saved filenames."""
    saved: List[str] = []
    for idx, img_url in enumerate(image_urls, 1):
        ext = _get_image_ext(img_url)
        filename = f"{slug}-{idx:02d}{ext}"
        dest = images_dir / filename
        if dest.exists():
            print(f"    {filename} (already exists, skipping)")
            saved.append(filename)
            continue
        if _download_image_file(img_url, dest):
            print(f"    ✓ {filename}")
            saved.append(filename)
    return saved


def _unique_slug(base_slug: str, seen: dict) -> str:
    if base_slug in seen:
        seen[base_slug] += 1
        return f"{base_slug}-{seen[base_slug]}"
    seen[base_slug] = 0
    return base_slug


def _merge_entry(old: dict, new: dict) -> dict:
    """Merge a freshly scraped entry over an existing one, preserving catalog
    enrichment the skill added (claims, category, description, price, product_url)
    when the new source leaves those empty."""
    merged = dict(new)
    for field in ENRICH_FIELDS + ("product_url",):
        new_val = new.get(field)
        old_val = old.get(field)
        empty = new_val in (None, "", [])
        if empty and old_val not in (None, "", []):
            merged[field] = old_val
    # Keep the earliest 'added' date if we have it.
    if old.get("added"):
        merged["added"] = old["added"]
    return merged


def _write_manifest(new_entries: List[dict], brand: Optional[str] = None) -> None:
    """Merge new entries into products.json by slug and write it back, preserving
    the top-level { brand, updated, products } shape and any existing enrichment."""
    manifest_path = Path("products.json")
    existing_products: List[dict] = []
    existing_brand = brand
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            existing_products = data.get("products", [])
            existing_brand = brand or data.get("brand")
        except Exception:
            pass

    by_slug = {p.get("slug"): p for p in existing_products}
    for entry in new_entries:
        slug = entry["slug"]
        if slug in by_slug:
            by_slug[slug] = _merge_entry(by_slug[slug], entry)
        else:
            by_slug[slug] = entry

    merged = list(by_slug.values())
    out = {
        "brand": existing_brand or "",
        "updated": _today(),
        "products": merged,
    }
    with open(manifest_path, "w") as f:
        json.dump(out, f, indent=2)


# ---------------------------------------------------------------------------
# Direct URL scraper (exact product pages)
# ---------------------------------------------------------------------------

def scrape_product_by_url(product_url: str, base_url: str) -> Optional[dict]:
    """Scrape a single product page by its direct URL. Tries Shopify JSON first
    (which also yields price + description + category), falls back to og: tags."""
    product_url = product_url.strip().rstrip("/")
    parsed = urlparse(product_url)

    # Shopify: /products/[handle].json returns all images + metadata
    shopify_match = re.search(r"/products/([^/?#]+)", parsed.path)
    if shopify_match:
        handle = shopify_match.group(1)
        try:
            api_url = f"{base_url}/products/{handle}.json"
            resp = requests.get(api_url, timeout=15, headers=SCRAPE_HEADERS)
            if resp.ok:
                p = resp.json().get("product", {})
                images = p.get("images", [])
                if images:
                    variants = p.get("variants", [])
                    price = variants[0].get("price") if variants else None
                    return {
                        "name": p["title"],
                        "image_urls": [re.sub(r"\?.*$", "", img["src"]) for img in images],
                        "product_url": product_url,
                        "price": price,
                        "category": p.get("product_type") or None,
                        "description": _strip_html(p.get("body_html", "")),
                    }
        except Exception:
            pass

    # Fallback: parse og:title + og:image from the page
    try:
        resp = requests.get(product_url, timeout=15, headers=SCRAPE_HEADERS)
        if not resp.ok:
            print(f"  ✗ {product_url} ({resp.status_code})")
            return None

        name_match = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
            resp.text, re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:title["\']',
            resp.text, re.IGNORECASE,
        )
        name = name_match.group(1).strip() if name_match else product_url.rstrip("/").split("/")[-1]

        img_match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']',
            resp.text, re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:image["\']',
            resp.text, re.IGNORECASE,
        )
        if not img_match:
            print(f"  ✗ No image found at {product_url}")
            return None

        img_url = img_match.group(1).strip()
        if img_url.startswith("//"):
            img_url = f"https:{img_url}"
        elif img_url.startswith("/"):
            img_url = f"{base_url}{img_url}"
        img_url = re.sub(r"\?.*$", "", img_url)

        return {
            "name": name,
            "image_urls": [img_url],
            "product_url": product_url,
        }
    except Exception as e:
        print(f"  ✗ Error fetching {product_url}: {e}")
        return None


def scrape_specific_product_urls(site_url: str, product_urls: List[str]) -> List[dict]:
    """Scrape only the specific product page URLs provided. No full site scan.
    Merges results into an existing products.json if one already exists."""
    site_url = site_url.rstrip("/")
    parsed = urlparse(site_url)
    if not parsed.scheme:
        site_url = f"https://{site_url}"
        parsed = urlparse(site_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    images_dir = Path("product-images")
    images_dir.mkdir(exist_ok=True)

    print(f"\nScraping {len(product_urls)} specific product(s) from {base_url}...\n")

    manifest: List[dict] = []
    seen_slugs: dict = {}

    for product_url in product_urls:
        product = scrape_product_by_url(product_url, base_url)
        if not product:
            continue

        slug = _unique_slug(_slugify(product["name"]), seen_slugs)
        img_count = len(product["image_urls"])
        print(f"  {product['name']} ({img_count} image{'s' if img_count != 1 else ''}) → product-images/{slug}-NN")

        saved = _save_images_flat(slug, product["image_urls"], images_dir)
        if saved:
            entry = _blank_entry()
            entry.update({
                "name": product["name"],
                "slug": slug,
                "images": saved,
                "product_url": product_url,
                "price": product.get("price"),
                "category": product.get("category"),
                "description": product.get("description", ""),
                "source": "scraped",
            })
            manifest.append(entry)
        print()

    if not manifest:
        print("\n  ✗ No product images were saved — the site likely blocked automated")
        print("    access (Akamai / Cloudflare bot protection) or isn't Shopify.")
        print("    Fallback: gather each product's name + image URLs with the WebFetch")
        print("    tool, then download them with:  brand.py --ingest-file products-to-ingest.json")
        return []

    _write_manifest(manifest)
    total_images = sum(len(p["images"]) for p in manifest)
    print(f"  {len(manifest)} product(s), {total_images} total image(s) saved to ./product-images/")
    print(f"  Catalog → ./products.json\n")
    return manifest


# ---------------------------------------------------------------------------
# Ingest pre-extracted image URLs (WebFetch/browser fallback for walled sites)
# ---------------------------------------------------------------------------

def ingest_products(products: List[dict]) -> List[dict]:
    """Download pre-extracted product images from supplied CDN URLs and merge into
    products.json. No HTML fetching — the image URLs are passed in directly.

    This is the fallback for sites that block automated HTML access (Akamai /
    Cloudflare bot protection, e.g. Nike). The page is protected, but the image
    CDN almost never is: gather each product's name + image URLs with WebFetch or
    the browser gallery extractor, then ingest them here.

    Each product entry: {"name": str, "image_urls": [str, ...], "product_url": str?}.
    Image URLs are downloaded verbatim (query params preserved — many CDNs need
    them for sizing or signing), so do not strip them upstream.
    """
    images_dir = Path("product-images")
    images_dir.mkdir(exist_ok=True)

    print(f"\nIngesting {len(products)} product(s) from supplied image URLs...\n")

    manifest: List[dict] = []
    seen_slugs: dict = {}

    for product in products:
        name = (product.get("name") or "").strip()
        image_urls = [u.strip() for u in (product.get("image_urls") or []) if u and u.strip()]
        if not name or not image_urls:
            print(f"  ✗ Skipping entry — missing name or image_urls: {product!r}")
            continue

        slug = _unique_slug(_slugify(name), seen_slugs)
        img_count = len(image_urls)
        print(f"  {name} ({img_count} image{'s' if img_count != 1 else ''}) → product-images/{slug}-NN")

        saved = _save_images_flat(slug, image_urls, images_dir)
        if saved:
            entry = _blank_entry()
            entry.update({
                "name": name,
                "slug": slug,
                "images": saved,
                "product_url": product.get("product_url", ""),
                "price": product.get("price"),
                "category": product.get("category"),
                "description": product.get("description", ""),
                "source": "ingested",
            })
            manifest.append(entry)
        print()

    if not manifest:
        print("\n  Warning: no product images were saved (all downloads failed).")
        return []

    _write_manifest(manifest)
    total_images = sum(len(p["images"]) for p in manifest)
    print(f"  {len(manifest)} product(s), {total_images} total image(s) saved to ./product-images/")
    print(f"  Catalog → ./products.json\n")
    return manifest


# ---------------------------------------------------------------------------
# Shopify API scraper
# ---------------------------------------------------------------------------

def _try_shopify_api(base_url: str, max_products: int = 100) -> tuple:
    """
    Fetch all products from Shopify API (sorted by best-selling).
    Returns (products, block_reason) where block_reason is None on success or a
    human-readable string describing why the request failed.
    """
    api_url = f"{base_url}/products.json?sort_by=best-selling&limit={max_products}"
    try:
        resp = requests.get(api_url, timeout=15, headers=SCRAPE_HEADERS)
        if not resp.ok:
            return [], None  # Not Shopify — not a block, just not supported
        data = resp.json()
        products = []
        for p in data.get("products", []):
            images = p.get("images", [])
            if not images:
                continue
            image_urls = [re.sub(r"\?.*$", "", img["src"]) for img in images]
            variants = p.get("variants", [])
            products.append({
                "name": p["title"],
                "handle": p["handle"],
                "image_urls": image_urls,
                "product_url": f"{base_url}/products/{p['handle']}",
                "price": variants[0].get("price") if variants else None,
                "category": p.get("product_type") or None,
                "description": _strip_html(p.get("body_html", "")),
            })
        return products, None
    except Exception:
        return [], None


# ---------------------------------------------------------------------------
# HTML fallback scraper
# ---------------------------------------------------------------------------

def _try_html_scrape(base_url: str, site_url: str, max_products: int) -> tuple:
    """Fallback HTML scraper using og:image and og:title — one image per product.
    Returns (products, block_reason) where block_reason describes the first blocking
    HTTP error encountered, or None if scraping simply found nothing."""
    candidate_pages = [
        f"{base_url}/collections/best-sellers",
        f"{base_url}/collections/bestsellers",
        f"{base_url}/best-sellers",
        f"{base_url}/bestsellers",
        f"{site_url}/collections/all?sort_by=best-selling",
        f"{base_url}/collections/all?sort_by=best-selling",
        f"{base_url}/shop",
        f"{base_url}/products",
        site_url,
    ]

    block_reason = None
    product_urls: list = []
    for page_url in candidate_pages:
        try:
            resp = requests.get(page_url, timeout=10, headers=SCRAPE_HEADERS)
            if not resp.ok:
                # Record the first blocking status (e.g. 403 from bot protection)
                if block_reason is None and resp.status_code in (403, 401, 429, 503):
                    status_labels = {
                        403: "403 Access Denied — the site is blocking automated access (bot/CDN protection)",
                        401: "401 Unauthorized — the site requires authentication",
                        429: "429 Too Many Requests — the site is rate-limiting this IP",
                        503: "503 Service Unavailable — the site returned a temporary block",
                    }
                    block_reason = status_labels.get(resp.status_code, f"HTTP {resp.status_code}")
                continue
            found = re.findall(
                r'href="(/(?:products|shop|store)/[^"?#\s]+)"',
                resp.text,
            )
            seen = set()
            for link in found:
                full = f"{base_url}{link}"
                if full not in seen:
                    seen.add(full)
                    product_urls.append(full)
            if product_urls:
                break
        except Exception:
            continue

    products = []
    for product_url in product_urls[:max_products * 2]:
        try:
            resp = requests.get(product_url, timeout=10, headers=SCRAPE_HEADERS)
            if not resp.ok:
                continue

            name_match = re.search(
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
                resp.text, re.IGNORECASE
            ) or re.search(
                r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:title["\']',
                resp.text, re.IGNORECASE
            )
            name = (name_match.group(1).strip() if name_match
                    else product_url.rstrip("/").split("/")[-1])

            img_match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']',
                resp.text, re.IGNORECASE
            ) or re.search(
                r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:image["\']',
                resp.text, re.IGNORECASE
            )
            if not img_match:
                continue

            img_url = img_match.group(1).strip()
            if img_url.startswith("//"):
                img_url = f"https:{img_url}"
            elif img_url.startswith("/"):
                img_url = f"{base_url}{img_url}"
            img_url = re.sub(r"\?.*$", "", img_url)

            products.append({
                "name": name,
                "handle": product_url.rstrip("/").split("/")[-1],
                "image_urls": [img_url],
                "product_url": product_url,
            })

            if len(products) >= max_products:
                break
        except Exception:
            continue

    return products, block_reason


# ---------------------------------------------------------------------------
# Build prioritised download list
# ---------------------------------------------------------------------------

def _build_download_list(
    all_products: List[dict],
    product_filters: Optional[List[str]],
    max_products: int,
) -> List[dict]:
    """
    If filters are given: priority products (matched by name) come first,
    then best-sellers fill remaining slots. Deduped by handle.
    """
    if not product_filters:
        return all_products[:max_products]

    priority = [p for p in all_products if _fuzzy_match(p["name"], product_filters)]
    rest = [p for p in all_products if not _fuzzy_match(p["name"], product_filters)]

    if not priority:
        print(f"  Warning: no products matched filters {product_filters} — downloading best-sellers only.")

    combined = priority + rest
    seen = set()
    deduped = []
    for p in combined:
        if p["handle"] not in seen:
            seen.add(p["handle"])
            deduped.append(p)

    return deduped[:max_products]


# ---------------------------------------------------------------------------
# Download products
# ---------------------------------------------------------------------------

def scrape_product_images(
    site_url: str,
    max_products: int = 20,
    product_filters: Optional[List[str]] = None,
) -> List[dict]:
    """
    Scrape and download all images per product, FLAT, into product-images/.
    Run from inside intelligence/ so outputs land in the right place.

    Flat naming:
      ./product-images/[slug]-01.jpg  [slug]-02.jpg ...
    """
    site_url = site_url.rstrip("/")
    parsed = urlparse(site_url)
    if not parsed.scheme:
        site_url = f"https://{site_url}"
        parsed = urlparse(site_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    images_dir = Path("product-images")
    images_dir.mkdir(exist_ok=True)

    print(f"\nScraping products from {base_url}...\n")

    all_products, _ = _try_shopify_api(base_url)
    if all_products:
        print(f"  Shopify API found {len(all_products)} products.")
    else:
        print("  Shopify API not available — trying HTML scrape...")
        all_products, block_reason = _try_html_scrape(base_url, site_url, max_products * 3)
        if all_products:
            print(f"  HTML scrape found {len(all_products)} products.")
        else:
            print()
            if block_reason:
                print(f"  ✗ Scrape blocked: {block_reason}")
                print(f"  The site is preventing automated HTML access (bot/CDN protection).")
            else:
                print(f"  ✗ No products found — the site structure isn't supported by the scraper.")
            print()
            print(f"  WebFetch fallback (preferred — works through most blocks):")
            print(f"    The HTML is protected but the image CDN usually isn't. Gather each")
            print(f"    product's name + image URLs with the WebFetch tool, write them to a")
            print(f"    JSON file, then run:")
            print(f"      brand.py --ingest-file products-to-ingest.json")
            print()
            print(f"  Manual fallback:")
            print(f"    Drop images into product-images/ named [slug]-01.jpg, [slug]-02.jpg,")
            print(f"    then run:  brand.py --index   to rebuild the catalog.")
            print()
            return []

    to_download = _build_download_list(all_products, product_filters, max_products)

    if product_filters:
        matched_names = [p["name"] for p in to_download
                         if _fuzzy_match(p["name"], product_filters)]
        print(f"\n  Prioritised: {matched_names}")
        print(f"  Downloading {len(to_download)} product(s) total (priority + best-sellers)\n")
    else:
        print(f"\n  Downloading top {len(to_download)} best-selling product(s)\n")

    manifest: List[dict] = []
    seen_slugs: dict = {}

    for p in to_download:
        slug = _unique_slug(_slugify(p["name"]), seen_slugs)
        img_count = len(p["image_urls"])
        print(f"  {p['name']} ({img_count} image{'s' if img_count != 1 else ''}) → product-images/{slug}-NN")

        saved = _save_images_flat(slug, p["image_urls"], images_dir)
        if not saved:
            print(f"    Warning: no images saved for {p['name']}")
            continue

        entry = _blank_entry()
        entry.update({
            "name": p["name"],
            "slug": slug,
            "images": saved,
            "product_url": p["product_url"],
            "price": p.get("price"),
            "category": p.get("category"),
            "description": p.get("description", ""),
            "source": "scraped",
        })
        manifest.append(entry)
        print()

    if not manifest:
        print("\n  Warning: no product images were saved.")
        return []

    _write_manifest(manifest)
    total_images = sum(len(p["images"]) for p in manifest)
    print(f"  {len(manifest)} product(s), {total_images} total image(s) saved to ./product-images/")
    print(f"  Catalog → ./products.json\n")

    return manifest


# ---------------------------------------------------------------------------
# Reindex catalog from images on disk
# ---------------------------------------------------------------------------

def reindex_from_disk() -> List[dict]:
    """Rebuild products.json from the flat files in product-images/. Groups files
    by their slug (filename with any trailing `-NN` index removed), and preserves
    existing catalog enrichment (price, category, description, claims, product_url)
    for any slug already recorded. Run this after manually dropping images in, or
    to reconcile the catalog with what's actually on disk."""
    images_dir = Path("product-images")
    if not images_dir.exists():
        print("  No product-images/ folder found — nothing to index.")
        return []

    # Load existing enrichment keyed by slug.
    existing: dict = {}
    manifest_path = Path("products.json")
    brand = ""
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            brand = data.get("brand", "")
            existing = {p.get("slug"): p for p in data.get("products", [])}
        except Exception:
            pass

    # Group files by slug (strip trailing -NN numeric index).
    groups: dict = {}
    for f in sorted(images_dir.iterdir()):
        if f.name.startswith("."):
            continue
        if f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        stem = f.stem
        m = re.match(r"^(.*?)-(\d{1,3})$", stem)
        slug = m.group(1) if m else stem
        groups.setdefault(slug, []).append(f.name)

    if not groups:
        print("  product-images/ has no image files — nothing to index.")
        return []

    entries: List[dict] = []
    for slug, files in sorted(groups.items()):
        files.sort()
        prior = existing.get(slug, {})
        entry = _blank_entry()
        entry.update(prior)  # carry enrichment forward
        entry["slug"] = slug
        entry["images"] = files
        if not entry.get("name"):
            entry["name"] = slug.replace("-", " ").title()
        if not prior:
            entry["source"] = "manual"
            entry["added"] = _today()
        entries.append(entry)

    out = {"brand": brand, "updated": _today(), "products": entries}
    with open(manifest_path, "w") as f:
        json.dump(out, f, indent=2)

    total = sum(len(e["images"]) for e in entries)
    print(f"\n  Reindexed {len(entries)} product(s), {total} image(s) from product-images/")
    print(f"  Catalog → ./products.json\n")
    for e in entries:
        print(f"  • {e['slug']:<32} {len(e['images'])} image(s)")
    print()
    return entries


# ---------------------------------------------------------------------------
# Logo scraper
# ---------------------------------------------------------------------------

def _find_jsonld_logo(page_html: str) -> Optional[str]:
    """Look for a schema.org Organization/WebSite `logo` field inside any
    JSON-LD block — a purpose-built signal when a site declares it, and the
    same field extract-site-logo.js checks from the live DOM."""
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html, re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            logo = node.get("logo")
            if logo:
                if isinstance(logo, str):
                    return logo
                if isinstance(logo, dict) and logo.get("url"):
                    return logo["url"]
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return None


def _find_header_logo_img(page_html: str) -> Optional[str]:
    """Regex-scan the <header>/<nav> region (or the top of <body> if neither
    exists) for an <img> that looks like the logo — src/alt/class mentions
    'logo', preferring an .svg when several tie."""
    region_m = re.search(r"<header\b.*?</header>", page_html, re.IGNORECASE | re.DOTALL) \
        or re.search(r"<nav\b.*?</nav>", page_html, re.IGNORECASE | re.DOTALL)
    region = region_m.group(0) if region_m else page_html[:20000]

    best_src, best_score = None, 0
    for tag in re.findall(r"<img\b[^>]*>", region, re.IGNORECASE):
        src_m = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not src_m:
            continue
        src = html.unescape(src_m.group(1))
        blob = tag.lower()
        score = 1  # any header/nav <img> is a weak candidate on its own
        if "logo" in blob:
            score += 10
        if re.search(r"\.svg(\?|$)", src, re.IGNORECASE):
            score += 3
        if score > best_score:
            best_score, best_src = score, src
    return best_src


def _find_favicon_links(page_html: str) -> List[dict]:
    """Collect every <link rel="...icon..."> tag with its declared size, best
    (largest, apple-touch preferred) first."""
    candidates = []
    for tag in re.findall(r"<link\b[^>]*>", page_html, re.IGNORECASE):
        rel_m = re.search(r'\brel=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not rel_m or "icon" not in rel_m.group(1).lower():
            continue
        href_m = re.search(r'\bhref=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not href_m:
            continue
        size_m = re.search(r'\bsizes=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        size = 0
        if size_m and "x" in size_m.group(1).lower():
            try:
                size = int(size_m.group(1).lower().split("x")[0])
            except ValueError:
                size = 0
        rel = rel_m.group(1).lower()
        candidates.append({"href": html.unescape(href_m.group(1)), "rel": rel, "size": size})
    candidates.sort(key=lambda f: (f["size"], "apple" in f["rel"]), reverse=True)
    return candidates


def fetch_logo(site_url: str) -> Optional[List[dict]]:
    """Fetch the brand's homepage and download its logo into logos/. HTTP-only
    — no browser needed. Priority order:
      1. schema.org JSON-LD Organization.logo (purpose-built, most reliable)
      2. a header/nav <img> that looks like the logo
      3. the largest declared favicon / apple-touch-icon, saved separately as
         a secondary mark when a stronger primary logo was also found

    If the header is rendered client-side (no logo in the raw HTML) or the
    site blocks automated requests, this finds nothing — fall back to the
    live-browser read (extract-site-logo.js + --logo-url) or a manual drop.
    Never overwrites a file that's already in logos/ (e.g. one dropped in by
    hand under the same name).
    """
    site_url = site_url.rstrip("/")
    parsed = urlparse(site_url)
    if not parsed.scheme:
        site_url = f"https://{site_url}"
        parsed = urlparse(site_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    logos_dir = Path("logos")
    logos_dir.mkdir(exist_ok=True)

    print(f"\nFetching logo from {base_url}...\n")

    try:
        resp = requests.get(site_url, timeout=15, headers=SCRAPE_HEADERS)
        resp.raise_for_status()
        page_html = resp.text
    except Exception as e:
        print(f"  ✗ Could not fetch {site_url}: {e}\n")
        print("  Browser fallback: run extract-site-logo.js via javascript_tool on the")
        print("  loaded homepage, then save what it finds with --logo-url.")
        print("  Manual fallback: ask the user to drop a logo file into logos/.\n")
        return None

    primary_url, primary_source = _find_jsonld_logo(page_html), "json-ld"
    if not primary_url:
        primary_url, primary_source = _find_header_logo_img(page_html), "header-img"

    saved: List[dict] = []

    if primary_url:
        primary_url = _abs_url(primary_url, base_url)
        ext = _get_logo_ext(primary_url)
        dest = logos_dir / f"logo{ext}"
        if dest.exists():
            print(f"  logo{ext} already exists — leaving it alone.")
            saved.append({"file": dest.name, "source": primary_source, "url": primary_url})
        elif _download_image_file(primary_url, dest):
            print(f"  ✓ {dest.name}  (from {primary_source}: {primary_url})")
            saved.append({"file": dest.name, "source": primary_source, "url": primary_url})
        else:
            primary_url = None

    favicons = _find_favicon_links(page_html)
    if favicons:
        icon_url = _abs_url(favicons[0]["href"], base_url)
        if icon_url != primary_url:
            ext = _get_logo_ext(icon_url)
            # Only the secondary/icon slot when a primary logo already exists —
            # otherwise the favicon IS the best logo we found, so it takes the
            # primary name.
            dest = logos_dir / (f"logo-icon{ext}" if saved else f"logo{ext}")
            if dest.exists():
                print(f"  {dest.name} already exists — leaving it alone.")
                saved.append({"file": dest.name, "source": "favicon", "url": icon_url})
            elif _download_image_file(icon_url, dest):
                print(f"  ✓ {dest.name}  (from favicon: {icon_url})")
                saved.append({"file": dest.name, "source": "favicon", "url": icon_url})

    if not saved:
        print("  ✗ No logo found in the page HTML — the header may be client-rendered,")
        print("    or the site blocks automated access.\n")
        print("  Browser fallback (preferred — catches JS-rendered headers + inline SVG):")
        print("    Run .claude/skills/brand/extract-site-logo.js via javascript_tool on the")
        print("    loaded homepage, then save what it returns:")
        print('      brand.py --logo-url "<suggested.value>"   (inline SVG: write it directly)')
        print()
        print("  Manual fallback:")
        print("    Ask the user to drop a logo file into logos/.\n")
        return None

    print(f"\n  {len(saved)} file(s) saved to ./logos/\n")
    return saved


def save_logo_url(url: str, name: str = "logo") -> Optional[dict]:
    """Download a single already-identified logo image URL into logos/ — the
    hand-off point after finding a URL via extract-site-logo.js or WebFetch.
    No HTML parsing, just a headers-spoofed download. Won't overwrite an
    existing file of the same name."""
    logos_dir = Path("logos")
    logos_dir.mkdir(exist_ok=True)
    ext = _get_logo_ext(url)
    dest = logos_dir / f"{_slugify(name)}{ext}"

    print(f"\nDownloading logo from {url}...\n")

    if dest.exists():
        print(f"  {dest.name} already exists — leaving it alone. Pass --logo-name to save under a different name.\n")
        return {"file": dest.name, "url": url}
    if _download_image_file(url, dest):
        print(f"  ✓ {dest.name} saved to ./logos/\n")
        return {"file": dest.name, "url": url}
    print("  ✗ Download failed.\n")
    return None


# ---------------------------------------------------------------------------
# Fetch open-license webfonts (Google Fonts) into the fonts/ folder
# ---------------------------------------------------------------------------

# A modern browser UA makes the Google Fonts CSS2 endpoint return compact woff2;
# this older UA biases it toward more portable ttf/woff. The downloader uses
# whichever URL the CSS hands back, so either is fine for the fonts/ bin.
_FONT_CSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; rv:10.0) Gecko/20100101 Firefox/10.0",
}


def fetch_google_fonts(families: List[str], weights: str = "400;500;600;700") -> List[dict]:
    """Resolve Google Fonts family names to their font files and save them under
    ./fonts/[family]/. Returns a manifest of what was saved.

    Only open-license families on Google Fonts resolve here. Licensed/foundry
    fonts (Adobe Fonts, Monotype, self-hosted commercial faces) cannot be
    downloaded this way — record those in typography.json and have the user drop
    the files into fonts/ by hand.
    """
    fonts_root = Path("fonts")
    fonts_root.mkdir(exist_ok=True)

    print(f"\nFetching {len(families)} font famil{'y' if len(families) == 1 else 'ies'} from Google Fonts...\n")

    saved = []
    for family in families:
        family = family.strip()
        if not family:
            continue
        fam_param = family.replace(" ", "+")
        css_url = f"https://fonts.googleapis.com/css2?family={fam_param}:wght@{weights}&display=swap"
        try:
            resp = requests.get(css_url, timeout=20, headers=_FONT_CSS_HEADERS)
        except Exception as e:
            print(f"  ✗ {family}: request failed ({e})")
            continue
        if not resp.ok or "@font-face" not in resp.text:
            print(f"  ✗ {family}: not found on Google Fonts (licensed/foundry font? add it to fonts/ manually)")
            continue

        # Each @font-face block carries one weight + its file URL.
        blocks = re.findall(r"@font-face\s*\{([^}]+)\}", resp.text)
        fam_dir = fonts_root / _slugify(family)
        fam_dir.mkdir(exist_ok=True)
        files = []
        for block in blocks:
            wght_m = re.search(r"font-weight:\s*(\d+)", block)
            url_m = re.search(r"url\(([^)]+)\)", block)
            if not url_m:
                continue
            font_url = url_m.group(1).strip().strip("'\"")
            wght = wght_m.group(1) if wght_m else "400"
            ext = Path(urlparse(font_url).path).suffix.lower() or ".ttf"
            fname = f"{_slugify(family)}-{wght}{ext}"
            dest = fam_dir / fname
            if dest.exists():
                print(f"    {fname} (already exists, skipping)")
                files.append(fname)
                continue
            try:
                fr = requests.get(font_url, timeout=30, headers=SCRAPE_HEADERS)
                fr.raise_for_status()
                dest.write_bytes(fr.content)
                print(f"    ✓ {fname}")
                files.append(fname)
            except Exception as e:
                print(f"    ✗ {fname}: download failed ({e})")

        if files:
            saved.append({"family": family, "folder": f"fonts/{_slugify(family)}", "files": files})
        print()

    if saved:
        total = sum(len(f["files"]) for f in saved)
        print(f"  {len(saved)} famil{'y' if len(saved) == 1 else 'ies'}, {total} file(s) saved to ./fonts/\n")
    else:
        print("  No fonts downloaded — none resolved on Google Fonts. Add licensed faces to fonts/ manually.\n")
    return saved


# ---------------------------------------------------------------------------
# Archive raw brand-context drops into context-uploads/
# ---------------------------------------------------------------------------

def _dated_unique_dest(dest_dir: Path, base: str, ext: str, day: str) -> Path:
    """A collision-safe, date-prefixed destination inside dest_dir:
    `YYYY-MM-DD-<base><ext>`, appending -2, -3, … when that name is already
    taken so an archived drop is never overwritten."""
    candidate = dest_dir / f"{day}-{base}{ext}"
    n = 2
    while candidate.exists():
        candidate = dest_dir / f"{day}-{base}-{n}{ext}"
        n += 1
    return candidate


def save_context(
    sources: List[str],
    as_name: Optional[str] = None,
    move: bool = False,
) -> List[dict]:
    """Archive raw "add this to my brand context" source material into
    context-uploads/.

    Every drop — a guidelines PDF, a positioning deck, a screenshot, a stray
    document — is preserved here verbatim as a dated, collision-safe file, so the
    brand keeps an audit trail of everything it was built from even as each drop's
    substance is folded into the derived intelligence docs (visual-guidelines.md,
    brand-voice.md, …). This never replaces that refinement; it runs alongside it.

    Files only. A pasted fact or a verbal correction has no source file — write it
    straight to context-uploads/[day]-[slug].md with the Write tool instead.

    Copies by default (non-destructive, safe for a file the user keeps elsewhere);
    pass move=True for a throwaway chat upload whose permanent home is this folder.
    Run from inside intelligence/.
    """
    dest_dir = Path("context-uploads")
    dest_dir.mkdir(exist_ok=True)

    day = _today()
    multiple = len(sources) > 1
    saved: List[dict] = []

    print(f"\nArchiving {len(sources)} context file(s) → ./context-uploads/\n")

    for idx, raw in enumerate(sources, 1):
        src = Path(raw.strip().strip('"').strip("'")).expanduser()
        if not src.exists() or not src.is_file():
            print(f"  ✗ {src} — not a file, skipping")
            continue

        if as_name:
            base = _slugify(as_name) or "context"
            if multiple:
                base = f"{base}-{idx:02d}"
        else:
            base = _slugify(src.stem) or "context"
        ext = src.suffix.lower()

        dest = _dated_unique_dest(dest_dir, base, ext, day)
        try:
            if move:
                shutil.move(str(src), str(dest))
            else:
                dest.write_bytes(src.read_bytes())
        except Exception as e:
            print(f"  ✗ {src.name}: {'move' if move else 'copy'} failed ({e})")
            continue

        print(f"  ✓ {dest.name}  ({'moved' if move else 'copied'} from {src})")
        saved.append({"file": dest.name, "source": str(src), "moved": move})

    if not saved:
        print("\n  Nothing archived — no readable source files were given.\n")
        return []

    print(f"\n  {len(saved)} file(s) saved to ./context-uploads/")
    print("  Raw archive only — now fold their substance into the affected")
    print("  intelligence docs and regenerate brand-context.md.\n")
    return saved


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------

def scaffold_brand(brand_name: str) -> Path:
    """Create a brand's full folder tree and return its root.

    Idempotent and non-destructive — existing folders keep their contents — so it
    is safe to rerun mid-flight, or to backfill a brand that predates a new
    skill's folder.
    """
    slug = _slugify(brand_name)
    if not slug:
        raise SystemExit(f"Could not derive a folder name from {brand_name!r}")

    root = _project_root() / "brands" / slug
    gen_dirs = generation_dirs()
    rels = [f"intelligence/{d}" for d in INTELLIGENCE_DIRS]
    rels += [f"generation/{d}" for d in gen_dirs]

    created = 0
    for rel in rels:
        d = root / rel
        if not d.exists():
            created += 1
        d.mkdir(parents=True, exist_ok=True)

    # Second pass, once every folder exists: git tracks files, not directories,
    # so an empty leaf needs a marker or it won't survive a clone. A folder with
    # children doesn't — they carry their own.
    for rel in rels:
        d = root / rel
        if not any(p.name != ".gitkeep" for p in d.iterdir()):
            (d / ".gitkeep").touch(exist_ok=True)

    print(f"\nScaffolded ./brands/{slug}/")
    print(f"  intelligence/  {len(INTELLIGENCE_DIRS)} folders")
    print(f"  generation/    {len(gen_dirs)} folders (declared by the installed skills)")
    if created:
        print(f"  {created} created, {len(rels) - created} already existed\n")
    else:
        print(f"  nothing new — all {len(rels)} folders already existed\n")
    return root


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build a brand product catalog (flat product-images/ + products.json)."
    )
    parser.add_argument("--scaffold", type=str, default=None, metavar="BRAND",
        help="Create the brand's full folder tree (intelligence/ + generation/) and exit. "
             "Run this first, before anything else. Idempotent, and unlike every other "
             "command here it runs from the project root, not from inside intelligence/.")
    parser.add_argument("--scrape", type=str, default=None, metavar="URL",
        help="Brand website URL (e.g. https://brand.com). Not required for --ingest/--index.")
    parser.add_argument("--index", action="store_true",
        help="Rebuild products.json from the flat images already on disk in product-images/, "
             "preserving existing catalog enrichment. Use after dropping images in manually.")
    parser.add_argument("--ingest-file", type=str, default=None, metavar="PATH",
        help="Path to a JSON file of pre-extracted products to download — a single "
             '{"name","image_urls":[...],"product_url"?} object or a list of them. '
             "Use this WebFetch/browser fallback when a site blocks HTML scraping: gather "
             "the image URLs, write them here, then download via the open CDN.")
    parser.add_argument("--ingest", type=str, default=None, metavar="JSON",
        help="Inline JSON equivalent of --ingest-file (single object or array).")
    parser.add_argument("--product-urls", type=str, default=None, metavar="URLS",
        help='Comma-separated direct product page URLs to scrape exactly '
             '(e.g. "https://brand.com/products/camp-shirt,https://brand.com/products/chino"). '
             'When given, only these products are fetched — no full site scan. '
             'Preferred over --products for reliable results.')
    parser.add_argument("--products", type=str, default=None, metavar="NAMES",
        help='Comma-separated product names to prioritise (fuzzy match). '
             'Use --product-urls instead for exact results.')
    parser.add_argument("--max", type=int, default=20, metavar="N",
        help="Total number of products to download when using --products or best-sellers (default: 20)")
    parser.add_argument("--fetch-logo", type=str, default=None, metavar="URL",
        help="Brand website URL to auto-extract and download the logo from into logos/ — "
             "tries JSON-LD Organization.logo, a header/nav <img>, then the largest favicon, "
             "in that order. HTTP-only, no browser needed. If it finds nothing (JS-rendered "
             "header, bot-blocked site, inline SVG), use the browser fallback "
             "(extract-site-logo.js) with --logo-url, or drop a file into logos/ by hand.")
    parser.add_argument("--logo-url", type=str, default=None, metavar="URL",
        help="Download a single already-identified logo image URL into logos/ — the hand-off "
             "point after finding a URL via extract-site-logo.js or WebFetch. Pairs with "
             "--logo-name to set the saved filename (default: \"logo\").")
    parser.add_argument("--logo-name", type=str, default="logo", metavar="NAME",
        help='Filename (without extension) to save --logo-url as inside logos/ (default: "logo").')
    parser.add_argument("--fetch-fonts", type=str, default=None, metavar="FAMILIES",
        help='Comma-separated Google Fonts family names to download into ./fonts/ '
             '(e.g. "Inter,Playfair Display"). Only open-license Google Fonts resolve; '
             'licensed/foundry fonts must be added to fonts/ by hand.')
    parser.add_argument("--font-weights", type=str, default="400;500;600;700", metavar="W",
        help='Semicolon-separated weights to fetch with --fetch-fonts (default: "400;500;600;700").')
    parser.add_argument("--save-context", type=str, default=None, metavar="PATHS",
        help="Comma-separated file path(s) to archive into intelligence/context-uploads/ "
             "as dated, collision-safe copies — the raw-input trail for an "
             '"add this to my brand context" drop, kept alongside (never instead of) '
             "folding the substance into the derived docs. Pair with --as to name them "
             "and --move for a throwaway chat upload. A pasted fact has no file: Write it "
             "straight to context-uploads/[day]-[slug].md instead. Runs from inside intelligence/.")
    parser.add_argument("--as", dest="save_context_as", type=str, default=None, metavar="NAME",
        help="Base name for files archived with --save-context (default: each source's own "
             "name). With several files it becomes a numbered prefix ([name]-01, [name]-02).")
    parser.add_argument("--move", action="store_true",
        help="With --save-context, move each source instead of copying it — for a throwaway "
             "chat upload whose permanent home is context-uploads/. Default is a safe copy.")
    parser.add_argument("--validate", action="store_true",
        help="Check every skill's SKILL.md declaration (frontmatter contract, version, "
             "output collisions). Run before packaging a release.")
    parser.add_argument("--docs", action="store_true",
        help="Regenerate the skill table and counts between markers in README.md and "
             "CLAUDE.md from the skills' own frontmatter. Validates first.")

    args = parser.parse_args()

    if args.validate:
        if not validate_skills():
            raise SystemExit(1)
    elif args.docs:
        generate_docs()
    elif args.scaffold:
        scaffold_brand(args.scaffold)
    elif args.save_context:
        sources = [s.strip() for s in args.save_context.split(",") if s.strip()]
        save_context(sources, as_name=args.save_context_as, move=args.move)
    elif args.fetch_logo:
        fetch_logo(args.fetch_logo)
    elif args.logo_url:
        save_logo_url(args.logo_url, name=args.logo_name)
    elif args.fetch_fonts:
        families = [f.strip() for f in args.fetch_fonts.split(",") if f.strip()]
        fetch_google_fonts(families, weights=args.font_weights)
    elif args.index:
        reindex_from_disk()
    elif args.ingest or args.ingest_file:
        raw = args.ingest
        if args.ingest_file:
            raw = Path(args.ingest_file).read_text()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            parser.error(f"--ingest/--ingest-file is not valid JSON: {e}")
        products = data if isinstance(data, list) else [data]
        ingest_products(products)
    elif args.product_urls:
        if not args.scrape:
            parser.error("--product-urls requires --scrape (the brand site URL).")
        url_list = [u.strip() for u in args.product_urls.split(",") if u.strip()]
        scrape_specific_product_urls(args.scrape, url_list)
    elif args.scrape:
        product_filters = (
            [p.strip() for p in args.products.split(",") if p.strip()]
            if args.products else None
        )
        scrape_product_images(args.scrape, max_products=args.max, product_filters=product_filters)
    else:
        parser.error("Provide --scaffold BRAND to create the folder tree, --scrape URL "
                     "(optionally with --product-urls), --ingest/--ingest-file for the "
                     "WebFetch fallback, --index to rebuild the catalog from disk, "
                     "--fetch-logo URL to download the site's logo, --logo-url for the "
                     "browser-fallback hand-off, or --save-context PATHS to archive a "
                     "brand-context drop into context-uploads/.")


if __name__ == "__main__":
    main()
