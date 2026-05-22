# Auto-extracted engine from notebook.
# Patient loop removed; GUI calls run_radiomics_pipeline() directly.

# ----------------------------- [1] Imports -----------------------------
import os, glob, re
import numpy as np
import pandas as pd
import pydicom
import SimpleITK as sitk
import matplotlib.pyplot as plt
from skimage.draw import polygon
from radiomics import featureextractor

# -------------------------- [2] Global Variables --------------------------
ROOT_DIR = r"D:\0_Data\pet_lung정리"
OUTPUT_ROOT = r"\\10.10.16.95\shared\25 lung pet\lung test"

# Single-modality settings
MODALITY_NAME = "PET"      # label string
MODALITY_SUBDIR = "pt"     # folder name under each patient (e.g., <patient>\pt\DICOM\...\...)

# -------------------------- [3] Utility Functions --------------------------

# RT Structure Set SOP Class UID (표준)
RTSTRUCT_SOP_UID = "1.2.840.10008.5.1.4.1.1.481.3"

def _is_rtstruct(ds):
    # Modality 또는 SOPClassUID로 판별 (둘 다 커버)
    if getattr(ds, "Modality", "") == "RTSTRUCT":
        return True
    sop = getattr(ds, "SOPClassUID", None)
    return str(sop) == RTSTRUCT_SOP_UID

def find_rtstruct_path(rt_root):
    """
    RTSTRUCT 파일(.dcm 확장자 유무와 무관)을 재귀적으로 찾아
    '파일 경로'를 반환. (폴더 또는 파일 경로 모두 허용)
    """
    if os.path.isfile(rt_root):
        try:
            ds = pydicom.dcmread(rt_root, stop_before_pixels=True, force=True)
            if _is_rtstruct(ds):
                print(f"✅ Found RTSTRUCT file directly: {rt_root}")
                return rt_root
        except Exception:
            pass
    if not os.path.isdir(rt_root):
        raise FileNotFoundError(f"RT root not found: {rt_root}")

    # 1) 루트 바로 아래 파일 먼저 확인 (확장자 유무 상관없이)
    for name in os.listdir(rt_root):
        path = os.path.join(rt_root, name)
        if os.path.isfile(path):
            try:
                ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
                if _is_rtstruct(ds):
                    print(f"✅ Found RTSTRUCT: {path}")
                    return path
            except Exception:
                pass

    # 2) 재귀적으로 모든 하위 파일 검사
    for root, _, files in os.walk(rt_root):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                ds = pydicom.dcmread(fpath, stop_before_pixels=True, force=True)
                if _is_rtstruct(ds):
                    print(f"✅ Found RTSTRUCT: {fpath}")
                    return fpath
            except Exception:
                continue

    raise FileNotFoundError(f"❌ No valid RTSTRUCT found recursively in {rt_root}")


def find_pet_dicom_dir(p_dir):
    """
    Search recursively for a folder containing DICOM files under patient root.
    Handles both cases:
      - DICOM files directly under a folder (e.g., pt/*.dcm)
      - DICOM files in subfolders (e.g., pt/DICOM/.../*.dcm)
    Returns the directory containing the DICOM series.
    """
    # 1️⃣ 먼저, p_dir 바로 아래에 DICOM 파일이 있는 경우
    direct_dcm = glob.glob(os.path.join(p_dir, "*.dcm"))
    if direct_dcm:
        print(f"✅ Found DICOM files directly under: {p_dir}")
        return p_dir

    # 2️⃣ 그 외에는 모든 하위 폴더를 재귀 탐색
    for root, dirs, files in os.walk(p_dir):
        # root 자체에 DICOM 파일이 있는지 확인
        dcm_files_here = glob.glob(os.path.join(root, "*.dcm"))
        if dcm_files_here:
            print(f"✅ Found DICOM files in: {root}")
            return root

        # DICOM이라는 이름이 포함된 폴더가 있으면 우선적으로 탐색
        for d in dirs:
            if "DICOM" in d.upper():
                path = os.path.join(root, d)
                dcm_files = glob.glob(os.path.join(path, "**", "*.dcm"), recursive=True)
                if dcm_files:
                    print(f"✅ Found DICOM folder: {path}")
                    return path

    raise FileNotFoundError(f"[{os.path.basename(p_dir)}-PET] No DICOM files found recursively under {p_dir}")


