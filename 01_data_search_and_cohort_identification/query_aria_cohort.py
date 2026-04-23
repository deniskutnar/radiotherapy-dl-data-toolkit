"""Query retrospective cohort candidates from ARIA.

This script is a cleaned research-facing version of the cohort identification step.
It illustrates the filtering logic described in the thesis chapter while removing
site-specific credentials and deployment details.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set


INCLUDED_APPROVAL_STATUS = {
    "Completed",
    "PlanApproval",
    "CompletedEarly",
    "TreatApproval",
    "ExternalApproval",
    "Retired",
}

PLAN_PREFIX_INCLUDE = ("hn",)
PLAN_PREFIX_EXCLUDE = ("cm000", "qa")
EXCLUDE_MACHINES = {"MACHINE_A", "MACHINE_B", "MACHINE_C"}
YEAR_START = 2009
YEAR_END = 2021


@dataclass
class PlanRecord:
    patient_id: str
    course_ser: str
    course_id: str
    plan_setup_id: str
    plan_uid: str
    status: str


def uid_to_datetime(uid: str) -> dt.datetime:
    """Parse the timestamp encoded in a DICOM-like UID tail.

    This mirrors the logic used in the original workflow.
    """
    return dt.datetime.strptime(uid.split(".")[-1], "%Y%m%d%H%M%S")


def include_plan(record: PlanRecord) -> bool:
    plan_name = record.plan_setup_id.lower()
    course_name = record.course_id.lower()

    if record.status not in INCLUDED_APPROVAL_STATUS:
        return False
    if "qa" in plan_name or "qa" in course_name:
        return False
    if not plan_name.startswith(PLAN_PREFIX_INCLUDE):
        return False
    if plan_name.startswith(PLAN_PREFIX_EXCLUDE):
        return False

    try:
        plan_time = uid_to_datetime(record.plan_uid)
    except Exception:
        return False

    return YEAR_START <= plan_time.year <= YEAR_END


def get_treatment_machines(plan_uid: str) -> Set[str]:
    """Placeholder for machine lookup against treatment records.

    Replace with site-specific query logic in a private deployment.
    """
    _ = plan_uid
    return set()


def deduplicate(records: Iterable[PlanRecord]) -> List[PlanRecord]:
    seen_uids: Set[str] = set()
    unique: List[PlanRecord] = []
    for record in records:
        if record.plan_uid in seen_uids:
            continue
        seen_uids.add(record.plan_uid)
        unique.append(record)
    return unique


def export_csv(records: Sequence[PlanRecord], output_csv: str) -> None:
    with open(output_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["patient_id", "plan_id", "course_id", "status", "plan_uid"])
        for rec in records:
            writer.writerow([rec.patient_id, rec.plan_setup_id, rec.course_id, rec.status, rec.plan_uid])


def main() -> None:
    # TODO: Replace this synthetic list with a real site-approved database query.
    raw_records = [
        PlanRecord("SYNTHETIC_0001", "1", "COURSE_01", "HN_PLAN_A", "1.2.3.20200101120000", "Completed"),
        PlanRecord("SYNTHETIC_0002", "2", "COURSE_02", "HN_PLAN_B", "1.2.3.20210101120000", "TreatApproval"),
    ]

    filtered = []
    for rec in raw_records:
        if not include_plan(rec):
            continue
        if get_treatment_machines(rec.plan_uid) & EXCLUDE_MACHINES:
            continue
        filtered.append(rec)

    unique = deduplicate(filtered)
    export_csv(unique, "filtered_records.csv")
    print(f"Exported {len(unique)} filtered records")


if __name__ == "__main__":
    main()
