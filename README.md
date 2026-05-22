# pyradiomics-gui
GUI tool for DICOM/RTSTRUCT-based radiomics extraction using PyRadiomics, with PET/SPECT/CT metadata detection and unimodal/multimodal analysis.

# PyRadiomics GUI / 라디오믹스 시연용 GUI

This repository provides a bilingual GUI application for DICOM/RTSTRUCT-based radiomics feature extraction using **PyRadiomics**.

이 저장소는 **PyRadiomics**를 이용하여 DICOM/RTSTRUCT 기반 라디오믹스 특징을 추출하는 GUI 프로그램입니다.

Feature extraction is based on:

> van Griethuysen JJM, Fedorov A, Parmar C, et al.  
> Computational Radiomics System to Decode the Radiographic Phenotype.  
> *Cancer Research*. 2017;77(21):e104-e107.  
> doi:10.1158/0008-5472.CAN-17-0339

---

## 1. Requirements / 필요 조건

Recommended environment:

```text
Windows 10/11
Anaconda or Miniconda
Python 3.7
PyRadiomics
SimpleITK
pydicom
pandas
openpyxl
numpy
```

This GUI was tested in a conda environment named:

```text
pyradiotest
```

---

## 2. Create conda environment / Conda 환경 만들기

Open **Anaconda Prompt**.

아래 명령은 일반 CMD가 아니라 **Anaconda Prompt**에서 실행하는 것을 권장합니다.

```bat
conda create -n pyradiotest python=3.7 -y
conda activate pyradiotest
```

---

## 3. Install required packages / 필수 패키지 설치

### Option A. Install from requirements.txt

If `requirements.txt` is provided:

```bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### Option B. Minimal installation

If you only want to install the core packages:

```bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install pyradiomics SimpleITK pydicom pandas openpyxl numpy
```

---

## 4. Check installation / 설치 확인

Run the following commands in the activated environment.

```bat
python -c "import radiomics; print('PyRadiomics version:', radiomics.__version__)"
```

```bat
python -c "from radiomics import featureextractor; extractor = featureextractor.RadiomicsFeatureExtractor(); print('PyRadiomics OK')"
```

```bat
python -c "import SimpleITK as sitk; print('SimpleITK OK:', sitk.Version())"
```

If the following messages appear, the environment is ready.

```text
PyRadiomics OK
SimpleITK OK
```

---

## 5. Run the GUI / GUI 실행 방법

Activate the conda environment first.

```bat
conda activate pyradiotest
```

Move to the repository folder.

```bat
cd /d path\to\pyradiomics-gui
```

Run the GUI.

```bat
python radiomics_demo_gui.py
```

Alternatively, if a launcher file is provided:

```bat
launch_gui_pyradiotest.bat
```

If the launcher fails with the message:

```text
'conda' is not recognized
```

open **Anaconda Prompt**, then run:

```bat
conda activate pyradiotest
cd /d path\to\pyradiomics-gui
python radiomics_demo_gui.py
```

---

## 6. Basic workflow / 기본 사용 순서

1. Click **Check Environment / 환경 점검**
2. Select the DICOM root folder
3. Select the output folder
4. Click **Scan DICOM Metadata / DICOM metadata 스캔**
5. Review detected PET / SPECT / CT / RTSTRUCT information
6. Open **Radiomics Settings / 라디오믹스 설정**
7. Run **Unimodal** or **Multimodal** extraction
8. Check the output folder

---

## 7. Unimodal and multimodal analysis / 단일 및 다중 모달 분석

The GUI automatically reads DICOM metadata and detects available imaging modalities.

GUI는 DICOM metadata를 읽어 사용 가능한 modality를 자동으로 판별합니다.

Supported modalities:

```text
PET
SPECT
CT
```

Unimodal analysis is available when at least one imaging modality and RTSTRUCT are detected.

```text
PET only    → PET unimodal
SPECT only  → SPECT unimodal
CT only     → CT unimodal
```

Multimodal analysis is available when two or more imaging modalities are detected.

```text
PET + CT      → PET/CT multimodal
SPECT + CT    → SPECT/CT multimodal
PET + SPECT   → PET/SPECT multimodal
PET + SPECT + CT → multiple pairwise combinations
```

---

## 8. Output files / 결과 파일

Output folders may include:

```text
unimodal/pet/
unimodal/spect/
unimodal/ct/

multimodal/pet/
multimodal/spect/
multimodal/ct/

multimodal_combined/
_gui_logs/
```

Typical output files:

```text
PET_radiomics_<PatientID>.xlsx
SPECT_radiomics_<PatientID>.xlsx
CT_radiomics_<PatientID>.xlsx
combined_PET_CT_wide_by_ROI.xlsx
combined_SPECT_CT_wide_by_ROI.xlsx
radiomics_settings_used_YYYYMMDD_HHMMSS.json
```

---

## 9. Notes on DICOM metadata detection / DICOM metadata 판별 방식

The GUI uses DICOM metadata such as:

```text
Modality
PatientID
StudyInstanceUID
SeriesInstanceUID
FrameOfReferenceUID
SOPClassUID
SeriesDescription
ProtocolName
RadiopharmaceuticalInformationSequence
ReferencedFrameOfReferenceSequence
RTReferencedSeriesSequence
```

RTSTRUCT matching is performed based on:

```text
Referenced SeriesInstanceUID
Referenced FrameOfReferenceUID
StudyInstanceUID
PatientID
```

Folder names are used only as auxiliary information.

폴더명은 보조 정보로만 사용하며, 기본적으로 DICOM header metadata를 기반으로 modality와 RTSTRUCT를 판별합니다.

---

## 10. Important notice / 주의 사항

This software is intended for research demonstration purposes only.

본 프로그램은 연구 및 시연 목적으로만 사용됩니다.

It is not intended for clinical diagnosis, treatment planning, or treatment decision-making.

임상 진단, 치료 계획, 치료 결정 목적으로 사용해서는 안 됩니다.

Do not upload patient-identifiable DICOM data to a public GitHub repository.

환자 식별 가능 DICOM 데이터는 public GitHub 저장소에 업로드하지 마십시오.

---

## 11. Recommended files to include in GitHub / GitHub에 포함 권장 파일

Recommended:

```text
radiomics_demo_gui.py
README.md
requirements.txt
environment.yml
launch_gui_pyradiotest.bat
run_gui_after_conda_activate.bat
.gitignore
```

Do not include:

```text
DICOM files
RTSTRUCT files
patient data
radiomics output Excel/CSV files
GUI logs
local path configuration files
```