def extract_patient_id(foldername):
    match = re.search(r'\d+_\d+', foldername)
    return match.group(0) if match else foldername

def time_to_seconds(dicom_time):
    dicom_time_str = dicom_time.split('.')[0]
    hours = int(dicom_time_str[:2])
    minutes = int(dicom_time_str[2:4])
    seconds = int(dicom_time_str[4:])
    fractional_seconds = float('0.' + dicom_time.split('.')[1]) if '.' in dicom_time else 0.0
    return hours * 3600 + minutes * 60 + seconds + fractional_seconds

def remove_outliers(data, z_thresh=3):
    mean, std = np.mean(data), np.std(data)
    return data[np.abs((data - mean) / std) < z_thresh]

def load_image(dicom_image_dir):
    reader = sitk.ImageSeriesReader()
    dicom_files = reader.GetGDCMSeriesFileNames(dicom_image_dir)
    if not dicom_files:
        raise FileNotFoundError(f"No DICOM files in: {dicom_image_dir}")
    reader.SetFileNames(dicom_files)
    return reader.Execute(), dicom_files

def load_rtstruct(dicom_mask_root):
    """
    rt_root(예: ...\\rt\\DICOM) 아래에서 RTSTRUCT 파일 하나를 찾아
    pydicom Dataset으로 반환
    """
    rt_file = find_rtstruct_path(dicom_mask_root)
    return pydicom.dcmread(rt_file, stop_before_pixels=True, force=True)


def create_filled_mask_from_contours(image, rt_structure, roi_index):
    mask_array = np.zeros(sitk.GetArrayFromImage(image).shape, dtype=np.uint8)
    roi_contour = rt_structure.ROIContourSequence[roi_index]
    contour_sequence = roi_contour.ContourSequence
    spacing = image.GetSpacing()
    origin = image.GetOrigin()
    z_max = mask_array.shape[0] - 1

    for contour in contour_sequence:
        points = np.array(contour.ContourData).reshape(-1, 3)
        z_value = points[0][2]
        slice_index = int(round((z_value - origin[2]) / spacing[2]))
        slice_index = max(0, min(z_max, slice_index))
        pixel_coords = [image.TransformPhysicalPointToIndex(tuple(p)) for p in points]
        rr, cc = polygon([p[1] for p in pixel_coords], [p[0] for p in pixel_coords], shape=mask_array.shape[1:])
        mask_array[slice_index, rr, cc] = 1

    mask_image = sitk.GetImageFromArray(mask_array)
    mask_image.CopyInformation(image)
    return mask_image

def compute_volume(mask):
    voxel_volume = np.prod(mask.GetSpacing())
    num_voxels = np.sum(sitk.GetArrayFromImage(mask) > 0)
    return voxel_volume * num_voxels / 1000.0

def compute_suv_scale(dicom_file):
    metadata = pydicom.dcmread(dicom_file)
    acquisition = time_to_seconds(metadata.SeriesTime)
    start = time_to_seconds(metadata.RadiopharmaceuticalInformationSequence[0].RadiopharmaceuticalStartTime)
    decay = acquisition - start
    bw = float(metadata.PatientWeight) * 1000
    dose = float(metadata.RadiopharmaceuticalInformationSequence[0].RadionuclideTotalDose)
    half_life = float(metadata.RadiopharmaceuticalInformationSequence[0].RadionuclideHalfLife)
    decayed_dose = dose * np.exp(-decay * np.log(2) / half_life)
    return bw / decayed_dose

def compute_suv_features(image, mask, scale):
    img_array = sitk.GetArrayFromImage(image)
    mask_array = sitk.GetArrayFromImage(mask)
    masked = img_array[mask_array > 0]
    masked = remove_outliers(masked.flatten())
    mean = masked.mean() * scale
    max_ = masked.max() * scale
    voxel_volume = np.prod(image.GetSpacing())
    peak_voxel_count = int(1000.0 / voxel_volume)
    peak = np.mean(np.sort(masked)[::-1][:peak_voxel_count]) * scale
    return {'SUVMean': mean, 'SUVMax': max_, 'SUVPeak': peak}

