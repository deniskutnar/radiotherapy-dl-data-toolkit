"""Extract clinically relevant planning parameters through PyESAPI.

This script mirrors the parameter pooling step used prior to baseline
reconstruction. The public version is schematic and uses placeholders where
site-specific object access patterns may differ.
"""

from __future__ import annotations

import atexit
from pathlib import Path

import pandas as pd

# import pyesapi  # Uncomment in a configured local environment


def sanitize_plan_id(plan_id: str) -> str:
    return plan_id.replace(":", "~").replace(",", "~")


def main() -> None:
    # app = pyesapi.CustomScriptExecutable.CreateApplication("python_demo")
    # atexit.register(app.Dispose)

    records = pd.read_csv("filtered_records.csv")
    output_dir = Path("parameter_pool")
    output_dir.mkdir(exist_ok=True)

    for _, row in records.iterrows():
        patient_id = row["patient_id"]
        plan_id = row["plan_id"]
        course_id = row["course_id"]

        # In a private deployment, replace this block with real PyESAPI access.
        # Example outputs shown here are synthetic.
        output_file = output_dir / f"{patient_id}_{course_id}_{sanitize_plan_id(plan_id)}_parameters.txt"
        with output_file.open("w", encoding="utf-8") as handle:
            handle.write(f"{patient_id}\n")
            handle.write("1.2.840.synthetic.image.series\n")
            handle.write("1.2.840.synthetic.image.study\n")
            handle.write("1.2.840.synthetic.struct.uid\n")
            handle.write("1.2.840.synthetic.struct.series\n")
            handle.write("1.2.840.synthetic.struct.study\n")
            handle.write("0.0\n0.0\n0.0\n")
            handle.write("17\n100\n1.8\n100\n")
            handle.write("PTV_MAIN, Lower, 30 Gy, 100, 120\n")
            handle.write("HEART, Upper, 12 Gy, 40, 90\n")

        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
