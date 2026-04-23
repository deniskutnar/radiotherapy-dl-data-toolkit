"""Template configuration for the GPU export workflow.

Copy this file to `gpu_export_config.py` and replace all placeholders.
Do not commit real credentials, hostnames, or storage paths.
"""

RESEARCH_COURSE_ID = "C99_RESEARCH"
READY_FLAG = "Done"
CSV_PATH = r"PATH/TO/filtered_records_UID.csv"
OUTPUT_ROOT = r"PATH/TO/GPU_EXPORT_ROOT"
TEMP_EXPORT_DIR = r"PATH/TO/TEMP_EXPORT"
SKIP_ROW_INDICES = []
START_INDEX = 0
END_INDEX = 10

# Optional label used when creating the PyESAPI application.
PYESAPI_APP_NAME = "python_demo"
