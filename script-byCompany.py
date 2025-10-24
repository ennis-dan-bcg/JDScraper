import argparse
import csv
import json
import logging
import sys
import time
import csv
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import traceback

import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

from anthropic import Anthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest"
COMPANY_SEARCH_PATH="/api/typeaheadHits"

STARTUP_COMPANY_NAMES  = ["Lovable", "Hugging Face", "Replit", "Anthropic", "Scale AI", "Glean", "Perplexity", "SpaceX", "xAI", "Canva", "Anduril", "Cruise", "Epic Games", "Ramp", "Miro", "Rippling", "Airtable", "Notion", "Polymarket", "Brex", "Cohere", "Plaid", "Hopper", ]
INSURANCE_COMPANY_NAMES  = ["Google", "Chubb","AIG", "The Hartford", "Farmers", "Progressive", "Nationwide", "Allstate", "Geico", "State Farm", "Zurich"]
TECH_COMPANY_NAMES  = [ "Meta", "Amazon", "Alphabet", "Microsoft", "Netflix", "Nvidia", "Stripe", "Apple", "Shopify", "Walmart", "Spotify", "Databricks", "Uber", "Lyft", "Doordash", "TikTok", "Pinterest", "Datadog", "DraftKings", "ServiceNow"]
FI_COMPANY_NAMES = ["Morgan Stanley", "Goldman Sachs", "Bank of America", "J.P. Morgan", "JPMorganChase", "Wells Fargo", "Citi", "American Express", "Capital One", "State Street" ]

ALL_COMPANY_NAMES = STARTUP_COMPANY_NAMES + INSURANCE_COMPANY_NAMES + TECH_COMPANY_NAMES + FI_COMPANY_NAMES


def get_company_classification(company_name):
    """
    Returns the classification of a company (Startup, Insurance, Tech, or FI).

    Args:
        company_name: The display name of the company

    Returns:
        String classification: "Startup", "Insurance", "Tech", "FI", or "Unknown"
    """
    if company_name in STARTUP_COMPANY_NAMES:
        return "Startup"
    elif company_name in INSURANCE_COMPANY_NAMES:
        return "Insurance"
    elif company_name in TECH_COMPANY_NAMES:
        return "Tech"
    elif company_name in FI_COMPANY_NAMES:
        return "FI"
    else:
        return "Unknown"


