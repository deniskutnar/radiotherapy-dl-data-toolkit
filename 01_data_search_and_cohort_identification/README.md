# Data search and cohort identification

This section corresponds to the thesis subsection **“Data search and cohort identification.”**

## Purpose
Identify an eligible retrospective lymphoma cohort from the oncology information system in a reproducible way.

## Inputs
- ARIA / oncology information system access
- approval status filters
- plan naming conventions
- date constraints
- machine exclusion rules

## Outputs
- filtered cohort table
- patient identifiers / plan identifiers for downstream retrieval

## Included material
- `query_aria_cohort.py` — sanitized example of the cohort query logic
- `filtered_records.example.csv` — example of a downstream cohort table

## Notes
All database hosts, usernames, passwords, identifiers, and local conventions are placeholders and must be replaced locally.
