# -*- coding: utf-8 -*-
"""DICOM metadata scanner for universal unimodal/multimodal radiomics GUI.

Main rule requested by user:
- If any one of PET/SPECT/CT exists with RTSTRUCT -> unimodal is possible.
- If two or more among PET/SPECT/CT exist with RTSTRUCT -> multimodal is possible.
"""
from __future__ import annotations

import os
import csv
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

try:
    import pydicom
except Exception:
    pydicom = None

RTSTRUCT_SOP_CLASS_UIDS = {"1.2.840.10008.5.1.4.1.1.481.3"}
IMAGE_MODALITIES = {"PT", "PET", "NM", "CT"}

@dataclass
class ImageSeries:
    patient_id: str = "UNKNOWN"
    patient_name: str = ""
    study_uid: str = ""
    study_date: str = ""
    series_uid: str = ""
    frame_uid: str = ""
    modality: str = ""
    normalized_modality: str = ""
    series_description: str = ""
    protocol_name: str = ""
    body_part: str = ""
    radiopharmaceutical: str = ""
    series_number: str = ""
    common_dir: str = ""
    sample_file: str = ""
    n_files: int = 0

@dataclass
class RTStructInfo:
    patient_id: str = "UNKNOWN"
    patient_name: str = ""
    study_uid: str = ""
    study_date: str = ""
    series_uid: str = ""
    frame_uid: str = ""
    sop_uid: str = ""
    path: str = ""
    parent_dir: str = ""
    referenced_series_uids: List[str] = None
    referenced_frame_uids: List[str] = None
    roi_names: List[str] = None

@dataclass
class PatientCase:
    patient_id: str
    study_date: str = ""
    pet_dir: str = ""
    spect_dir: str = ""
    ct_dir: str = ""
    rt_path: str = ""
    rt_dir: str = ""
    pet_series_uid: str = ""
    spect_series_uid: str = ""
    ct_series_uid: str = ""
    available_modalities: str = ""
    unimodal_plan: str = "Missing"
    multimodal_plan: str = "Missing"
    status_unimodal: str = "Missing"
    status_multimodal: str = "Missing"
    match_note: str = ""


def _safe_str(x: Any) -> str:
    try:
        return str(x) if x is not None else ""
    except Exception:
        return ""


def normalize_modality(modality: str, series_description: str = "", protocol_name: str = "", body_part: str = "", radiopharmaceutical: str = "") -> str:
    """Normalize DICOM Modality to GUI labels.

    Priority is intentionally conservative:
    - DICOM Modality == NM is always treated as SPECT/NM.
    - DICOM Modality == CT is CT.
    - DICOM Modality == PT is normally PET, but can be treated as SPECT/NM if
      the textual metadata strongly indicates a nuclear medicine bone/SPECT scan.
      This handles vendor/export cases where SPECT-like data are mislabeled or
      exported under PT.
    """
    m = (modality or "").upper().strip()
    text = " ".join([series_description or "", protocol_name or "", body_part or "", radiopharmaceutical or ""]).lower()

    # Hard DICOM rules first
    if m == "NM":
        return "SPECT"
    if m == "CT":
        return "CT"

    # PT usually means PET, but some SPECT/bone scan exports may carry PT.
    # Treat as SPECT only when there is strong SPECT/NM evidence in metadata.
    import re
    spect_patterns = [
        r"\bspect\b", r"bone\s*scan", r"bonescan", r"\bbone\b",
        r"\bbs\b", r"\bnm\b", r"whole\s*body", r"\bwb\b",
        r"\bplanar\b", r"gamma", r"scintigraphy", r"scinti", r"\bmibi\b",
        r"\bmdp\b", r"\bhdp\b", r"\bhmdp\b", r"tc[- ]?99", r"99m\s*tc",
        r"99mtc", r"technetium"
    ]
    pet_patterns = [r"\bpet\b", r"\bfdg\b", r"f-18", r"18f", r"florbetaben", r"florbetapir", r"\bpsma\b"]

    if m in ("PT", "PET"):
        has_spect_evidence = any(re.search(pat, text) for pat in spect_patterns)
        has_pet_evidence = any(re.search(pat, text) for pat in pet_patterns)
        if has_spect_evidence and not has_pet_evidence:
            return "SPECT"
        return "PET"
    return m


