import os
import time
from outscraper import ApiClient
from config import SEARCH_QUERIES, RESULTS_PER_QUERY


def _build_client() -> ApiClient:
    api_key = os.environ.get("OUTSCRAPER_API_KEY")
    if not api_key:
        raise EnvironmentError("OUTSCRAPER_API_KEY is not set. Check your .env file.")
    return ApiClient(api_key=api_key)


def _parse_result(raw: dict, category: str) -> dict:
    """Normalise a single Outscraper place result into our lead schema."""
    emails_raw = raw.get("emails_and_contacts", {})
    maps_email = ""
    if isinstance(emails_raw, dict):
        emails_list = emails_raw.get("emails", [])
        if emails_list:
            maps_email = emails_list[0].get("value", "")

    return {
        "business_name": raw.get("name", ""),
        "category": category,
        "address": raw.get("full_address", ""),
        "suburb": raw.get("city", ""),
        "phone": raw.get("phone", ""),
        "website": raw.get("site", ""),
        "email_maps": maps_email,
        "emails_website": "",   # populated by enricher
        "rating": raw.get("rating", ""),
        "reviews": raw.get("reviews", ""),
        "google_maps_url": raw.get("url", ""),
    }


def run_scrape() -> list[dict]:
    client = _build_client()
    leads: list[dict] = []
    seen: set[str] = set()

    for item in SEARCH_QUERIES:
        query = item["query"]
        category = item["category"]
        print(f"  Querying: {query} ({RESULTS_PER_QUERY} results)...")

        try:
            results = client.google_maps_search(
                query,
                limit=RESULTS_PER_QUERY,
                language="en",
                region="AU",
            )

            batch = results[0] if results else []
            for raw in batch:
                place_id = raw.get("place_id") or raw.get("name", "")
                if place_id in seen:
                    continue
                seen.add(place_id)
                leads.append(_parse_result(raw, category))

            print(f"    -> {len(batch)} results, {len(leads)} total unique so far")

        except Exception as exc:
            print(f"    [ERROR] {query}: {exc}")

        time.sleep(0.5)

    return leads
