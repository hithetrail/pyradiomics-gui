Radiomics Demo GUI / 라디오믹스 시연용 GUI
=========================================

이 GUI는 DICOM metadata를 직접 읽어 PET, SPECT, CT, RTSTRUCT를 자동 판별하고,
PyRadiomics 기반 radiomics feature extraction을 실행합니다.

This GUI automatically identifies PET, SPECT, CT, and RTSTRUCT from DICOM metadata,
and runs PyRadiomics-based radiomics feature extraction.

Reference / 참고문헌
-------------------
van Griethuysen JJM, Fedorov A, Parmar C, et al. Computational Radiomics System to Decode the Radiographic Phenotype. Cancer Research. 2017;77(21):e104-e107. DOI: 10.1158/0008-5472.CAN-17-0339

실행 방법 / How to run
---------------------
1) Anaconda Prompt 실행
2) 아래 명령 실행:

conda activate pyradiotest
cd /d 압축푼_폴더\radiomics_demo_gui_v4
python radiomics_demo_gui.py

또는 launch_gui_pyradiotest.bat를 실행하세요.

GUI 순서 / GUI workflow
----------------------
1. 환경 점검 / Environment check
2. DICOM 최상위 폴더와 결과 저장 폴더 선택 / Select input and output folders
3. DICOM metadata 스캔 / Scan DICOM metadata
4. Radiomics 설정 보기/수정 / Review or edit extraction settings
5. Unimodal 선택/실행 또는 Multimodal 실행 / Select Unimodal modality or run Multimodal

주요 기능 / Main features
-------------------------
- 폴더명에 의존하지 않고 DICOM metadata 기반 자동 판별
- PET/SPECT/CT 중 하나 이상 + RTSTRUCT이면 Unimodal 가능
- Unimodal 실행 시 PET, SPECT, CT 중 실행할 modality 직접 선택 가능
- PET/SPECT/CT 중 둘 이상 + RTSTRUCT이면 Multimodal 가능
- Radiomics 기본 설정을 GUI에서 확인 및 수정 가능
- 실행 중지 및 마지막 실행 재실행 지원
- 결과 Excel 자동 병합

주의 / Notes
------------
- RTSTRUCT matching note가 fallback으로 표시되는 경우, contour alignment를 확인하는 것이 좋습니다.
- 실행 중지는 현재 처리 중인 ROI 또는 환자 단위가 끝난 뒤 안전하게 반영됩니다.
