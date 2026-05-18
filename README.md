# Delvix AI — Melbourne SMB Lead Scraper

Scrapes Google Maps for AI-unsophisticated SMBs across 7 target industries in Melbourne, enriches each result with emails extracted from business websites, and outputs a formatted Excel spreadsheet.

## Setup

### 1. Get an Outscraper API key
Sign up at [outscraper.com](https://outscraper.com). The free tier gives ~$3 credit. At ~$0.002 per result, the default config (30 queries × 20 results = 600 leads) costs around $1.20.

### 2. Install dependencies
```
pip install -r requirements.txt
```

### 3. Configure your API key
```
cp .env.example .env
# Edit .env and add your key
```

### 4. Run
```
python main.py
```

Output: `delvix_leads_melbourne.xlsx`

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `RESULTS_PER_QUERY` | 20 | Google Maps results per search term. Increase for more leads. |
| `CRAWL_DELAY` | 1.5s | Pause between website crawl requests. |
| `MAX_PAGES_PER_SITE` | 2 | Homepage + contact page per business. |
| `OUTPUT_FILE` | `delvix_leads_melbourne.xlsx` | Output filename. |

---

## Output columns

| Column | Source |
|---|---|
| Business Name | Google Maps |
| Category | Search query group |
| Suburb | Google Maps |
| Address | Google Maps |
| Phone | Google Maps |
| Website | Google Maps |
| Email (Maps) | Google Maps listing |
| Emails (Website) | Scraped from business website |
| Rating | Google Maps |
| Reviews | Google Maps |
| Google Maps URL | Google Maps |

---

## Scaling up

- Increase `RESULTS_PER_QUERY` to 50–100 for denser coverage.
- Add suburbs to queries in `config.py` (e.g. `"plasterers Fitzroy"`) for suburb-level targeting.
- Outscraper also supports `google_maps_search_v2` which returns richer data including social profiles.

---

## Legal note

Outscraper is a compliant commercial data service. Website enrichment crawls publicly listed business contact pages. All data collected is business contact information, not personal data, consistent with Australian Spam Act 2003 requirements for B2B commercial messaging.