def _extract_radiopharmaceutical(ds) -> str:
    vals = []
    try:
        for item in getattr(ds, "RadiopharmaceuticalInformationSequence", []) or []:
            for key in ["Radiopharmaceutical", "RadionuclideCodeSequence"]:
                v = getattr(item, key, None)
                if v is None:
                    continue
                if key == "RadionuclideCodeSequence":
                    try:
                        for code in v:
                            vals.append(_safe_str(getattr(code, "CodeMeaning", "")))
                            vals.append(_safe_str(getattr(code, "CodeValue", "")))
                    except Exception:
                        vals.append(_safe_str(v))
                else:
                    vals.append(_safe_str(v))
    except Exception:
        pass
    return " ".join([v for v in vals if v])


def _read_dicom_meta(path: str):
    if pydicom is None:
        raise ImportError("pydicom is not installed. Run: python -m pip install pydicom")
    try:
        return pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception:
        return None


def _is_probably_dicom(path: str) -> bool:
    name = os.path.basename(path).lower()
    if name.endswith((".xlsx", ".xls", ".csv", ".txt", ".json", ".png", ".jpg", ".jpeg", ".py", ".ipynb", ".zip", ".log")):
        return False
    return True


def _extract_rt_references(ds) -> Tuple[List[str], List[str], List[str]]:
    series_uids, frame_uids, roi_names = [], [], []
    try:
        for roi in getattr(ds, "StructureSetROISequence", []) or []:
            name = _safe_str(getattr(roi, "ROIName", ""))
            if name:
                roi_names.append(name)
    except Exception:
        pass
    try:
        for fr in getattr(ds, "ReferencedFrameOfReferenceSequence", []) or []:
            fuid = _safe_str(getattr(fr, "FrameOfReferenceUID", ""))
            if fuid:
                frame_uids.append(fuid)
            for study in getattr(fr, "RTReferencedStudySequence", []) or []:
                for series in getattr(study, "RTReferencedSeriesSequence", []) or []:
                    suid = _safe_str(getattr(series, "SeriesInstanceUID", ""))
                    if suid:
                        series_uids.append(suid)
    except Exception:
        pass
    try:
        for series in getattr(ds, "ReferencedSeriesSequence", []) or []:
            suid = _safe_str(getattr(series, "SeriesInstanceUID", ""))
            if suid:
                series_uids.append(suid)
    except Exception:
        pass
    return sorted(set(series_uids)), sorted(set(frame_uids)), sorted(set(roi_names))