def enrich_jobs_with_claude(jobs_list, company_name):
    """
    Use Claude API to extract structured information from job descriptions.

    Extracts: years of experience, education requirements, job function, and team.

    Returns: List of jobs with enriched metadata (all jobs preserved)
    """
    if not jobs_list:
        return jobs_list

    # Initialize Anthropic client
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key or api_key == 'your_api_key_here':
        print(f"[ENRICHMENT] WARNING: No valid Anthropic API key found. Skipping enrichment for {company_name}")
        return jobs_list

    client = Anthropic(api_key=api_key)

    print(f"[ENRICHMENT] Starting enrichment for {company_name} ({len(jobs_list)} jobs)...")

    # Batch jobs for API efficiency
    batch_size = 8
    all_enriched_jobs = []

    for i in range(0, len(jobs_list), batch_size):
        batch = jobs_list[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(jobs_list) + batch_size - 1) // batch_size

        print(f"[ENRICHMENT] {company_name}: Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)...")

        # Create prompt for Claude
        jobs_json = json.dumps(batch, indent=2)

        prompt = f"""You are analyzing job postings for {company_name} to extract structured information.

**Task: Extract Information**
For each job, extract:
1. **Years of experience required** - Parse from description and provide:
   - min_years: minimum years (as integer, or null if not specified)
   - max_years: maximum years (as integer, or null if not specified or open-ended like "5+")
   Examples: "3-5 years" → min=3, max=5; "5+ years" → min=5, max=null; "Not specified" → min=null, max=null
2. **Educational requirements** - MUST be one of these exact values: "Associate's", "Bachelor's", "Master's", "PhD", or "Not specified". Choose the highest level mentioned.
3. **Job function/department** (e.g., "Engineering", "Product Management", "Sales")
4. **Specific team** if mentioned (e.g., "Payments Team", "Infrastructure", "Not specified")
5. **Job level** - Extract the seniority/level from the job title and description. Look for patterns like:
   - Junior, Senior, Staff, Principal, Distinguished
   - SWE I, SWE II, SWE III, SWE IV, Software Engineer I/II/III/IV
   - L3, L4, L5, L6, L7, L8 (level numbers)
   - IC3, IC4, IC5, IC6 (individual contributor levels)
   - Entry Level, Mid-Level, Senior Level
   - Engineer 1, Engineer 2, Engineer 3
   Return the exact level string found (e.g., "Senior", "SWE II", "L5", "IC4", "Junior"). If not specified, return "Not specified".

**Input Jobs:**
{jobs_json}

**Output Format:**
Return a JSON object with this structure:
{{
  "jobs": [
    {{
      "job_id": "the unique job ID (number only, e.g., '4316072852')",
      "extracted_info": {{
        "experience_min_years": 3 or null,
        "experience_max_years": 5 or null,
        "education": "Associate's" or "Bachelor's" or "Master's" or "PhD" or "Not specified",
        "function": "Engineering",
        "team": "Payments Team" or "Not specified",
        "job_level": "Senior" or "SWE II" or "L5" or "Not specified"
      }}
    }}
  ]
}}

IMPORTANT:
- Extract metadata for ALL jobs provided (do not skip any)
- Only return job IDs and extracted information (not full URLs or job objects)
- Job ID is the numeric identifier from the job (e.g., "4316072852")
- For experience bounds, use integers or null (not strings)
- For education, ONLY use these exact values: "Associate's", "Bachelor's", "Master's", "PhD", or "Not specified"
- For job_level, preserve the exact format found in the title/description
- Do NOT return the full job objects (descriptions, etc.) as they may be truncated

Return ONLY valid JSON, no other text."""

        # Retry logic with validation
        max_retries = 3
        retry_count = 0
        batch_success = False

        while retry_count < max_retries and not batch_success:
            try:
                if retry_count > 0:
                    print(f"[ENRICHMENT] {company_name}: Retry attempt {retry_count}/{max_retries - 1} for batch {batch_num}/{total_batches}")

                # Call Claude API with Haiku (cheapest model)
                message = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=4096,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

                # Parse Claude's response
                # Find the text content block
                response_text = None
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text = block.text
                        break

                if not response_text:
                    raise ValueError("No text content in Claude response")

                result = json.loads(response_text)

                # Validation 1: Check if we got the correct number of jobs
                returned_jobs = result.get('jobs', [])
                if len(returned_jobs) != len(batch):
                    print(f"[ENRICHMENT] {company_name}: WARNING - Expected {len(batch)} jobs, got {len(returned_jobs)}. Retrying...")
                    retry_count += 1
                    continue

                # Validation 2: Check if all required fields are present
                required_fields = ['experience_min_years', 'experience_max_years', 'education', 'function', 'team', 'job_level']
                all_fields_present = True

                for job_result in returned_jobs:
                    if 'job_id' not in job_result or 'extracted_info' not in job_result:
                        print(f"[ENRICHMENT] {company_name}: WARNING - Missing job_id or extracted_info. Retrying...")
                        all_fields_present = False
                        break

                    extracted = job_result['extracted_info']
                    missing_fields = [field for field in required_fields if field not in extracted]

                    if missing_fields:
                        print(f"[ENRICHMENT] {company_name}: WARNING - Missing fields {missing_fields} for job {job_result.get('job_id', 'unknown')}. Retrying...")
                        all_fields_present = False
                        break

                    # Validation 3: Check if education is one of the allowed values
                    allowed_education_values = ["Associate's", "Bachelor's", "Master's", "PhD", "Not specified"]
                    education_value = extracted.get('education', '')
                    if education_value not in allowed_education_values:
                        print(f"[ENRICHMENT] {company_name}: WARNING - Invalid education value '{education_value}' for job {job_result.get('job_id', 'unknown')}. Must be one of {allowed_education_values}. Retrying...")
                        all_fields_present = False
                        break

                if not all_fields_present:
                    retry_count += 1
                    continue

                # All validations passed - process the jobs
                original_jobs_by_id = {job['job_id']: job for job in batch}

                for job_result in returned_jobs:
                    job_id = job_result['job_id']
                    extracted = job_result['extracted_info']

                    # Find the original job object (with full data)
                    if job_id in original_jobs_by_id:
                        original_job = original_jobs_by_id[job_id]

                        # Add ONLY the extracted fields to the original job
                        original_job['experience_min_years'] = extracted.get('experience_min_years', None)
                        original_job['experience_max_years'] = extracted.get('experience_max_years', None)
                        original_job['education_required'] = extracted.get('education', 'Not specified')
                        original_job['function_extracted'] = extracted.get('function', 'Not specified')
                        original_job['team_extracted'] = extracted.get('team', 'Not specified')
                        original_job['job_level'] = extracted.get('job_level', 'Not specified')

                        # Add to enriched list (preserving ALL original data)
                        all_enriched_jobs.append(original_job)
                    else:
                        print(f"[ENRICHMENT] {company_name}: WARNING - Claude returned job_id not in batch: {job_id}")

                print(f"[ENRICHMENT] {company_name}: ✓ Successfully enriched {len(returned_jobs)} jobs with metadata")
                batch_success = True

            except json.JSONDecodeError as e:
                print(f"[ENRICHMENT] {company_name}: ERROR - Invalid JSON response. Retrying... ({retry_count + 1}/{max_retries})")
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"\n{'='*70}")
                    print(f"[ENRICHMENT] {company_name}: FAILED after {max_retries} attempts - JSON decode error")
                    print(f"{'='*70}")
                    traceback.print_exc()
                    print(f"\n[ENRICHMENT] {company_name}: Keeping all {len(batch)} jobs from this batch without enrichment")
                    print(f"{'='*70}\n")
                    all_enriched_jobs.extend(batch)

            except Exception as e:
                print(f"[ENRICHMENT] {company_name}: ERROR - {type(e).__name__}: {str(e)}")
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"\n{'='*70}")
                    print(f"[ENRICHMENT] {company_name}: FAILED after {max_retries} attempts")
                    print(f"{'='*70}")
                    print(f"Error Type: {type(e).__name__}")
                    print(f"Error Message: {str(e)}")
                    print(f"\nFull Traceback:")
                    print(f"{'-'*70}")
                    traceback.print_exc()
                    print(f"{'-'*70}")
                    if hasattr(e, '__dict__'):
                        print(f"\nError Attributes: {e.__dict__}")
                    print(f"\n[ENRICHMENT] {company_name}: Keeping all {len(batch)} jobs from this batch without enrichment")
                    print(f"{'='*70}\n")
                    all_enriched_jobs.extend(batch)

    print(f"[ENRICHMENT] {company_name}: Complete! Processed {len(all_enriched_jobs)} jobs\n")
    return all_enriched_jobs


