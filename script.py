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
jobs = []

COMPANY_JOBS_PATH = "/jobs/api/seeMoreJobPostings/search"

MAX_JOBS = 1000

has_more_jobs = True
job_next_start = 0
job_card_elements = []

while (has_more_jobs and len(job_card_elements) < MAX_JOBS) :
    jsParams = {
        "keywords" : "technical engineer",
        # "f_E" : "2",
        "start" : job_next_start,
    }
    jobs_response = requests.get(BASE_SEARCH_URL + COMPANY_JOBS_PATH,jsParams, verify=False)
    soup = BeautifulSoup(jobs_response.content)
    thisPull = soup.find_all('div', attrs={"class" : "job-search-card"})
    has_more_jobs = len(thisPull) >= 1
    job_card_elements += thisPull
    job_next_start += len(thisPull)
    # print(thisPull[0])
    print('Pulled jobs: ', len(job_card_elements))

print('Total Jobs:', len(job_card_elements))
jobList = []
for card in job_card_elements:
        jobTitle: str = str(card.find('span', attrs={"class" : "sr-only"}).get_text()).strip()
        company: str = card.find('h4', attrs={"class" : "base-search-card__subtitle"}).get_text().strip()
        if jobTitle + company in jobList:
            print("Skipping " + jobTitle + " at " + company + ", already in list.")
            continue
        # print("Processing " +  jobTitle + " at " + company)
        link = card.find('a', attrs={"class" : "base-card__full-link"})
        job_url = str(link.attrs['href'])
        partial_link = job_url.split('?')[0]
        jobId = partial_link.split('-')[-1]
        # print(jobId)
        try:
            job_desc_response = requests.get(BASE_SEARCH_URL + "/jobs/api/jobPosting/" + jobId, verify=False)
        except:
            print("Something went wrong fetching this job.", file=sys.stderr)
            continue
        # print(job_desc_response.status_code)
        if(job_desc_response.status_code == 200):
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
                "company" : company,
                "seniority" : seniority,
                "employmentType" : employmentType,
                "Job Function" : jfunction,
                "industry" : industry

            })
            print("Processed Job: ", title, company, jobId, loc, comp)
            jobList.append(title+company)

with open('output.json', 'w') as f:
    json.dump(jobs, f)

    



    



