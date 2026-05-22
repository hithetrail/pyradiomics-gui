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
ROOT_DIR = r"D:\0_Data\spect_latemronj\새 폴더"
OUTPUT_ROOT = r"\\10.10.16.95\shared\25 spect_mronj\late"

# -------------------------- [3] Utility Functions --------------------------
def _is_dicom(fp):
    try:
        ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True)
        _ = ds.file_meta  # ensure it parsed as DICOM
        return True
    except Exception:
        return False

def _peek_modality(fp):
    try:
        ds = pydicom.dcmread(fp, stop_before_pixels=True)
        return getattr(ds, "Modality", None)
    except Exception:
        return None

def find_dicom_dir(root_dir, expected_modality=None):
    """
    Recursively find a directory that actually contains DICOM files.
    If expected_modality is provided ('NM' for SPECT, 'CT' for CT),
    prefer a directory whose first DICOM file matches it.
    """
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"Not a directory: {root_dir}")

    candidates = []
    # 1) check root itself
    files_here = [os.path.join(root_dir, f) for f in os.listdir(root_dir)
                  if os.path.isfile(os.path.join(root_dir, f))]
    dcm_here = [f for f in files_here if _is_dicom(f)]
    if dcm_here:
        candidates.append(root_dir)

    # 2) walk subfolders
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if not filenames:
            continue
        fps = [os.path.join(dirpath, f) for f in filenames]
        dcm_files = [f for f in fps if _is_dicom(f)]
        if dcm_files:
            candidates.append(dirpath)

    if not candidates:
        raise FileNotFoundError(f"❌ No DICOM files found under: {root_dir}")

    # Prefer modality match if requested
    if expected_modality is not None:
        for c in candidates:
            # look at one dicom file in this dir
            any_dcm = None
            for f in os.listdir(c):
                fp = os.path.join(c, f)
                if os.path.isfile(fp) and _is_dicom(fp):
                    any_dcm = fp
                    break
            if any_dcm:
                mod = _peek_modality(any_dcm)
                if mod == expected_modality:
                    return c

    # Fall back to first candidate
    return candidates[0]

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
    """
    Load the largest series within the directory using SimpleITK.
    (Handles multiple series by choosing the one with the most files.)
    """
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(dicom_image_dir)
    if not series_ids:
        raise FileNotFoundError(f"No DICOM series found in: {dicom_image_dir}")

    def _files_for(sid):
        return reader.GetGDCMSeriesFileNames(dicom_image_dir, sid)

    # choose the series with the most files
    best_sid = max(series_ids, key=lambda sid: len(_files_for(sid)))
    dicom_files = _files_for(best_sid)
    reader.SetFileNames(dicom_files)
    img = reader.Execute()
    return img, dicom_files


def load_rtstruct(dicom_mask_root):
    rt_files = glob.glob(os.path.join(dicom_mask_root, "**", "*"), recursive=True)
    for rt_file in rt_files:
        if os.path.isfile(rt_file):  # 파일만 읽음
            try:
                dcm = pydicom.dcmread(rt_file, stop_before_pixels=True)
                if getattr(dcm, "Modality", "") == "RTSTRUCT":
                    print(f"✅ Found RTSTRUCT: {rt_file}")
                    return dcm
            except Exception:
                continue
    raise FileNotFoundError("❌ No valid RTSTRUCT found recursively in " + dicom_mask_root)


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

def compute_radiomics_features(image, mask, modality="SPECT", force2D=False):
    if modality == "CT":
        params = {
            'binCount': 25,
            'label': 1,
            'interpolator': sitk.sitkBSpline,
            'normalize': True,
            'resampledPixelSpacing': [1, 1, 1],
            'removeOutliers': 4,
            'correctMask': True,
            'additionalInfo': True,
            'HUrange': [-1000, 3000]
        }
    else:  # SPECT
        params = {
            'binCount': 20,
            'label': 1,
            'interpolator': sitk.sitkBSpline,
            'normalize': True,
            'resampledPixelSpacing': [1, 1, 1],
            'removeOutliers': 4,
            'correctMask': True,
            'additionalInfo': True
        }

    extractor = featureextractor.RadiomicsFeatureExtractor(**params)
    extractor.settings['force2D'] = force2D
    extractor.enableImageTypes(Original={}, LoG={'sigma': [1.0, 2.0, 3.0, 4.0, 5.0]}, Wavelet={})
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
def run_radiomics_pipeline(image_dir, mask_dir, output_dir, patient_id, modality):
    image, dicom_files = load_image(image_dir)
    rtstruct = load_rtstruct(mask_dir)
    scale = compute_suv_scale(dicom_files[0]) if modality == "SPECT" else 1.0
    all_features = {}

    if modality == "SPECT":
        gaussian2 = sitk.SmoothingRecursiveGaussian(image, sigma=2)
        hybrid = sitk.UnsharpMask(sitk.SmoothingRecursiveGaussian(image, sigma=3), [1.0, 1.0, 1.0], amount=5.0)

    for i in range(len(rtstruct.ROIContourSequence)):
        roi_name = rtstruct.StructureSetROISequence[i].ROIName
        mask = create_filled_mask_from_contours(image, rtstruct, i)
        slice_index = np.median(np.where(sitk.GetArrayFromImage(mask) > 0)[0]).astype(int)
        
        # --- (추가) 마스크 정보 확인 ---
        print(f"\n[🔍 ROI: {roi_name}]")
        analyze_mask_info(mask)

        slice_index = np.median(np.where(sitk.GetArrayFromImage(mask) > 0)[0]).astype(int)
        # --- 시각화 ---
        show_and_save_images(image, mask, slice_index, patient_id, output_dir, modality, roi_name)

        # --- SUV 및 Radiomics 추출 ---
        feats = {
            'MaskVolume_cm3': compute_volume(mask)
        }

        if modality == "SPECT":
            feats.update({f"gaussian_{k}": v for k, v in compute_suv_features(gaussian2, mask, scale).items()})
            feats.update({f"hybrid_{k}": v for k, v in compute_suv_features(hybrid, mask, scale).items()})

        feats.update(compute_radiomics_features(image, mask, force2D=(mask.GetDepth() == 1)))
        all_features[roi_name] = feats

    save_to_excel(all_features, output_dir, patient_id, modality)

