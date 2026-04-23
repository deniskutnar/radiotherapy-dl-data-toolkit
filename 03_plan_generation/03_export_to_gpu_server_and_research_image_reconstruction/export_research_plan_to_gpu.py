"""Clean export workflow for the chapter subsection
"Export to GPU server and research image reconstruction".

This script is a sanitised and consolidated version of the original project code.
It exports CT, dose, beam dose, fluence maps, structure masks, and lightweight
label metadata from a completed research plan.
"""

import atexit
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import runpy
import SimpleITK as sitk

import pyesapi

from gpu_export_config_template import (
    CSV_PATH,
    END_INDEX,
    OUTPUT_ROOT,
    PYESAPI_APP_NAME,
    READY_FLAG,
    RESEARCH_COURSE_ID,
    SKIP_ROW_INDICES,
    START_INDEX,
    TEMP_EXPORT_DIR,
)
from gpu_export_utils import (
    image_to_bev,
    resample_by_spacing,
    resample_to_target,
    restore_info_image,
    revert_scaling_factor,
    rotate_image_sitk,
    save_numpy,
)


app = pyesapi.CustomScriptExecutable.CreateApplication(PYESAPI_APP_NAME)
atexit.register(app.Dispose)


aria_access = runpy.run_path("../01_data_search_and_cohort_identification/aria_access.py")
aria_cursor = aria_access["cursor"]


def lookup_patient_id_from_series_uid(series_uid: str) -> str:
    query = f"""
    SELECT Patient.PatientId, Series.SeriesUID
    FROM Patient, Study, Series
    WHERE Study.PatientSer = Patient.PatientSer
      AND Series.StudySer = Study.StudySer
      AND Series.SeriesUID IN ('{series_uid}')
    """
    aria_cursor.execute(query)
    rows = aria_cursor.fetchall()
    if not rows:
        raise RuntimeError(f"No patient found for series UID: {series_uid}")
    return rows[0][0]


def prepare_case_output_dir(patient_id: str, plan_id: str) -> str:
    safe_plan_id = plan_id.replace(":", "~").replace(",", "~")
    case_dir = os.path.join(OUTPUT_ROOT, patient_id, safe_plan_id)
    os.makedirs(case_dir, exist_ok=True)
    return case_dir


def crop_or_pad_superior_inferior(volume: np.ndarray, center_index: int, half_width: int, fill_value: float) -> np.ndarray:
    if center_index + half_width < volume.shape[0]:
        volume = volume[: center_index + half_width, :, :]
    else:
        pad = (center_index + half_width) - volume.shape[0]
        volume = np.pad(volume, ((0, pad), (0, 0), (0, 0)), mode="constant", constant_values=fill_value)

    if center_index - half_width > 0:
        volume = volume[center_index - half_width :, :, :]
    else:
        pad = abs(center_index - half_width)
        volume = np.pad(volume, ((pad, 0), (0, 0), (0, 0)), mode="constant", constant_values=fill_value)
    return volume


