# Export to GPU server and research image reconstruction

This subsection contains the post-planning export workflow used to convert research plans into deep-learning-ready arrays.

## Rationale

After the research plan has been created and calculated in Eclipse, additional scripting is needed to:

1. read CT, dose, beam dose, and fluence data through PyESAPI,
2. restore physical image geometry,
3. resample data into a consistent research grid,
4. derive beam-oriented views,
5. export arrays to the GPU or research storage.

## Input

- `filtered_records_UID.csv` with processed cases marked as ready
- a completed research plan in the research course
- PyESAPI access to dose, beams, structures, and image geometry
- local helper utilities for image restoration, resampling, BEV conversion, and export

## Output

For each selected case, the export step can generate:

- `full_ct.npy`
- `full_dose.npy`
- `masks.npy`
- `dd_raw*.npy`
- `dd*.npy`
- `ct*.npy`
- `fm*.npy`
- lightweight label files such as `target_id.npy` and `oars_id.npy`

## Files in this folder

- `gpu_export_config_template.py` – environment-specific placeholders
- `gpu_export_utils.py` – reusable geometry and export helpers
- `export_research_plan_to_gpu.py` – clean end-to-end export workflow

## Practical note

The original project code evolved iteratively and existed in several variants. The script here is a cleaned, chapter-oriented version that preserves the key logic while removing site-specific details.