def get_default_radiomics_settings():
    """Default settings shown in the GUI. Values are intentionally close to the original notebook."""
    return {
        "pet_spect_binCount": 20,
        "ct_binCount": 25,
        "normalize": True,
        "resample": True,
        "resampledPixelSpacing": [1.0, 1.0, 1.0],
        "removeOutliers": 4.0,
        "correctMask": True,
        "additionalInfo": True,
        "interpolator": "BSpline",  # BSpline, Linear, NearestNeighbor
        "enable_original": True,
        "enable_log": True,
        "log_sigma": [1.0, 2.0, 3.0, 4.0, 5.0],
        "enable_wavelet": True,
        "save_preview_images": True,
    }


def _parse_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ["1", "true", "yes", "y", "on", "예", "사용"]


def _interpolator_from_name(name):
    name = str(name or "BSpline").strip().lower()
    if name in ["linear", "sitklinear"]:
        return sitk.sitkLinear
    if name in ["nearest", "nearestneighbor", "sitknearestneighbor"]:
        return sitk.sitkNearestNeighbor
    return sitk.sitkBSpline


def _clean_settings(user_settings=None):
    settings = get_default_radiomics_settings()
    if user_settings:
        settings.update(user_settings)
    try:
        settings["pet_spect_binCount"] = int(settings["pet_spect_binCount"])
        settings["ct_binCount"] = int(settings["ct_binCount"])
        settings["removeOutliers"] = float(settings["removeOutliers"])
        settings["resampledPixelSpacing"] = [float(x) for x in settings["resampledPixelSpacing"]]
        if len(settings["resampledPixelSpacing"]) != 3:
            settings["resampledPixelSpacing"] = [1.0, 1.0, 1.0]
        settings["log_sigma"] = [float(x) for x in settings["log_sigma"]]
    except Exception:
        # keep safe defaults when the GUI sends malformed values
        settings = get_default_radiomics_settings()
    for key in ["normalize", "resample", "correctMask", "additionalInfo", "enable_original", "enable_log", "enable_wavelet", "save_preview_images"]:
        settings[key] = _parse_bool(settings.get(key))
    return settings


def compute_radiomics_features(image, mask, modality="PET", force2D=False, radiomics_settings=None):
    s = _clean_settings(radiomics_settings)
    params = {
        'binCount': s["ct_binCount"] if modality.upper() == "CT" else s["pet_spect_binCount"],
        'label': 1,
        'interpolator': _interpolator_from_name(s["interpolator"]),
        'normalize': s["normalize"],
        'removeOutliers': s["removeOutliers"],
        'correctMask': s["correctMask"],
        'additionalInfo': s["additionalInfo"],
    }
    if s["resample"]:
        params['resampledPixelSpacing'] = s["resampledPixelSpacing"]
    if modality.upper() == "CT":
        params['HUrange'] = [-1000, 3000]

    extractor = featureextractor.RadiomicsFeatureExtractor(**params)
    extractor.settings['force2D'] = force2D
    image_types = {}
    if s["enable_original"]:
        image_types["Original"] = {}
    if s["enable_log"]:
        image_types["LoG"] = {'sigma': s["log_sigma"]}
    if s["enable_wavelet"]:
        image_types["Wavelet"] = {}
    if image_types:
        extractor.enableImageTypes(**image_types)
    return extractor.execute(image, mask)

def save_to_excel(all_features, output_dir, patient_id, modality):
    dfs = [pd.DataFrame(list(f.items()), columns=["Feature", roi]) for roi, f in all_features.items()]
    final_df = dfs[0]
    for df in dfs[1:]:
        final_df = final_df.merge(df, on="Feature", how="outer")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{modality}_radiomics_{patient_id}.xlsx")
    final_df.to_excel(output_path, index=False)
    print(f"✅ Saved to: {output_path}")

