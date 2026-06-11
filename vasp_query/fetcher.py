"""Fetch VASP wiki data. Updates data/raw/vasp_wiki_all_data.json."""

import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from vasp_query._common import RAW_DIR, DATA_DIR

_RAW_WIKI = RAW_DIR / "vasp_wiki_all_data.json"
_RAW_META = RAW_DIR / "_meta.json"
_BASE = "https://vasp.at/wiki/"
logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA})
    return s


def list_all_pages() -> list[str]:
    """Get all page titles from the VASP wiki via Special:AllPages (A-Z)."""
    seen: set[str] = set()
    pages: list[str] = []
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for char in alphabet:
        url = f"{_BASE}Special:AllPages?from={char}"
        while url:
            logger.info("  listing: %s", url.split("=")[-1][:30])
            r = _session().get(url, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            div = soup.find("div", {"id": "mw-content-text"})
            if div:
                for a in div.find_all("a", href=True):
                    href = a["href"]
                    # Skip Special: pages and non-wiki links
                    if not href.startswith("/wiki/") or "/wiki/Special:" in href:
                        continue
                    name = href.split("/wiki/", 1)[-1]
                    # Skip anchors and non-page links
                    if "#" in name or "?" in name or not name:
                        continue
                    if name not in seen:
                        seen.add(name)
                        pages.append(name)
            # Next page
            next_link = (
                soup.find("a", string=lambda t: t and "Next page" in t)
                or soup.find("a", string=">")
            )
            url = urljoin(_BASE, next_link["href"]) if next_link else None
            time.sleep(0.5)
    return pages


def fetch_page(title: str) -> dict | None:
    """Fetch a single page's content from the VASP wiki."""
    url = _BASE + title
    try:
        r = _session().get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1", {"class": "firstHeading"})
        title_text = h1.get_text().strip() if h1 else title
        div = soup.find("div", {"id": "mw-content-text"})
        if div:
            for ed in div.find_all("div", {"class": "mw-editsection"}):
                ed.decompose()
            content = div.get_text(separator="\\n", strip=True)
        else:
            content = ""
        return {"title": title_text, "url": url, "content": content}
    except Exception as e:
        logger.warning("  failed: %s (%s)", title, e)
        return None


def fetch_all() -> int:
    """Scrape all VASP wiki pages and save to raw data file."""
    logger.info("Fetching VASP wiki page list...")
    titles = list_all_pages()
    logger.info("Found %d pages. Fetching content...", len(titles))

    from tqdm import tqdm
    data: list[dict] = []
    for title in tqdm(titles, desc="Fetching wiki pages", unit="page"):
        page = fetch_page(title)
        if page:
            data.append(page)
        time.sleep(0.5)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(_RAW_WIKI, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    _write_meta(len(data), titles)
    logger.info("Saved %d pages to %s", len(data), _RAW_WIKI)
    return len(data)


def fetch_check() -> dict:
    """Check remote wiki for changes via MediaWiki API (fast, ~2s).

    Returns dict with keys: page_count, last_modified, changed.
    """
    meta = _read_meta()
    s = _session()

    # Get remote stats for main namespace only
    gen = s.get(f"{_BASE}api.php?action=query&generator=allpages&gaplimit=1&gapfilterredir=nonredirects&format=json", timeout=15).json()
    remote_count = gen.get("query", {}).get("pages", {})
    remote_total = len(remote_count) if "-1" not in remote_count else 0
    # Use allpages count via apcontinue
    ap = s.get(f"{_BASE}api.php?action=query&list=allpages&aplimit=max&format=json", timeout=15).json()
    all_pages = ap.get("query", {}).get("allpages", [])
    remote_count = len(all_pages)
    apcontinue = ap.get("continue", {}).get("apcontinue")
    while apcontinue:
        ap = s.get(f"{_BASE}api.php?action=query&list=allpages&aplimit=max&apcontinue={apcontinue}&format=json", timeout=15).json()
        all_pages.extend(ap.get("query", {}).get("allpages", []))
        apcontinue = ap.get("continue", {}).get("apcontinue")
    remote_count = len(all_pages)
    remote_titles = {p["title"] for p in all_pages}

    # Get latest change timestamp
    rc = s.get(f"{_BASE}api.php?action=query&list=recentchanges&rcprop=timestamp&rclimit=1&format=json", timeout=15).json()
    recent_changes = rc.get("query", {}).get("recentchanges", [])
    remote_last_modified = recent_changes[0]["timestamp"] if recent_changes else "unknown"

    local_count = meta.get("page_count", 0)
    local_titles = set(meta.get("page_titles", []))

    # Normalize: API returns spaces, scraper uses underscores; both use URL encoding
    from urllib.parse import unquote
    def norm(t):
        t = unquote(t)
        return t.replace(" ", "_").replace("_", " ").lower().strip()
    remote_norm = {norm(t): t for t in remote_titles}
    local_norm = {norm(t): t for t in local_titles}

    new_pages = sorted(set(remote_norm.keys()) - set(local_norm.keys()))[:20]
    removed_pages = sorted(set(local_norm.keys()) - set(remote_norm.keys()))[:20]

    changed = bool(new_pages) or bool(removed_pages) or remote_last_modified != meta.get("last_modified", "")
    return {
        "page_count": remote_count,
        "last_page_count": local_count,
        "last_modified": remote_last_modified,
        "new_pages": new_pages,
        "removed_pages": removed_pages,
        "changed": changed,
    }


def _write_meta(count: int, titles: list[str]) -> None:
    """Write fetch metadata with page list hash."""
    h = hashlib.md5("".join(titles).encode()).hexdigest()
    # Get latest remote change timestamp for future comparison
    try:
        rc = _session().get(
            f"{_BASE}api.php?action=query&list=recentchanges&rcprop=timestamp&rclimit=1&format=json",
            timeout=10
        ).json()
        last_modified = rc.get("query", {}).get("recentchanges", [{}])[0].get("timestamp", "")
    except Exception:
        last_modified = ""
    meta = {
        "last_fetch": datetime.now(timezone.utc).isoformat(),
        "last_modified": last_modified,
        "page_count": count,
        "page_titles_md5": h,
        "page_titles": titles,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(_RAW_META, "w") as f:
        json.dump(meta, f, indent=2)


def _read_meta() -> dict:
    if _RAW_META.exists():
        return json.loads(_RAW_META.read_text())
    return {}