def scan_dicom_tree(root: str, progress_callback=None, max_files: Optional[int] = None):
    candidates = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            if _is_probably_dicom(fp):
                candidates.append(fp)
                if max_files and len(candidates) >= max_files:
                    break
        if max_files and len(candidates) >= max_files:
            break

    series_files: Dict[str, List[str]] = defaultdict(list)
    series_meta: Dict[str, Any] = {}
    rt_list: List[RTStructInfo] = []
    skipped = 0

    for i, fp in enumerate(candidates, 1):
        if progress_callback and (i == 1 or i % 200 == 0 or i == len(candidates)):
            progress_callback(f"Reading DICOM metadata {i}/{len(candidates)}")
        ds = _read_dicom_meta(fp)
        if ds is None:
            skipped += 1
            continue
        modality = _safe_str(getattr(ds, "Modality", "")).upper()
        sop_class = _safe_str(getattr(ds, "SOPClassUID", ""))
        is_rt = modality == "RTSTRUCT" or sop_class in RTSTRUCT_SOP_CLASS_UIDS
        if is_rt:
            ref_series, ref_frames, roi_names = _extract_rt_references(ds)
            rt_list.append(RTStructInfo(
                patient_id=_safe_str(getattr(ds, "PatientID", "UNKNOWN")) or "UNKNOWN",
                patient_name=_safe_str(getattr(ds, "PatientName", "")),
                study_uid=_safe_str(getattr(ds, "StudyInstanceUID", "")),
                study_date=_safe_str(getattr(ds, "StudyDate", "")),
                series_uid=_safe_str(getattr(ds, "SeriesInstanceUID", "")),
                frame_uid=_safe_str(getattr(ds, "FrameOfReferenceUID", "")),
                sop_uid=_safe_str(getattr(ds, "SOPInstanceUID", "")),
                path=fp,
                parent_dir=os.path.dirname(fp),
                referenced_series_uids=ref_series,
                referenced_frame_uids=ref_frames,
                roi_names=roi_names,
            ))
        elif modality in IMAGE_MODALITIES:
            suid = _safe_str(getattr(ds, "SeriesInstanceUID", ""))
            if not suid:
                skipped += 1
                continue
            series_files[suid].append(fp)
            if suid not in series_meta:
                series_meta[suid] = ds
        else:
            skipped += 1

    series_list: List[ImageSeries] = []
    for suid, files in series_files.items():
        ds = series_meta[suid]
        dirs = [os.path.dirname(f) for f in files]
        try:
            common_dir = os.path.commonpath(dirs)
        except Exception:
            common_dir = dirs[0] if dirs else ""
        modality = _safe_str(getattr(ds, "Modality", "")).upper()
        series_description = _safe_str(getattr(ds, "SeriesDescription", ""))
        protocol_name = _safe_str(getattr(ds, "ProtocolName", ""))
        body_part = _safe_str(getattr(ds, "BodyPartExamined", ""))
        radiopharm = _extract_radiopharmaceutical(ds)
        series_list.append(ImageSeries(
            patient_id=_safe_str(getattr(ds, "PatientID", "UNKNOWN")) or "UNKNOWN",
            patient_name=_safe_str(getattr(ds, "PatientName", "")),
            study_uid=_safe_str(getattr(ds, "StudyInstanceUID", "")),
            study_date=_safe_str(getattr(ds, "StudyDate", "")),
            series_uid=suid,
            frame_uid=_safe_str(getattr(ds, "FrameOfReferenceUID", "")),
            modality=modality,
            normalized_modality=normalize_modality(modality, series_description, protocol_name, body_part, radiopharm),
            series_description=series_description,
            protocol_name=protocol_name,
            body_part=body_part,
            radiopharmaceutical=radiopharm,
            series_number=_safe_str(getattr(ds, "SeriesNumber", "")),
            common_dir=common_dir,
            sample_file=files[0] if files else "",
            n_files=len(files),
        ))
    return series_list, rt_list, skipped


def _score_series(s: ImageSeries, desired: str) -> int:
    text = " ".join([s.series_description or "", s.protocol_name or "", s.body_part or "", s.radiopharmaceutical or ""]).lower()
    score = int(s.n_files or 0)
    if s.normalized_modality == desired:
        score += 100000
    if desired == "PET" and any(k in text for k in ["pet", "fdg", "f-18", "18f", "psma"]):
        score += 2000
    if desired == "SPECT" and any(k in text for k in ["spect", "bone", "bs", "nm", "scan", "mdp", "hdp", "tc-99", "99mtc"]):
        score += 2000
    if desired == "CT" and "ct" in text:
        score += 2000
    return score


def _best_series(series: List[ImageSeries], desired: str) -> Optional[ImageSeries]:
    candidates = [s for s in series if s.normalized_modality == desired]
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: _score_series(x, desired), reverse=True)[0]


def _match_rt_for_series(rt_list: List[RTStructInfo], target: Optional[ImageSeries]) -> Tuple[Optional[RTStructInfo], str]:
    if target is None or not rt_list:
        return None, "no target series or no RTSTRUCT"
    exact = [r for r in rt_list if target.series_uid in (r.referenced_series_uids or [])]
    if exact:
        return exact[0], f"RT references {target.normalized_modality} SeriesInstanceUID"
    if target.frame_uid:
        same_frame = [r for r in rt_list if target.frame_uid in (r.referenced_frame_uids or []) or target.frame_uid == r.frame_uid]
        if same_frame:
            return same_frame[0], f"RT shares/references {target.normalized_modality} FrameOfReferenceUID"
    same_study = [r for r in rt_list if r.study_uid and target.study_uid and r.study_uid == target.study_uid]
    if same_study:
        return same_study[0], f"RT has same StudyInstanceUID as {target.normalized_modality}; verify contour alignment"
    return rt_list[0], "fallback: first RTSTRUCT for patient; verify carefully"


def _choose_best_rt(rt_list: List[RTStructInfo], targets: List[ImageSeries]) -> Tuple[Optional[RTStructInfo], str]:
    if not rt_list:
        return None, "no RTSTRUCT"
    # Prefer CT, then PET, then SPECT because RT contours are often drawn on CT/PET-CT CT.
    preferred = []
    for desired in ["CT", "PET", "SPECT"]:
        preferred.extend([t for t in targets if t and t.normalized_modality == desired])
    for t in preferred:
        rt, note = _match_rt_for_series(rt_list, t)
        if rt and not note.startswith("fallback") and not note.startswith("RT has same StudyInstanceUID"):
            return rt, note
    for t in preferred:
        rt, note = _match_rt_for_series(rt_list, t)
        if rt:
            return rt, note
    return rt_list[0], "fallback: first RTSTRUCT for patient; verify carefully"