def scrape_company_jobs(company_name_og):
    """
    Scrape all jobs for a single company from LinkedIn.

    Returns: Tuple of (company_name, list of jobs) or (None, []) on failure
    """
    print(f"[SCRAPING] Starting scrape for {company_name_og}...")

    company_jobs = []
    company_search_params = {
        "typeaheadType": "COMPANY",
        "query": company_name_og
    }

    # Retry logic for company lookup with exponential backoff
    company_response = None
    max_retries = 5
    for attempt in range(max_retries):
        try:
            company_response = requests.get(BASE_SEARCH_URL + COMPANY_SEARCH_PATH, company_search_params, verify=False, timeout=10)
            if company_response.status_code == 200:
                break
            elif company_response.status_code == 429:
                wait_time = 2 ** (attempt + 1)
                print(f"[SCRAPING] {company_name_og}: Rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
            else:
                print(f"[SCRAPING] {company_name_og}: Attempt {attempt + 1}/{max_retries} - Got status {company_response.status_code}")
                time.sleep(2)
        except Exception as e:
            print(f"[SCRAPING] {company_name_og}: Attempt {attempt + 1}/{max_retries} - Request failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)

    # Parse company response
    if company_response is None or company_response.status_code != 200:
        print(f"[SCRAPING] {company_name_og}: Failed to lookup company after {max_retries} attempts. Skipping.")
        return None, []

    try:
        company_id = company_response.json()[0]['id']
        company_name = company_response.json()[0]['displayName']
    except (KeyError, IndexError, ValueError) as e:
        print(f"[SCRAPING] {company_name_og}: Failed to parse company data - {e}")
        return None, []

    COMPANY_JOBS_PATH = "/jobs/api/seeMoreJobPostings/search"

    has_more_jobs = True
    job_next_start = 0
    job_link_elements = []

    # Paginate through all job listings
    while has_more_jobs:
        jsParams = {
            "f_C": company_id,
            "keywords": "software engineer",
            "start": job_next_start,
        }

        jobs_response = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                jobs_response = requests.get(BASE_SEARCH_URL + COMPANY_JOBS_PATH, jsParams, verify=False, timeout=10)
                if jobs_response.status_code == 200:
                    break
                elif jobs_response.status_code == 429:
                    wait_time = 2 ** (attempt + 1)
                    print(f"[SCRAPING] {company_name}: Pagination rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(wait_time)
                else:
                    print(f"[SCRAPING] {company_name}: Pagination attempt {attempt + 1}/{max_retries} - Got status {jobs_response.status_code}")
                    time.sleep(2)
            except Exception as e:
                print(f"[SCRAPING] {company_name}: Pagination attempt {attempt + 1}/{max_retries} - Request failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)

        if jobs_response is None or jobs_response.status_code != 200:
            print(f"[SCRAPING] {company_name}: Failed to fetch job page after {max_retries} attempts. Stopping pagination.")
            has_more_jobs = False
            break

        soup = BeautifulSoup(jobs_response.content)
        thisPull = soup.find_all('a', attrs={"class": "base-card__full-link"})

        if len(thisPull) == 0:
            print(f"[SCRAPING] {company_name}: No more jobs found. Pagination complete.")
            has_more_jobs = False
        else:
            job_link_elements += thisPull
            job_next_start += len(thisPull)

        print(f"[SCRAPING] {company_name}: Pulled {len(job_link_elements)} total jobs so far")

    print(f"[SCRAPING] {company_name}: Found {len(job_link_elements)} total jobs")

    # Process each job detail
    jobList = []
    for link in job_link_elements:
        jobTitle: str = str(link.find('span', attrs={"class": "sr-only"}).get_text()).strip()
        if jobTitle in jobList:
            continue

        job_url = str(link.attrs['href'])
        partial_link = job_url.split('?')[0]
        jobId = partial_link.split('-')[-1]

        # Retry logic for job detail requests
        job_desc_response = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                job_desc_response = requests.get(BASE_SEARCH_URL + "/jobs/api/jobPosting/" + jobId, verify=False, timeout=10)
                if job_desc_response.status_code == 200:
                    break
                elif job_desc_response.status_code == 429:
                    wait_time = 2 ** (attempt + 1)
                    print(f"[SCRAPING] {company_name}: Rate limited (429) for job {jobId}. Waiting {wait_time}s")
                    time.sleep(wait_time)
                else:
                    time.sleep(2)
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    job_desc_response = None

        if job_desc_response is None or job_desc_response.status_code != 200:
            continue

        if job_desc_response.status_code == 200:
            jobDescSoup = BeautifulSoup(job_desc_response.content)
            try:
                criteriaTags = jobDescSoup.find_all('span', attrs={"class": "description__job-criteria-text"})
                seniority = criteriaTags[0].get_text().strip()
                employmentType = criteriaTags[1].get_text().strip()
                jfunction = criteriaTags[2].get_text().strip()
                industry = criteriaTags[3].get_text().strip()
            except:
                seniority = "N/A"
                employmentType = "N/A"
                jfunction = "N/A"
                industry = "N/A"
            try:
                loc = jobDescSoup.find('span', attrs={"class": "topcard__flavor--bullet"}).get_text().strip()
            except:
                loc = "N/A"
            try:
                comp = jobDescSoup.find('div', attrs={"class": "salary"}).get_text().strip().split(' - ')[0].removesuffix('/yr')
            except:
                comp = "0"
            try:
                desc = jobDescSoup.find('div', attrs={"class": "description__text"}).find('div', attrs={"class": "show-more-less-html__markup"}).get_text(separator="\n").strip()
            except:
                desc = "N/A"
            try:
                title = jobDescSoup.find('h2', attrs={"class": "top-card-layout__title"}).get_text().strip()
            except:
                title = "N/A"

            job_url_full = job_desc_response.url
            extracted_job_id = job_url_full.split('/')[-1]

            company_jobs.append({
                "job_id": extracted_job_id,
                "desc": desc,
                "comp": comp,
                "title": title,
                "url": job_url_full,
                "loc": loc,
                "company": company_name,
                "company_classification": get_company_classification(company_name_og),
                "seniority": seniority,
                "employmentType": employmentType,
                "Job Function": jfunction,
                "industry": industry
            })
            jobList.append(title)

    print(f"[SCRAPING] {company_name}: Complete! Scraped {len(company_jobs)} jobs\n")
    return company_name, company_jobs


jobs = []

# Ask user whether to append or replace output
print("\n" + "="*50)
print("Output Mode Selection")
print("="*50)
if os.path.exists('output.json'):
    print("Existing output.json file found.")
    while True:
        mode = input("Do you want to (A)ppend to existing data or (R)eplace it? [A/R]: ").strip().upper()
        if mode in ['A', 'R']:
            break
        print("Invalid input. Please enter 'A' for append or 'R' for replace.")

    if mode == 'A':
        print("→ Appending mode: New jobs will be added to existing output.json")
        try:
            with open('output.json', 'r') as f:
                existing_jobs = json.load(f)
                if isinstance(existing_jobs, list):
                    jobs = existing_jobs
                    print(f"  Loaded {len(jobs)} existing jobs")
                else:
                    print("  Warning: Existing output.json is not a list. Starting fresh.")
        except Exception as e:
            print(f"  Error loading existing file: {e}. Starting fresh.")
    else:
        print("→ Replace mode: output.json will be overwritten")
else:
    print("No existing output.json found. Creating new file.")  
print("="*50 + "\n")


# List of companies to scrape
companies_to_scrape = ["Salesforce"]

print(f"\n{'='*50}")
print(f"Starting concurrent job scraping for {len(companies_to_scrape)} companies")
print(f"{'='*50}\n")

# Use ThreadPoolExecutor for background enrichment
# Max 3 companies can be enriched concurrently
with ThreadPoolExecutor(max_workers=3) as executor:
    enrichment_futures = {}

    # Sequentially scrape each company
    for company_name_og in companies_to_scrape:
        # Scrape the company (sequential, one at a time)
        company_name, company_jobs = scrape_company_jobs(company_name_og)

        # If scraping failed, skip enrichment
        if company_name is None or not company_jobs:
            print(f"[MAIN] Skipping enrichment for {company_name_og} (no jobs scraped)\n")
            continue

        # Submit enrichment to background thread
        print(f"[MAIN] Submitting {company_name} for background enrichment (while continuing to scrape next company)\n")
        future = executor.submit(enrich_jobs_with_claude, company_jobs, company_name)
        enrichment_futures[future] = company_name

    print(f"\n{'='*50}")
    print(f"All companies scraped! Waiting for enrichment to complete...")
    print(f"{'='*50}\n")

    # Collect results as they complete
    for future in as_completed(enrichment_futures):
        company_name = enrichment_futures[future]
        try:
            enriched_jobs = future.result()
            jobs.extend(enriched_jobs)
            print(f"[MAIN] Collected enriched results for {company_name} ({len(enriched_jobs)} jobs)\n")
        except Exception as e:
            print(f"[MAIN] ERROR: Enrichment failed for {company_name}: {str(e)}\n")

print(f"\n{'='*50}")
print(f"All processing complete! Total jobs collected: {len(jobs)}")
print(f"{'='*50}\n")

with open('output.json', 'w') as f:
    json.dump(jobs, f)

    



    



