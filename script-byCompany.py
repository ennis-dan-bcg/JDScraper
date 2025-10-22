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

import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest"
COMPANY_SEARCH_PATH="/api/typeaheadHits"

STARTUP_COMPANY_NAMES  = ["Lovable", "Hugging Face", "Replit", "Anthropic", "Scale AI", "Glean", "Perplexity"]
INSURANCE_COMPANY_NAMES  = ["Chubb","AIG", "The Hartford", "Farmers", "Progressive", "Nationwide", "Allstate", "Geico", "State Farm", "Zurich"]
TECH_COMPANY_NAMES  = [ "Meta", "Amazon", "Alphabet", "Microsoft", "Netflix", "Nvidia", "Stripe", "Apple", "Shopify", "Walmart"]

ALL_COMPANY_NAMES = STARTUP_COMPANY_NAMES + INSURANCE_COMPANY_NAMES + TECH_COMPANY_NAMES


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
        print(f"WARNING: No valid Anthropic API key found. Skipping deduplication for {company_name}")
        return jobs_list

    client = Anthropic(api_key=api_key)

    print(f"\nEnriching {len(jobs_list)} jobs for {company_name} with Claude metadata...")

    # Batch jobs for API efficiency (10-15 jobs per batch)
    batch_size = 12
    all_enriched_jobs = []

    for i in range(0, len(jobs_list), batch_size):
        batch = jobs_list[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(jobs_list) + batch_size - 1) // batch_size

        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)...")

        # Create prompt for Claude
        jobs_json = json.dumps(batch, indent=2)

        prompt = f"""You are analyzing job postings for {company_name} to extract structured information.

**Task: Extract Information**
For each job, extract:
1. **Years of experience required** (parse from description, look for "X+ years", "X-Y years", etc. Return as a number or range like "3-5". If not specified, return "Not specified")
2. **Educational requirements** (Bachelor's, Master's, PhD, or "Not specified")
3. **Job function/department** (e.g., "Engineering", "Product Management", "Sales")
4. **Specific team** if mentioned (e.g., "Payments Team", "Infrastructure", "Not specified")

**Input Jobs:**
{jobs_json}

**Output Format:**
Return a JSON object with this structure:
{{
  "jobs": [
    {{
      "job_url": "the unique job URL",
      "extracted_info": {{
        "years_experience": "3-5" or "5+" or "Not specified",
        "education": "Bachelor's" or "Master's" or "PhD" or "Not specified",
        "function": "Engineering",
        "team": "Payments Team" or "Not specified"
      }}
    }}
  ]
}}

IMPORTANT:
- Extract metadata for ALL jobs provided (do not skip any)
- Only return job URLs and extracted information
- Do NOT return the full job objects (descriptions, etc.) as they may be truncated

Return ONLY valid JSON, no other text."""

        try:
            # Call Claude API with Haiku (cheapest model)
            message = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Parse Claude's response
            response_text = message.content[0].text
            result = json.loads(response_text)

            # Create a mapping of original jobs by URL for fast lookup
            original_jobs_by_url = {job['url']: job for job in batch}

            # Process all jobs and add extracted metadata
            for job_result in result.get('jobs', []):
                job_url = job_result['job_url']
                extracted = job_result['extracted_info']

                # Find the original job object (with full data)
                if job_url in original_jobs_by_url:
                    original_job = original_jobs_by_url[job_url]

                    # Add ONLY the extracted fields to the original job
                    original_job['years_experience'] = extracted.get('years_experience', 'Not specified')
                    original_job['education_required'] = extracted.get('education', 'Not specified')
                    original_job['function_extracted'] = extracted.get('function', 'Not specified')
                    original_job['team_extracted'] = extracted.get('team', 'Not specified')

                    # Add to enriched list (preserving ALL original data)
                    all_enriched_jobs.append(original_job)
                else:
                    print(f"    WARNING: Claude returned URL not in batch: {job_url}")

            print(f"    Enriched {len(result.get('jobs', []))} jobs with metadata")

        except Exception as e:
            print(f"    ERROR processing batch: {str(e)}")
            print(f"    Keeping all {len(batch)} jobs from this batch without enrichment")
            all_enriched_jobs.extend(batch)

    print(f"  Enrichment complete: {len(all_enriched_jobs)} jobs processed\n")
    return all_enriched_jobs


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


