# LinkedIn Job Description Scraper

This repository contains a Python script that downloads job postings for a given company name from LinkedIn's public guest job search endpoint.

## Prerequisites

- Python 3.9 or newer
- A virtual environment is recommended
- The script depends on `requests` and `beautifulsoup4`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

If you do not want to use a requirements file you can install the packages directly:

```bash
pip install requests beautifulsoup4
```

## Running the scraper

From the repository root run:

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
