"""Fetch LinkedIn jobs by company and export them in JSON or CSV format."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import requests
from bs4 import BeautifulSoup

import warnings

warnings.filterwarnings("ignore")


BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest"
COMPANY_SEARCH_PATH = "/api/typeaheadHits"
COMPANY_JOBS_PATH = "/jobs/api/seeMoreJobPostings/search"

STARTUP_COMPANY_NAMES = [
    "Lovable",
    "Hugging Face",
    "OpenAI",
    "Replit",
    "Anthropic",
    "Scale AI",
    "Glean",
    "Perplexity",
]
INSURANCE_COMPANY_NAMES = [
    "Chubb",
    "AIG",
    "The Hartford",
    "Farmers",
    "Progressive",
    "Nationwide",
    "Allstate",
    "Geico",
    "State Farm",
    "Zurich",
]
TECH_COMPANY_NAMES = [
    "Meta",
    "Amazon",
    "Alphabet",
    "Microsoft",
    "Netflix",
    "Nvidia",
    "Stripe",
    "Apple",
    "Shopify",
    "Walmart",
]


COMPANY_LISTS: Dict[str, Sequence[str]] = {
    "startups": STARTUP_COMPANY_NAMES,
    "insurance": INSURANCE_COMPANY_NAMES,
    "tech": TECH_COMPANY_NAMES,
    "all": STARTUP_COMPANY_NAMES + INSURANCE_COMPANY_NAMES + TECH_COMPANY_NAMES,
}


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download job postings from LinkedIn for selected companies."
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help=(
            "Output file or directory. When a directory is provided, a JSON file named "
            "linkedin_jobs.json will be created inside it."
        ),
    )
    parser.add_argument(
        "-e",
        "--experience-level",
        default="2",
        help="LinkedIn f_E experience level filter (e.g., 2 for Entry level).",
    )
    parser.add_argument(
        "-c",
        "--company-list",
        nargs="+",
        default=["all"],
        choices=sorted(COMPANY_LISTS.keys()),
        help=(
            "One or more predefined company lists to query. Use 'all' to include "
            "every company."
        ),
    )
    parser.add_argument(
        "--companies",
        nargs="+",
        default=None,
        help=(
            "Optional explicit company names. When provided, these override any "
            "selected company list."
        ),
    )
    parser.add_argument(
        "-k",
        "--keywords",
        default="data engineer",
        help="Keywords to search for within each company.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (e.g., INFO, DEBUG).",
    )
    return parser.parse_args()


def resolve_companies(selected_lists: Iterable[str], overrides: List[str] | None) -> List[str]:
    if overrides:
        return sorted(dict.fromkeys(overrides))

    company_names: Dict[str, None] = {}
    for list_name in selected_lists:
        for company in COMPANY_LISTS[list_name]:
            company_names.setdefault(company, None)
    return sorted(company_names.keys())


def resolve_output_path(output: str) -> Path:
    output_path = Path(output)

    if output.endswith(("/", "\\")):
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path / "linkedin_jobs.json"

    if output_path.exists() and output_path.is_dir():
        output_file = output_path / "linkedin_jobs.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        return output_file

    if output_path.suffix:
        if output_path.suffix.lower() not in {".json", ".csv"}:
            raise ValueError("Only .json and .csv output formats are supported.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    # No suffix and not an existing directory. Default to JSON.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path.with_suffix(".json")


def fetch_company_id(company_name: str) -> str | None:
    params = {"typeaheadType": "COMPANY", "query": company_name}
    response = requests.get(
        BASE_SEARCH_URL + COMPANY_SEARCH_PATH, params=params, verify=False, timeout=30
    )
    try:
        return response.json()[0]["id"]
    except Exception:
        logger.warning(
            "Unable to find company id for %s (status %s)",
            company_name,
            response.status_code,
        )
        return None


def fetch_jobs_for_company(
    company_id: str, keywords: str, experience_level: str
) -> List[BeautifulSoup]:
    has_more_jobs = True
    job_next_start = 0
    job_link_elements: List[BeautifulSoup] = []

    while has_more_jobs:
        params = {
            "f_C": company_id,
            "keywords": keywords,
            "start": job_next_start,
            "f_E": experience_level,
        }
        response = requests.get(
            BASE_SEARCH_URL + COMPANY_JOBS_PATH, params=params, verify=False, timeout=30
        )
        logger.debug("Jobs URL: %s", response.url)
        soup = BeautifulSoup(response.content, "html.parser")
        current_links = soup.find_all("a", attrs={"class": "base-card__full-link"})
        has_more_jobs = len(current_links) >= 1
        job_link_elements.extend(current_links)
        job_next_start += len(current_links)
        logger.info(
            "Pulled %s jobs so far for company_id=%s", len(job_link_elements), company_id
        )

    return job_link_elements


def extract_job_details(link: BeautifulSoup, company_name: str) -> Dict[str, str]:
    job_title = str(link.find("span", attrs={"class": "sr-only"}).get_text()).strip()
    job_url = str(link.attrs["href"])
    job_id = job_url.split("?")[0].split("-")[-1]

    job_response = requests.get(
        BASE_SEARCH_URL + f"/jobs/api/jobPosting/{job_id}", verify=False, timeout=30
    )
    if job_response.status_code != 200:
        raise ValueError(f"Job {job_id} request failed: {job_response.status_code}")

    job_soup = BeautifulSoup(job_response.content, "html.parser")

    def safe_text(selector: str, *, allow_default: str = "N/A") -> str:
        element = job_soup.select_one(selector)
        return element.get_text().strip() if element else allow_default

    try:
        criteria_tags = job_soup.find_all(
            "span", attrs={"class": "description__job-criteria-text"}
        )
        seniority = criteria_tags[0].get_text().strip()
        employment_type = criteria_tags[1].get_text().strip()
        job_function = criteria_tags[2].get_text().strip()
        industry = criteria_tags[3].get_text().strip()
    except Exception:
        seniority = employment_type = job_function = industry = "N/A"

    try:
        compensation = (
            job_soup.find("div", attrs={"class": "salary"})
            .get_text()
            .strip()
            .split(" - ")[0]
            .removesuffix("/yr")
        )
    except Exception:
        compensation = "0"

    description_wrapper = job_soup.find(
        "div", attrs={"class": "description__text"}
    )
    if description_wrapper is not None:
        description_content = description_wrapper.find(
            "div", attrs={"class": "show-more-less-html__markup"}
        )
        description = (
            description_content.get_text(separator="\n").strip()
            if description_content
            else "N/A"
        )
    else:
        description = "N/A"

    title_element = job_soup.find("h2", attrs={"class": "top-card-layout__title"})
    title = title_element.get_text().strip() if title_element else "N/A"

    return {
        "desc": description,
        "comp": compensation,
        "title": title,
        "url": job_response.url,
        "loc": safe_text("span.topcard__flavor--bullet"),
        "company": company_name,
        "seniority": seniority,
        "employmentType": employment_type,
        "Job Function": job_function,
        "industry": industry,
        "jobTitle": job_title,
    }


def append_jobs_to_output(jobs: List[Dict[str, str]], output_file: Path) -> None:
    if not jobs:
        logger.info("No jobs fetched; skipping write.")
        return

    if output_file.suffix.lower() == ".json":
        existing_jobs: List[Dict[str, str]] = []
        if output_file.exists():
            try:
                with output_file.open("r", encoding="utf-8") as fh:
                    existing_content = json.load(fh)
                    if isinstance(existing_content, list):
                        existing_jobs = existing_content
            except json.JSONDecodeError:
                logger.warning("Existing JSON is invalid; starting a new list.")

        with output_file.open("w", encoding="utf-8") as fh:
            json.dump(existing_jobs + jobs, fh, indent=2)
        return

    # CSV handling
    fieldnames = sorted({key for job in jobs for key in job.keys()})
    file_exists = output_file.exists()
    needs_header = (not file_exists) or output_file.stat().st_size == 0
    with output_file.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if needs_header:
            writer.writeheader()
        for job in jobs:
            writer.writerow(job)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s: %(message)s")

    output_file = resolve_output_path(args.output)
    companies = resolve_companies(args.company_list, args.companies)

    logger.info("Saving jobs to %s", output_file)
    logger.info("Fetching companies: %s", ", ".join(companies))

    all_jobs: List[Dict[str, str]] = []
    seen_titles: Dict[str, None] = {}

    for company in companies:
        company_id = fetch_company_id(company)
        if not company_id:
            continue

        links = fetch_jobs_for_company(
            company_id=company_id,
            keywords=args.keywords,
            experience_level=args.experience_level,
        )

        logger.info("Total links for %s: %s", company, len(links))
        for link in links:
            try:
                job_info = extract_job_details(link, company)
            except Exception as err:  # noqa: BLE001 - broad to continue fetching
                logger.warning("Skipping job due to error: %s", err)
                continue

            unique_key = f"{job_info.get('title','')}-{job_info.get('company','')}-{job_info.get('jobTitle','')}"
            if unique_key in seen_titles:
                logger.debug("Skipping duplicate job: %s", unique_key)
                continue
            seen_titles[unique_key] = None
            all_jobs.append(job_info)
            logger.info(
                "Processed Job: %s at %s", job_info.get("title", "N/A"), job_info.get("company", "N/A")
            )

    append_jobs_to_output(all_jobs, output_file)


if __name__ == "__main__":
    main()

    



    



