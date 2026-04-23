# Plan setup and optimisation

## Purpose
Create a new research-compatible baseline IMRT plan in the writable research Eclipse instance, using the previously exported planning parameters and transferred CT / RTSTRUCT data.

## What this script does
1. reads the cohort CSV and the matching parameter text file
2. resolves the patient record, optionally via SQL lookup from image Series UID
3. matches the transferred CT series and RTSTRUCT by UID inside Eclipse
4. creates a new research structure set and copies eligible structures
5. creates a new course / plan
6. recreates beam geometry, prescription, and optimisation objectives
7. runs IMRT optimisation, leaf motion calculation, and dose calculation
8. updates the cohort CSV with a status marker such as `Done`

## Inputs
- cohort CSV with patient / plan metadata
- parameter text files from `01_extraction_of_planning_parameters_from_the_clinical_plan`
- transferred CT and RTSTRUCT objects already present in the research environment
- writable ESAPI session in a research Eclipse instance

## Outputs
- reconstructed baseline IMRT plan in the research environment
- updated cohort CSV tracking reconstruction status

## Included material
- `rebuild_baseline_plan.cs` — fuller sanitized reconstruction / optimisation script
- `reconstruction.example.yaml` — example local settings template

## Notes
- All infrastructure identifiers are placeholders and must be replaced locally.
- The script keeps the thesis logic visible, rather than turning it into a generic software package.
- Because this step modifies plans, `[assembly: ESAPIScript(IsWriteable = true)]` must remain enabled.
