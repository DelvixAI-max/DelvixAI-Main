import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import CRAWL_DELAY, MAX_PAGES_PER_SITE

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

_JUNK_DOMAINS = {
    "sentry.io", "wixpress.com", "example.com", "squarespace.com",
    "wordpress.com", "shopify.com", "amazonaws.com", "cloudfront.net",
    "googletagmanager.com", "w3.org",
}

_CONTACT_SLUGS = ["/contact", "/contact-us", "/about", "/get-in-touch", "/enquire"]


def _fetch(url: str, timeout: int = 8) -> str | None:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.ok and "text/html" in resp.headers.get("content-type", ""):
            return resp.text
    except Exception:
        pass
    return None


def _extract_emails(html: str, base_domain: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")

    emails: set[str] = set()

    # mailto: links — highest confidence
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr:
                emails.add(addr.lower())

    # regex sweep over visible text
    text = soup.get_text(" ", strip=True)
    for match in _EMAIL_RE.findall(text):
        emails.add(match.lower())

    # filter junk
    cleaned: set[str] = set()
    for email in emails:
        domain = email.split("@")[-1]
        if domain in _JUNK_DOMAINS:
            continue
        if domain == base_domain:
            cleaned.add(email)
        elif not any(j in domain for j in _JUNK_DOMAINS):
            cleaned.add(email)

    return cleaned


def _contact_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    urls = [base_url]
    for slug in _CONTACT_SLUGS:
        candidate = root + slug
        if candidate not in urls:
            urls.append(candidate)
    return urls[:MAX_PAGES_PER_SITE + 1]


def enrich_leads(leads: list[dict]) -> None:
    """Mutates each lead dict in-place, adding discovered emails to emails_website."""
    total = len(leads)
    for idx, lead in enumerate(leads, 1):
        website = (lead.get("website") or "").strip()
        if not website:
            continue

        if not website.startswith("http"):
            website = "https://" + website

        base_domain = urlparse(website).netloc.lstrip("www.")
        print(f"  [{idx}/{total}] Enriching: {lead['business_name']} — {website}")

        found: set[str] = set()
        for url in _contact_urls(website):
            html = _fetch(url)
            if html:
                found |= _extract_emails(html, base_domain)
            time.sleep(CRAWL_DELAY)

        # Remove any email already captured from Maps to avoid duplication
        maps_email = (lead.get("email_maps") or "").lower()
        found.discard(maps_email)

        lead["emails_website"] = ", ".join(sorted(found))
