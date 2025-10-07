"""LinkedIn job description scraper.

This script scrapes job postings for a given company name from LinkedIn's
public job search pages (the guest job search endpoint). It collects basic
metadata and, optionally, the full job description for each posting. Results
can be exported to CSV or JSON.

Due to the aggressive anti-automation measures employed by LinkedIn, use this
script responsibly. It is intended for educational purposes and small-scale
analysis only. Respect LinkedIn's terms of service and robots.txt when using
it.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class JobPosting:
    """Represents a single job posting scraped from LinkedIn."""

    job_id: str
    title: str
    company: str
    location: str
    listed_at: Optional[str]
    job_url: str
    company_url: Optional[str]
    description: Optional[str]
    workplace_type: Optional[str]
    seniority_level: Optional[str]
    employment_type: Optional[str]
    job_functions: Optional[str]
    industries: Optional[str]

    def to_serialisable(self) -> Dict[str, Optional[str]]:
        """Convert the dataclass to a JSON/CSV serialisable dictionary."""

        return asdict(self)


def parse_arguments(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(description="Scrape job descriptions from LinkedIn for a company")
    parser.add_argument("company", help="Company name keyword to search for (e.g. 'OpenAI')")
    parser.add_argument("--location", default="Worldwide", help="Location filter (default: Worldwide)")
    parser.add_argument("--max-results", type=int, default=50, help="Maximum number of job postings to fetch")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests in seconds")
    parser.add_argument("--output", default="linkedin_jobs.csv", help="Output file path")
    parser.add_argument(
        "--format",
        choices={"csv", "json"},
        default="csv",
        help="Output format (csv or json)",
    )
    parser.add_argument(
        "--skip-description",
        action="store_true",
        help="Skip fetching job description pages for faster scraping",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args(list(argv) if argv is not None else None)


def create_logger(verbose: bool = False) -> logging.Logger:
    """Configure and return a logger."""

    logger = logging.getLogger("linkedin_scraper")
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logger


def build_search_params(company: str, location: str, start: int) -> Dict[str, str]:
    """Build query parameters for the LinkedIn guest job search endpoint."""

    return {
        "keywords": company,
        "location": location,
        "start": str(start),
        "refresh": "true",
    }


def fetch_search_results(company: str, location: str, start: int, logger: logging.Logger) -> Optional[BeautifulSoup]:
    """Fetch and parse a batch of job search results."""

    params = build_search_params(company, location, start)
    logger.debug("Fetching search results with params: %s", params)
    response = requests.get(BASE_SEARCH_URL, params=params, headers=BASE_HEADERS, timeout=30)
    if response.status_code == 404:
        logger.warning("Received 404 for search results (start=%s).", start)
        return None
    response.raise_for_status()

    if not response.text.strip():
        logger.debug("Empty response body for start=%s", start)
        return None

    return BeautifulSoup(response.text, "html.parser")


def extract_text(element: Optional[BeautifulSoup]) -> str:
    """Safely extract stripped text from a BeautifulSoup element."""

    return element.get_text(strip=True) if element else ""


def extract_job_cards(soup: BeautifulSoup, logger: logging.Logger) -> List[JobPosting]:
    """Extract job cards from the search results soup."""

    job_cards = []
    for li in soup.select("li.jobs-search-results__list-item"):
        job_id = li.get("data-entity-urn", "").split(":")[-1]
        job_link = li.select_one("a.base-card__full-link")
        title_el = li.select_one("h3.base-search-card__title")
        company_el = li.select_one("h4.base-search-card__subtitle")
        location_el = li.select_one("span.job-search-card__location")
        listed_el = li.select_one("time")
        company_link_el = li.select_one("a.base-search-card__subtitle-link")

        if not job_link:
            logger.debug("Skipping job card without link: %s", li)
            continue

        job_posting = JobPosting(
            job_id=job_id or "",
            title=extract_text(title_el),
            company=extract_text(company_el),
            location=extract_text(location_el),
            listed_at=listed_el["datetime"] if listed_el and listed_el.has_attr("datetime") else extract_text(listed_el),
            job_url=job_link.get("href", "").split("?")[0],
            company_url=company_link_el.get("href") if company_link_el else None,
            description=None,
            workplace_type=None,
            seniority_level=None,
            employment_type=None,
            job_functions=None,
            industries=None,
        )
        job_cards.append(job_posting)

    logger.debug("Extracted %d job cards", len(job_cards))
    return job_cards


def fetch_job_description(job: JobPosting, logger: logging.Logger) -> None:
    """Fetch and enrich a job posting with its description and criteria."""

    if not job.job_url:
        logger.debug("Job %s has no URL, skipping description fetch", job.job_id)
        return

    logger.debug("Fetching job description for %s", job.job_url)
    response = requests.get(job.job_url, headers=BASE_HEADERS, timeout=30)
    if response.status_code == 404:
        logger.warning("Job page not found for %s", job.job_url)
        return
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    description_el = soup.select_one("div.show-more-less-html__markup")
    if description_el:
        job.description = description_el.get_text("\n", strip=True)

    for criteria in soup.select("ul.description__job-criteria-list li"):
        label = extract_text(criteria.select_one("h3"))
        value = extract_text(criteria.select_one("span"))
        lower_label = label.lower()
        if "seniority" in lower_label:
            job.seniority_level = value
        elif "employment" in lower_label:
            job.employment_type = value
        elif "job function" in lower_label:
            job.job_functions = value
        elif "industr" in lower_label:
            job.industries = value
        elif "workplace" in lower_label:
            job.workplace_type = value


def scrape_jobs(
    company: str,
    location: str,
    max_results: int,
    delay: float,
    skip_description: bool,
    logger: logging.Logger,
) -> List[JobPosting]:
    """Scrape job postings for the given company."""

    scraped: List[JobPosting] = []
    start = 0

    while len(scraped) < max_results:
        soup = fetch_search_results(company, location, start, logger)
        if not soup:
            logger.info("No more search results returned at start=%s", start)
            break

        job_cards = extract_job_cards(soup, logger)
        if not job_cards:
            logger.info("No job cards found at start=%s", start)
            break

        for job in job_cards:
            scraped.append(job)
            if len(scraped) >= max_results:
                break

        logger.info("Collected %d/%d job summaries", len(scraped), max_results)
        start += 25
        if len(scraped) < max_results:
            logger.debug("Sleeping for %s seconds", delay)
            time.sleep(delay)

    if not skip_description:
        for index, job in enumerate(scraped, start=1):
            try:
                fetch_job_description(job, logger)
            except requests.RequestException as error:
                logger.warning("Failed to fetch description for %s: %s", job.job_url, error)
            if index < len(scraped):
                logger.debug("Sleeping for %s seconds between job pages", delay)
                time.sleep(delay)

    return scraped


def write_csv(jobs: List[JobPosting], output_path: str, logger: logging.Logger) -> None:
    """Write job postings to a CSV file."""

    logger.info("Writing %d job postings to CSV: %s", len(jobs), output_path)
    fieldnames = list(jobs[0].to_serialisable().keys()) if jobs else []
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            writer.writerow(job.to_serialisable())


def write_json(jobs: List[JobPosting], output_path: str, logger: logging.Logger) -> None:
    """Write job postings to a JSON file."""

    logger.info("Writing %d job postings to JSON: %s", len(jobs), output_path)
    with open(output_path, "w", encoding="utf-8") as jsonfile:
        json.dump([job.to_serialisable() for job in jobs], jsonfile, ensure_ascii=False, indent=2)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_arguments(argv)
    logger = create_logger(args.verbose)

    try:
        jobs = scrape_jobs(
            company=args.company,
            location=args.location,
            max_results=max(args.max_results, 1),
            delay=max(args.delay, 0.0),
            skip_description=args.skip_description,
            logger=logger,
        )
    except requests.RequestException as error:
        logger.error("Failed to scrape jobs: %s", error)
        return 1

    if not jobs:
        logger.warning("No jobs found for company '%s'", args.company)
        return 2

    writer = write_csv if args.format == "csv" else write_json
    writer(jobs, args.output, logger)
    logger.info("Scraping completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