def export_case(row: pd.Series) -> None:
    image_series_uid = row.iloc[0]
    plan_id = row.iloc[1]
    patient_id = lookup_patient_id_from_series_uid(image_series_uid)

    app.ClosePatient()
    patient = app.OpenPatientById(patient_id)
    plan = patient.CoursesLot(RESEARCH_COURSE_ID).PlanSetupsLot(plan_id)
    plan.DoseValuePresentation = plan.DoseValuePresentation.Relative

    output_dir = prepare_case_output_dir(patient_id, plan_id)

    ct_np = plan.StructureSet.Image.np_array_like()
    ct_esapi = plan.StructureSet.Image
    dose_np = plan.Dose.np_array_like()
    dose_esapi = plan.Dose
    beam_dose_arrays = [beam.Dose.np_array_like() for beam in plan.Beams]

    structures = plan.StructureSet.StructuresLot()
    masks = {s.Id: plan.Dose.np_structure_mask(s) for s in structures}

    restored_ct = restore_info_image(ct_np, ct_esapi, is_ct=True)
    restored_dose = restore_info_image(dose_np, dose_esapi)

    isotropic_ct = resample_by_spacing(restored_ct, [1.0, 1.0, 1.0], interpolation=sitk.sitkBSpline)
    dose_at_ct = resample_to_target(restored_dose, isotropic_ct, interpolation=sitk.sitkLinear)

    isotropic_ct_np = sitk.GetArrayFromImage(isotropic_ct)
    isotropic_dose_np = sitk.GetArrayFromImage(dose_at_ct)
    ct_bev = image_to_bev(isotropic_ct_np)
    dose_bev = image_to_bev(isotropic_dose_np)

    processed_masks = {}
    for structure in structures:
        mask_itk = sitk.GetImageFromArray(masks[structure.Id])
        mask_itk.CopyInformation(restored_dose)
        mask_at_ct = resample_to_target(mask_itk, isotropic_ct, dtype=sitk.sitkUInt8, interpolation=sitk.sitkNearestNeighbor)
        processed_masks[structure.Id] = image_to_bev(sitk.GetArrayFromImage(mask_at_ct))

    beam0 = plan.BeamsLot(0)
    iso = beam0.get_IsocenterPosition()
    img_origin = ct_esapi.Origin
    z_iso = (isotropic_ct_np.shape[2] - abs(img_origin[2])) + (-1 * iso.get_z())
    x_iso = abs(img_origin[0]) + iso.get_x()
    y_iso = abs(img_origin[1]) + iso.get_y()

    for beam_index in range(len(plan.Beams)):
        beam = plan.BeamsLot(beam_index)
        angle = 360 - (beam_index * 24)

        empty = np.zeros(ct_bev.shape, dtype=np.int16)
        image = sitk.GetImageFromArray(empty)
        image.SetOrigin((0.0, 0.0, 0.0))
        image.SetSpacing((1.0, 1.0, 1.0))
        image.SetDirection((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
        size = image.GetSize()
        spacing = image.GetSpacing()
        origin = image.GetOrigin()
        center = [
            origin[0] + 0.5 * (size[0] - 1) * spacing[0],
            origin[1] + 0.5 * (size[1] - 1) * spacing[1],
            origin[2] + 0.5 * (size[2] - 1) * spacing[2],
        ]
        transform = sitk.Euler3DTransform()
        transform.SetCenter(center)
        transform.SetRotation(0, 0, math.radians(angle))
        rotated_iso = transform.TransformPoint((x_iso, y_iso, z_iso))
        x_coordinate = int(round(rotated_iso[0]))
        axis_slice = int(round(rotated_iso[1]))
        y_coordinate = int(round(rotated_iso[2]))

        restored_dd = restore_info_image(beam_dose_arrays[beam_index], dose_esapi)
        dd_at_ct = resample_to_target(restored_dd, isotropic_ct, interpolation=sitk.sitkLinear)
        dd_bev = image_to_bev(sitk.GetArrayFromImage(dd_at_ct))

        dd_bev = crop_or_pad_superior_inferior(dd_bev, y_coordinate, 150, 0)
        dd_bev_img = sitk.GetImageFromArray(dd_bev)
        dd_bev_img.SetSpacing((1.0, 1.0, 1.0))
        dd_bev = sitk.GetArrayFromImage(resample_by_spacing(dd_bev_img, [2.5, 2.5, 2.5], interpolation=sitk.sitkLinear))
        save_numpy(f"dd_raw{beam_index}.npy", dd_bev, output_dir, TEMP_EXPORT_DIR)

        fluence = beam.GetOptimalFluence()
        fm = np.array(fluence.GetPixels())
        fm = sitk.GetImageFromArray(fm)
        fm.SetSpacing((2.5, 2.5))
        fm = resample_by_spacing(fm, [1.0, 1.0], interpolation=sitk.sitkNearestNeighbor)
        fm = sitk.GetArrayFromImage(fm)

        rotated_ct = sitk.GetArrayFromImage(
            rotate_image_sitk(sitk.GetImageFromArray(ct_bev), angle, value=-1000, interpolation=sitk.sitkLinear)
        )
        rotated_dd = sitk.GetArrayFromImage(
            rotate_image_sitk(sitk.GetImageFromArray(image_to_bev(sitk.GetArrayFromImage(dd_at_ct))), angle, value=0, interpolation=sitk.sitkLinear)
        )

        unique_jaws = set()
        for cp in range(beam.ControlPoints.Count):
            jaw = beam.ControlPoints[cp].JawPositions
            unique_jaws.add((min(jaw.X1, jaw.X2), max(jaw.X1, jaw.X2), min(jaw.Y1, jaw.Y2), max(jaw.Y1, jaw.Y2)))

        x1 = max(unique_jaws, key=lambda item: abs(item[0]))[0]
        x2 = max(unique_jaws, key=lambda item: abs(item[1]))[1]
        y1 = max(unique_jaws, key=lambda item: abs(item[2]))[2]
        y2 = max(unique_jaws, key=lambda item: abs(item[3]))[3]

        dd_max = np.max(rotated_dd, axis=2)
        desired_height, desired_width = dd_max.shape
        top_pad = round((z_iso - fluence.YOrigin) / 1)
        right_pad = round((desired_width - (x_coordinate + fluence.XOrigin + int(fluence.XSizeMM))) / 1)
        bottom_pad = desired_height - fm.shape[0] - top_pad
        left_pad = desired_width - fm.shape[1] - right_pad
        if top_pad < 0:
            fm = fm[abs(top_pad) :, :]
            top_pad = 0
        fm = np.pad(fm, ((top_pad, bottom_pad), (left_pad, right_pad)), mode="constant", constant_values=0)

        rotated_dd = crop_or_pad_superior_inferior(rotated_dd, y_coordinate, 150, 0)
        rotated_ct = crop_or_pad_superior_inferior(rotated_ct, y_coordinate, 150, -1000)
        fm = crop_or_pad_superior_inferior(fm[:, :, np.newaxis], y_coordinate, 150, 0)[:, :, 0]

        ydim, xdim, zdim = rotated_dd.shape
        iso_center_x = x_coordinate
        iso_center_y = (ydim - 1) / 2.0

        original_dd = sitk.GetImageFromArray(np.transpose(rotated_dd, (2, 0, 1)))
        original_ct = sitk.GetImageFromArray(np.transpose(rotated_ct, (2, 0, 1)))
        original_dd.SetSpacing([1.0, 1.0, 1.0])
        original_ct.SetSpacing([1.0, 1.0, 1.0])

        displacement_field = np.zeros((zdim, ydim, xdim, 3), dtype=np.float64)
        for z in range(zdim):
            yy, xx = np.meshgrid(np.arange(ydim, dtype=np.float64), np.arange(xdim, dtype=np.float64), indexing="ij")
            distance = 1000 - (axis_slice - z)
            y2_cone = distance * (y2 / 1000)
            y1_cone = distance * ((y1 * -1) / 1000)
            x2_cone = distance * (x2 / 1000)
            x1_cone = distance * ((x1 * -1) / 1000)
            scale_y = revert_scaling_factor(((-1 * y1) + y2) / (y1_cone + y2_cone))
            scale_x = revert_scaling_factor(((-1 * x1) + x2) / (x1_cone + x2_cone))
            displacement_field[z, :, :, 0] = (xx - iso_center_x) * (scale_x - 1.0)
            displacement_field[z, :, :, 1] = (yy - iso_center_y) * (scale_y - 1.0)

        disp_image = sitk.GetImageFromArray(displacement_field, isVector=True)
        disp_image.CopyInformation(original_dd)
        transform = sitk.DisplacementFieldTransform(disp_image)

        new_spacing = [2.5, 2.5, 2.5]
        new_size = [int(math.ceil((original_dd.GetSize()[i] * original_dd.GetSpacing()[i]) / new_spacing[i])) for i in range(3)]

        transformed_dd = sitk.Resample(
            original_dd,
            new_size,
            transform=transform,
            interpolator=sitk.sitkLinear,
            outputOrigin=list(original_dd.GetOrigin()),
            outputSpacing=new_spacing,
            outputDirection=list(original_dd.GetDirection()),
            defaultPixelValue=0.0,
            outputPixelType=original_dd.GetPixelIDValue(),
        )
        transformed_ct = sitk.Resample(
            original_ct,
            new_size,
            transform=transform,
            interpolator=sitk.sitkBSpline,
            outputOrigin=list(original_ct.GetOrigin()),
            outputSpacing=new_spacing,
            outputDirection=list(original_ct.GetDirection()),
            defaultPixelValue=-1000.0,
            outputPixelType=original_ct.GetPixelIDValue(),
        )

        transformed_dd = np.transpose(sitk.GetArrayFromImage(transformed_dd), (1, 2, 0))
        transformed_ct = np.transpose(sitk.GetArrayFromImage(transformed_ct), (1, 2, 0))
        fm_img = sitk.GetImageFromArray(fm)
        fm_img.SetSpacing((1.0, 1.0))
        fm = sitk.GetArrayFromImage(resample_by_spacing(fm_img, [2.5, 2.5], interpolation=sitk.sitkNearestNeighbor))

        save_numpy(f"dd{beam_index}.npy", transformed_dd, output_dir, TEMP_EXPORT_DIR)
        save_numpy(f"ct{beam_index}.npy", transformed_ct, output_dir, TEMP_EXPORT_DIR)
        save_numpy(f"fm{beam_index}.npy", fm, output_dir, TEMP_EXPORT_DIR)

    ct_bev = crop_or_pad_superior_inferior(ct_bev, y_coordinate, 150, -1000)
    dose_bev = crop_or_pad_superior_inferior(dose_bev, y_coordinate, 150, 0)
    for key in list(processed_masks.keys()):
        processed_masks[key] = crop_or_pad_superior_inferior(processed_masks[key], y_coordinate, 150, 0)

    ct_bev_img = sitk.GetImageFromArray(ct_bev)
    ct_bev_img.SetSpacing((1.0, 1.0, 1.0))
    dose_bev_img = sitk.GetImageFromArray(dose_bev)
    dose_bev_img.SetSpacing((1.0, 1.0, 1.0))
    ct_bev = sitk.GetArrayFromImage(resample_by_spacing(ct_bev_img, [2.5, 2.5, 2.5], interpolation=sitk.sitkBSpline))
    dose_bev = sitk.GetArrayFromImage(resample_by_spacing(dose_bev_img, [2.5, 2.5, 2.5], interpolation=sitk.sitkLinear))

    for structure_id in list(processed_masks.keys()):
        mask_img = sitk.GetImageFromArray(processed_masks[structure_id])
        mask_img.SetSpacing((1.0, 1.0, 1.0))
        processed_masks[structure_id] = sitk.GetArrayFromImage(
            resample_by_spacing(mask_img, [2.5, 2.5, 2.5], interpolation=sitk.sitkNearestNeighbor)
        )

    target_id = plan.TargetVolumeID
    oars_id = sorted({objective.get_StructureId() for objective in plan.OptimizationSetup.Objectives})

    save_numpy("full_ct.npy", ct_bev, output_dir, TEMP_EXPORT_DIR)
    save_numpy("full_dose.npy", dose_bev, output_dir, TEMP_EXPORT_DIR)
    save_numpy("masks.npy", processed_masks, output_dir, TEMP_EXPORT_DIR)
    save_numpy("target_id.npy", target_id, output_dir, TEMP_EXPORT_DIR)
    save_numpy("oars_id.npy", oars_id, output_dir, TEMP_EXPORT_DIR)

    print(f"Exported case: {patient_id} | {plan_id}")


def main() -> None:
    df = pd.read_csv(CSV_PATH, skiprows=1, header=None)
    ready_df = df.loc[df.iloc[:, 8] == READY_FLAG].reset_index(drop=True)

    end_index = min(END_INDEX, len(ready_df))
    for idx in range(START_INDEX, end_index):
        if idx in SKIP_ROW_INDICES:
            continue
        export_case(ready_df.iloc[idx])


if __name__ == "__main__":
    main()
