import argparse
import csv
import json
import logging
import sys
import time
import csv
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest"
COMPANY_SEARCH_PATH="/api/typeaheadHits"

STARTUP_COMPANY_NAMES  = ["Lovable", "Hugging Face", "OpenAI", "Replit", "Anthropic", "Scale AI", "Glean", "Perplexity"]
INSURANCE_COMPANY_NAMES  = ["Chubb","AIG", "The Hartford", "Farmers", "Progressive", "Nationwide", "Allstate", "Geico", "State Farm", "Zurich"]
TECH_COMPANY_NAMES  = [ "Meta", "Amazon", "Alphabet", "Microsoft", "Netflix", "Nvidia", "Stripe", "Apple", "Shopify", "Walmart"]

ALL_COMPANY_NAMES = STARTUP_COMPANY_NAMES + INSURANCE_COMPANY_NAMES + TECH_COMPANY_NAMES


jobs = []


for company_name_og in ALL_COMPANY_NAMES:
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
            "keywords" : "data engineer",
            "start" : job_next_start,
        }
        jobs_response = requests.get(BASE_SEARCH_URL + COMPANY_JOBS_PATH,jsParams, verify=False)
        print(jobs_response.url)
        soup = BeautifulSoup(jobs_response.content)
        thisPull = soup.find_all('a', attrs={"class" : "base-card__full-link"})
        has_more_jobs = len(thisPull) >= 1
        job_link_elements += thisPull
        job_next_start += len(thisPull)
        print('Pulled jobs for ' + company_name + ":", len(job_link_elements))

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
        # print(jobId)
        job_desc_response = requests.get(BASE_SEARCH_URL + "/jobs/api/jobPosting/" + jobId, verify=False)
        # print(job_desc_response.status_code)
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


            jobs.append({
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

with open('output.json', 'w') as f:
    json.dump(jobs, f)

    



    