def build_patient_cases(series_list: List[ImageSeries], rt_list: List[RTStructInfo]) -> List[PatientCase]:
    by_patient_series: Dict[str, List[ImageSeries]] = defaultdict(list)
    by_patient_rt: Dict[str, List[RTStructInfo]] = defaultdict(list)
    for s in series_list:
        by_patient_series[s.patient_id].append(s)
    for r in rt_list:
        by_patient_rt[r.patient_id].append(r)

    patients = sorted(set(by_patient_series) | set(by_patient_rt))
    cases: List[PatientCase] = []
    for pid in patients:
        ss = by_patient_series.get(pid, [])
        rr = by_patient_rt.get(pid, [])
        pet = _best_series(ss, "PET")
        spect = _best_series(ss, "SPECT")
        ct = _best_series(ss, "CT")
        targets = [x for x in [pet, spect, ct] if x]
        rt, note = _choose_best_rt(rr, targets)
        mods = []
        if pet: mods.append("PET")
        if spect: mods.append("SPECT")
        if ct: mods.append("CT")
        study_dates = [x.study_date for x in ss if x.study_date] + [x.study_date for x in rr if x.study_date]
        study_date = sorted(set(study_dates))[0] if study_dates else ""
        case = PatientCase(patient_id=pid, study_date=study_date)
        case.pet_dir = pet.common_dir if pet else ""
        case.spect_dir = spect.common_dir if spect else ""
        case.ct_dir = ct.common_dir if ct else ""
        case.pet_series_uid = pet.series_uid if pet else ""
        case.spect_series_uid = spect.series_uid if spect else ""
        case.ct_series_uid = ct.series_uid if ct else ""
        case.rt_path = rt.path if rt else ""
        case.rt_dir = rt.path if rt else ""  # pass exact RTSTRUCT file to engine
        case.available_modalities = ", ".join(mods) if mods else "None"
        if mods and rt:
            case.status_unimodal = "Ready"
            case.unimodal_plan = ", ".join([f"{m} alone" for m in mods])
        else:
            case.status_unimodal = "Missing image or RTSTRUCT"
            case.unimodal_plan = case.status_unimodal
        if len(mods) >= 2 and rt:
            case.status_multimodal = "Ready"
            if len(mods) == 2:
                case.multimodal_plan = " + ".join(mods)
            else:
                case.multimodal_plan = " + ".join(mods) + " / pairwise combinations"
        else:
            case.status_multimodal = "Need at least 2 modalities + RTSTRUCT"
            case.multimodal_plan = case.status_multimodal
        case.match_note = note
        cases.append(case)
    return cases


def export_inventory_csv(path: str, cases: List[PatientCase], series_list: List[ImageSeries], rt_list: List[RTStructInfo]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    case_csv = path
    series_csv = os.path.splitext(path)[0] + "_series.csv"
    rt_csv = os.path.splitext(path)[0] + "_rtstruct.csv"

    with open(case_csv, "w", newline="", encoding="utf-8-sig") as f:
        fields = list(asdict(cases[0]).keys()) if cases else list(PatientCase("x").__dict__.keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in cases:
            w.writerow(asdict(c))
    with open(series_csv, "w", newline="", encoding="utf-8-sig") as f:
        fields = list(asdict(series_list[0]).keys()) if series_list else list(ImageSeries().__dict__.keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in series_list:
            w.writerow(asdict(s))
    with open(rt_csv, "w", newline="", encoding="utf-8-sig") as f:
        fields = list(asdict(rt_list[0]).keys()) if rt_list else list(RTStructInfo().__dict__.keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rt_list:
            d = asdict(r)
            d["referenced_series_uids"] = ";".join(d.get("referenced_series_uids") or [])
            d["referenced_frame_uids"] = ";".join(d.get("referenced_frame_uids") or [])
            d["roi_names"] = ";".join(d.get("roi_names") or [])
            w.writerow(d)
    return case_csv, series_csv, rt_csv
