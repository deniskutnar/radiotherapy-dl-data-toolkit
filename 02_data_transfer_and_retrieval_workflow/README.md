# Data transfer and retrieval workflow

This section corresponds to the thesis subsection **“Data transfer and retrieval workflow.”**

## Purpose
Retrieve the relevant DICOM planning objects for each selected case, verify the expected UIDs, and move the required image and structure objects from the source environment into the research environment.

## Inputs
- `filtered_records.csv` cohort table
- parameter text files generated during plan-parameter extraction
- configured DICOM source, destination, and local calling nodes
- UID references for the CT image series and RTSTRUCT object

## Outputs
- C-FIND summary of all discovered modalities
- UID-level validation of matched study / series / SOP instance objects
- selective C-MOVE transfer of the CT series and RTSTRUCT
- console transfer log for queue progress and response status

## Included material
- `move_patient_data.cs` — sanitized ESAPI + EvilDICOM implementation for UID-based C-FIND and C-MOVE
- `dicom_nodes.example.json` — example node configuration
- `workflow_diagram.png` and `workflow_diagram.svg`

## Notes
The public version keeps the full modality search block for `RTPLAN`, `RTDOSE`, `CT`, `RTSTRUCT`, and `RTIMAGE`, because that verification step is part of the documented workflow. All AE titles, hostnames, ports, and file paths are placeholders and must be replaced locally.
