# 03. Plan generation

This section documents the scripting layer that converts a transferred clinical case into a reproducible research plan and then exports deep-learning-ready data to the GPU environment.

## Purpose

The overall goal of this stage is to turn a clinically approved reference plan into a standardised research representation that can be reused for model development.

## Subsections

### 01. Extraction of planning parameters from the clinical plan
Extracts the minimum set of parameters required to reproduce a plan in the research environment, including image and structure identifiers, isocentre, prescription settings, and optimisation objectives.

**Input:** clinical plan available through ESAPI/PyESAPI.  
**Output:** parameter text files used by downstream scripts.

### 02. Plan setup and optimisation
Creates a new writable research plan, recreates beams and optimisation objectives, runs optimisation, calculates leaf motions, and computes dose.

**Input:** exported parameter file plus the transferred image/RTSTRUCT objects.  
**Output:** research plan in Eclipse.

### 03. Export to GPU server and research image reconstruction
Exports CT, dose, beam dose, fluence-map-derived arrays, and structure masks into a research file layout suitable for downstream deep learning pipelines.

**Input:** completed research plan in Eclipse plus CSV queue of processed cases.  
**Output:** `.npy` volumes on the GPU or research storage.

## Figure

See `../figures/workflow_diagram.png` for the chapter-level overview of this section.

## Notes

- All examples are sanitised. Replace placeholder paths, machine names, storage roots, and credentials with local values.
- The exported arrays are intentionally shown as a practical outcome of the scripting framework rather than a full productised software package.
- Write-enabled ESAPI access is required for subsection 02. Read-only access is sufficient for subsection 03.
