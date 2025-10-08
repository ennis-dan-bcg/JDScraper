# LinkedIn Job Description Scraper

This repository contains Python scripts that download job postings from LinkedIn's public guest job search endpoint.

## Prerequisites

- Python 3.9 or newer
- A virtual environment is recommended
- The scripts depend on `requests` and `beautifulsoup4`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

If you do not want to use a requirements file you can install the packages directly:

```bash
pip install requests beautifulsoup4
```

## Company-centric scraping (`script-byCompany.py`)

Use `script-byCompany.py` when you want to gather postings for one or more predefined company lists (startups, tech, insurance, or all combined) or supply an explicit set of company names. The script supports JSON and CSV output, automatically appending to existing files instead of overwriting them.

```bash
python script-byCompany.py \
  --output data/linkedin_jobs.json \
  --experience-level 2 \
  --company-list startups tech \
  --keywords "data engineer" \
  --log-level INFO
```

Key options:

- `--output` / `-o` (**required**): Destination file or directory. Directories create `linkedin_jobs.json` inside. Files must end with `.json` or `.csv`. Existing files are appended to.
- `--experience-level` / `-e`: LinkedIn `f_E` experience level code (e.g., `2` for entry level). Defaults to `2`.
- `--company-list` / `-c`: One or more predefined company lists (`startups`, `insurance`, `tech`, or `all`). Defaults to `all`.
- `--companies`: Explicit company names. When provided, these override the predefined lists.
- `--keywords` / `-k`: Search keywords used for each company (default `"data engineer"`).
- `--log-level`: Logging verbosity (default `INFO`).

Example directory output (writes/updates `out/linkedin_jobs.json`):

```bash
python script-byCompany.py -o out/ -c startups
```

Example CSV output (appends to `jobs.csv`):

```bash
python script-byCompany.py -o jobs.csv --companies "OpenAI" "Anthropic"
```

## Single-company scraping (`script.py`)

`script.py` focuses on scraping a single company and offers more granular control over the number of job cards to fetch, location filters, request pacing, and whether to download full job descriptions.

```bash
python script.py "Company Name" \
  --location "United States" \
  --max-results 100 \
  --delay 3 \
  --format csv \
  --output linkedin_jobs.csv
```

Only the company name is required. All other flags are optional:

- `--location`: LinkedIn location filter (defaults to `Worldwide`).
- `--max-results`: Maximum number of job cards to collect (default `50`).
- `--delay`: Seconds to sleep between requests to avoid rate limits (default `2`).
- `--format`: Output format, either `csv` or `json` (default `csv`).
- `--output`: Destination file path (default `linkedin_jobs.csv`).
- `--skip-description`: Skip fetching each job detail page to speed up scraping.
- `--verbose`: Enable verbose logging output.

The script exits with a non-zero status code when scraping fails or no results are returned.

## Output

Depending on the format selected, the scraper writes the collected postings to a CSV or JSON file containing the job metadata and (optionally) descriptions.

## Notes

Use the scraper responsibly. LinkedIn has strict anti-automation measures and the endpoints may change without notice. Respect the site's terms of service and robots.txt.