def show_and_save_images(image, mask, slice_index, patient_id, output_dir, modality, roi_name):
    image_array = sitk.GetArrayFromImage(image)
    mask_array = sitk.GetArrayFromImage(mask)
    image_slice = image_array[slice_index, :, :]
    mask_slice = mask_array[slice_index, :, :]

    plt.figure(figsize=(15, 5))
    plt.subplot(1, 3, 1)
    plt.imshow(image_slice, cmap='gray')
    plt.title("Original Image")
    plt.axis('off')

    plt.subplot(1, 3, 2)
    plt.imshow(mask_slice, cmap='gray')
    plt.title("Mask Only")
    plt.axis('off')

    plt.subplot(1, 3, 3)
    plt.imshow(image_slice, cmap='gray')
    plt.imshow(mask_slice, cmap='Reds', alpha=0.6)
    plt.title("Masked Image")
    plt.axis('off')

    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, f"{modality}_Masked_Image_{patient_id}_{roi_name}.png")
    plt.savefig(save_path, bbox_inches='tight')
    plt.close()

def analyze_mask_info(mask_image):
    mask_array = sitk.GetArrayFromImage(mask_image)
    spacing = mask_image.GetSpacing()
    size = mask_image.GetSize()
    origin = mask_image.GetOrigin()
    direction = mask_image.GetDirection()
    voxel_volume_mm3 = np.prod(spacing)
    num_voxels = np.sum(mask_array > 0)
    volume_cm3 = (voxel_volume_mm3 * num_voxels) / 1000.0

    print("🧠 Mask Info:")
    print(f"- Shape (Z, Y, X): {mask_array.shape}")
    print(f"- Spacing: {spacing}")
    print(f"- Size: {size}")
    print(f"- Origin: {origin}")
    print(f"- Direction: {direction}")
    print(f"- Non-zero voxels: {num_voxels}")
    print(f"- Volume (cm³): {volume_cm3:.2f}")
    print(f"- Unique values: {np.unique(mask_array)}")

# -------------------------- [4] Radiomics Pipeline --------------------------
def run_radiomics_pipeline(image_dir, mask_dir, output_dir, patient_id, modality, radiomics_settings=None, stop_event=None):
    settings = _clean_settings(radiomics_settings)
    if stop_event is not None and stop_event.is_set():
        print(f"[{patient_id}] Stop requested before loading. Skipping.")
        return
    image, dicom_files = load_image(image_dir)
    rtstruct = load_rtstruct(mask_dir)
    scale = compute_suv_scale(dicom_files[0]) if modality.upper() in ["PET", "SPECT"] else 1.0
    all_features = {}

    # PET/SPECT smoothing/“hybrid” for SUV features
    if modality.upper() in ["PET", "SPECT"]:
        gaussian2 = sitk.SmoothingRecursiveGaussian(image, sigma=2)
        hybrid = sitk.UnsharpMask(sitk.SmoothingRecursiveGaussian(image, sigma=3), [1.0, 1.0, 1.0], amount=5.0)

    for i in range(len(rtstruct.ROIContourSequence)):
        if stop_event is not None and stop_event.is_set():
            print(f"[{patient_id}] Stop requested. Partial results may have been saved for previous ROI/cases.")
            break
        roi_name = rtstruct.StructureSetROISequence[i].ROIName
        mask = create_filled_mask_from_contours(image, rtstruct, i)

        nz = np.where(sitk.GetArrayFromImage(mask) > 0)[0]
        if nz.size == 0:
            print(f"[{patient_id}] ROI '{roi_name}' mask is empty. Skipping.")
            continue
        slice_index = int(np.median(nz))

        print(f"\n[🔍 ROI: {roi_name}]")
        analyze_mask_info(mask)

        if settings.get("save_preview_images", True):
            show_and_save_images(image, mask, slice_index, patient_id, output_dir, modality, roi_name)

        feats = {'MaskVolume_cm3': compute_volume(mask)}

        if modality.upper() in ["PET", "SPECT"]:
            feats.update({f"gaussian_{k}": v for k, v in compute_suv_features(gaussian2, mask, scale).items()})
            feats.update({f"hybrid_{k}": v for k, v in compute_suv_features(hybrid, mask, scale).items()})

        feats.update(compute_radiomics_features(image, mask, modality=modality, force2D=(mask.GetDepth() == 1), radiomics_settings=settings))
        all_features[roi_name] = feats

    if all_features:
        save_to_excel(all_features, output_dir, patient_id, modality)
    else:
        print(f"[{patient_id}] No features extracted; Excel save skipped.")

