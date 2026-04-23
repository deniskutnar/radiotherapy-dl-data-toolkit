import math
import os
import shutil
from typing import Any

import numpy as np
import SimpleITK as sitk


def restore_info_image(image: np.ndarray, esapi_image: Any, is_ct: bool = False) -> sitk.Image:
    """Restore geometry metadata from an ESAPI image-like object.

    ESAPI/PyESAPI array exports often lose spacing/origin/direction information.
    This helper recreates a SimpleITK image with the original geometry.
    """
    if is_ct:
        current_min = image.min()
        if current_min != -1000:
            image = image - (current_min + 1000)

    image_sitk = sitk.GetImageFromArray(image)
    image_sitk.SetOrigin((esapi_image.Origin[0], esapi_image.Origin[1], esapi_image.Origin[2]))
    image_sitk.SetSpacing((esapi_image.ZRes, esapi_image.YRes, esapi_image.XRes))
    image_sitk.SetDirection((
        esapi_image.ZDirection[0], esapi_image.ZDirection[1], esapi_image.ZDirection[2],
        esapi_image.YDirection[0], esapi_image.YDirection[1], esapi_image.YDirection[2],
        esapi_image.XDirection[0], esapi_image.XDirection[1], esapi_image.XDirection[2],
    ))
    return image_sitk


def resample_to_target(
    source_img: sitk.Image,
    target_img: sitk.Image,
    dtype: int = sitk.sitkFloat32,
    interpolation: int = sitk.sitkLinear,
) -> sitk.Image:
    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(target_img)
    resampler.SetSize(target_img.GetSize())
    resampler.SetOutputOrigin(target_img.GetOrigin())
    resampler.SetOutputDirection(target_img.GetDirection())
    resampler.SetOutputSpacing(target_img.GetSpacing())
    resampler.SetOutputPixelType(dtype)
    resampler.SetInterpolator(interpolation)
    resampler.SetTransform(sitk.Transform(3, sitk.sitkIdentity))
    return resampler.Execute(source_img)


def resample_by_spacing(
    image: sitk.Image,
    new_spacing,
    dtype: int = sitk.sitkFloat32,
    interpolation: int = sitk.sitkLinear,
) -> sitk.Image:
    original_spacing = image.GetSpacing()
    original_size = image.GetSize()
    new_size = [int(round(osz * osp / nsp)) for osz, osp, nsp in zip(original_size, original_spacing, new_spacing)]

    resampler = sitk.ResampleImageFilter()
    resampler.SetSize(new_size)
    resampler.SetOutputSpacing(new_spacing)
    resampler.SetOutputOrigin(image.GetOrigin())
    resampler.SetOutputDirection(image.GetDirection())
    resampler.SetTransform(sitk.Transform())
    resampler.SetOutputPixelType(dtype)
    resampler.SetInterpolator(interpolation)
    return resampler.Execute(image)


def rotate_image_sitk(
    input_image: sitk.Image,
    angle_degrees: float,
    axis: str = "z",
    value: float = 0,
    interpolation: int = sitk.sitkLinear,
) -> sitk.Image:
    size = input_image.GetSize()
    spacing = input_image.GetSpacing()
    origin = input_image.GetOrigin()
    center = [
        origin[0] + 0.5 * (size[0] - 1) * spacing[0],
        origin[1] + 0.5 * (size[1] - 1) * spacing[1],
        origin[2] + 0.5 * (size[2] - 1) * spacing[2],
    ]

    angle_radians = math.radians(angle_degrees)
    transform = sitk.Euler3DTransform()
    transform.SetCenter(center)

    if axis == "x":
        transform.SetRotation(angle_radians, 0, 0)
    elif axis == "y":
        transform.SetRotation(0, angle_radians, 0)
    else:
        transform.SetRotation(0, 0, angle_radians)

    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(input_image)
    resampler.SetTransform(transform)
    resampler.SetInterpolator(interpolation)
    resampler.SetDefaultPixelValue(value)
    return resampler.Execute(input_image)


def image_to_bev(image: np.ndarray) -> np.ndarray:
    image = np.transpose(image, axes=(0, 2, 1))
    image = np.swapaxes(image, 0, 1)
    image = np.flipud(image)
    return image


def revert_scaling_factor(scale_factor: float) -> float:
    if scale_factor == 0:
        raise ValueError("Scaling factor cannot be zero.")
    return 1 / scale_factor


def save_numpy(name: str, payload: Any, output_dir: str, temp_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, name)
    final_path = os.path.join(output_dir, name)
    np.save(temp_path, payload, allow_pickle=True)
    shutil.move(temp_path if temp_path.endswith('.npy') else temp_path + '.npy', final_path)