for company_name_og in STARTUP_COMPANY_NAMES:
    company_jobs = []  # Collect jobs for this company
    company_search_params= {
    "typeaheadType":"COMPANY",
    "query": company_name_og
}

    company_response = requests.get(BASE_SEARCH_URL + COMPANY_SEARCH_PATH, company_search_params, verify=False)

    # print(company_response.json())
    try:
        company_id = company_response.json()[0]['id']
        company_name = company_response.json()[0]['displayName']
    except:
        print("Something went wrong trying to find ", company_name_og, company_response.status_code, company_response.content)
        continue

    COMPANY_JOBS_PATH = "/jobs/api/seeMoreJobPostings/search"

    has_more_jobs = True
    job_next_start = 0
    job_link_elements = []

    while has_more_jobs:
        jsParams = {
            "f_C" : company_id,
            "keywords" : "software engineer",
            "start" : job_next_start,
        }
        jobs_response = requests.get(BASE_SEARCH_URL + COMPANY_JOBS_PATH,jsParams, verify=False)
        print(jobs_response.url)
        soup = BeautifulSoup(jobs_response.content)
        thisPull = soup.find_all('a', attrs={"class" : "base-card__full-link"})

        # Stop if we get no results OR if we're getting the same results (pagination ended)
        if len(thisPull) == 0:
            has_more_jobs = False
        else:
            job_link_elements += thisPull
            job_next_start += len(thisPull)

        print('Pulled jobs for ' + company_name + ":", len(job_link_elements))

        # Add delay to avoid rate limiting
        time.sleep(0.5)

    print('Total Jobs:', len(job_link_elements))
    jobList = []
    for link in job_link_elements:
        jobTitle: str = str(link.find('span', attrs={"class" : "sr-only"}).get_text()).strip()
        if jobTitle in jobList:
            print("Skipping " + jobTitle + ", already in list.")
            continue
        print("Processing ", jobTitle)
        job_url = str(link.attrs['href'])
        partial_link = job_url.split('?')[0]
        jobId = partial_link.split('-')[-1]

        # Retry logic for job detail requests
        job_desc_response = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                job_desc_response = requests.get(BASE_SEARCH_URL + "/jobs/api/jobPosting/" + jobId, verify=False, timeout=10)
                if job_desc_response.status_code == 200:
                    break
                else:
                    print(f"  Attempt {attempt + 1}/{max_retries}: Got status {job_desc_response.status_code}")
                    time.sleep(1)
            except Exception as e:
                print(f"  Attempt {attempt + 1}/{max_retries}: Request failed - {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    print(f"  Skipping job after {max_retries} failed attempts")
                    job_desc_response = None

        if job_desc_response is None or job_desc_response.status_code != 200:
            continue

        if(job_desc_response.status_code == 200):
            # print(job_desc_response.url)
            jobDescSoup = BeautifulSoup(job_desc_response.content)
            try:
                criteriaTags = jobDescSoup.find_all('span', attrs={"class" : "description__job-criteria-text"})
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
                loc = jobDescSoup.find('span', attrs={"class" : "topcard__flavor--bullet"}).get_text().strip()
            except:
                loc = "N/A"
            try:
                comp = jobDescSoup.find('div', attrs={"class" : "salary"}).get_text().strip().split(' - ')[0].removesuffix('/yr')
            except: 
                comp = "0"
            try:
                 desc = jobDescSoup.find('div', attrs={"class" : "description__text"}).find('div', attrs={"class" : "show-more-less-html__markup"}).get_text(separator="\n").strip()
            except:
                desc = "N/A"
            try:
                title = jobDescSoup.find('h2', attrs={"class" : "top-card-layout__title"}).get_text().strip()
            except:
                title = "N/A"


            company_jobs.append({
                "desc" : desc,
                "comp" : comp,
                "title" : title,
                "url" : job_desc_response.url,
                "loc" : loc,
                "company" : company_name,
                "seniority" : seniority,
                "employmentType" : employmentType,
                "Job Function" : jfunction,
                "industry" : industry

            })
            print("Processed Job: ", title, company_name, jobId, loc, comp)
            jobList.append(title)

            # Add delay between job detail requests to avoid rate limiting
            time.sleep(0.3)

    # Enrich jobs for this company with Claude metadata
    enriched_company_jobs = enrich_jobs_with_claude(company_jobs, company_name)
    jobs.extend(enriched_company_jobs)

with open('output.json', 'w') as f:
    json.dump(jobs, f)

    



    



