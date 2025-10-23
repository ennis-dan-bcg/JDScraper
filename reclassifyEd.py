import json
import re
from collections import defaultdict

def standardize_education(education_str):
    """
    Standardize education requirement to one of:
    - "Bachelor's"
    - "Master's"
    - "PhD"
    - "Associate's"
    - "Not specified"

    Always returns the LOWEST degree when multiple are listed.
    """
    if not education_str or education_str.strip() == "":
        return "Not specified"

    # Normalize the string
    edu = education_str.strip()
    edu_lower = edu.lower()

    # Check for "Not specified" first
    if edu_lower == "not specified":
        return "Not specified"

    # Check for Associate's
    if "associate" in edu_lower:
        return "Associate's"

    # Check for Bachelor's patterns (including when listed with higher degrees)
    # Pattern: Contains bachelor's or BS
    bachelor_patterns = [
        r"bachelor",
        r"\bbs\b",
        r"\bba\b",
        r"\bb\.s\.",
        r"\bb\.a\.",
        r"engineering graduate"  # Special case per user request
    ]

    has_bachelors = any(re.search(pattern, edu_lower) for pattern in bachelor_patterns)

    # Check for Master's patterns
    master_patterns = [
        r"master",
        r"\bms\b",
        r"\bma\b",
        r"\bm\.s\.",
        r"\bm\.a\.",
        r"\bmsc\b",
        r"graduate degree",
        r"advanced degree"
    ]

    has_masters = any(re.search(pattern, edu_lower) for pattern in master_patterns)

    # Check for PhD patterns
    phd_patterns = [
        r"phd",
        r"ph\.d",
        r"doctorate"
    ]

    has_phd = any(re.search(pattern, edu_lower) for pattern in phd_patterns)

    # Apply rule: Return LOWEST degree when multiple are present
    if has_bachelors:
        return "Bachelor's"
    elif has_masters:
        return "Master's"
    elif has_phd:
        return "PhD"
    else:
        # Couldn't classify - return original but warn
        print(f"  WARNING: Could not classify education requirement: '{education_str}'")
        return "Not specified"


def main():
    print("="*60)
    print("Education Requirement Standardization Script")
    print("="*60)

    # Load output.json
    print("\nLoading output.json...")
    try:
        with open('output.json', 'r', encoding='utf-8') as f:
            jobs = json.load(f)
    except FileNotFoundError:
        print("ERROR: output.json not found!")
        return
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in output.json: {e}")
        return

    print(f"Loaded {len(jobs)} jobs")

    # Track changes
    changes = defaultdict(lambda: defaultdict(int))
    unchanged = 0

    # Process each job
    print("\nStandardizing education requirements...")
    for job in jobs:
        original_edu = job.get('education_required', 'Not specified')
        standardized_edu = standardize_education(original_edu)

        # Track the change
        if original_edu != standardized_edu:
            changes[standardized_edu][original_edu] += 1
            job['education_required'] = standardized_edu
        else:
            unchanged += 1

    # Save back to output.json
    print("\nSaving standardized data to output.json...")
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    # Count final distribution
    final_counts = defaultdict(int)
    for job in jobs:
        final_counts[job.get('education_required', 'Not specified')] += 1

    print("\nFinal Education Distribution:")
    for edu_level in ["Bachelor's", "Master's", "PhD", "Associate's", "Not specified"]:
        count = final_counts.get(edu_level, 0)
        percentage = (count / len(jobs) * 100) if jobs else 0
        print(f"  {edu_level:15s}: {count:4d} ({percentage:5.1f}%)")

    print(f"\nJobs changed: {sum(sum(v.values()) for v in changes.values())}")
    print(f"Jobs unchanged: {unchanged}")

    if changes:
        print("\nDetailed Changes:")
        for standardized, original_values in sorted(changes.items()):
            print(f"\n  Standardized to '{standardized}':")
            for original, count in sorted(original_values.items(), key=lambda x: -x[1]):
                print(f"    '{original}' -> {count} job(s)")

    print("\n" + "="*60)
    print("Standardization complete!")
    print("="*60)


if __name__ == "__main__":
    main()
