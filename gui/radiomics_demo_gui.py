# -*- coding: utf-8 -*-
"""Radiomics demo GUI - universal PET/SPECT/CT unimodal and multimodal radiomics launcher."""
from __future__ import annotations

import os
import sys
import glob
import traceback
import threading
import queue
import datetime as dt
import subprocess
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from contextlib import redirect_stdout, redirect_stderr

from dicom_metadata_scanner import scan_dicom_tree, build_patient_cases, export_inventory_csv

APP_TITLE = "Radiomics Demo GUI / 라디오믹스 시연용 GUI"
MODALITIES = ["PET", "SPECT", "CT"]


def open_folder(path):
    if not path:
        return
    os.makedirs(path, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def timestamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


class QueueWriter(object):
    def __init__(self, put_func):
        self.put_func = put_func
        self._buf = ""
    def write(self, text):
        if not text:
            return
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.put_func(line)
    def flush(self):
        if self._buf.strip():
            self.put_func(self._buf.strip())
        self._buf = ""


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1380x820")
        self.minsize(1160, 720)
        self.q = queue.Queue()
        self.series_list = []
        self.rt_list = []
        self.cases = []
        self.radiomics_settings = self._default_radiomics_settings()
        self.stop_event = threading.Event()
        self.running = False
        self.last_run = None
        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        header = ttk.Frame(self, padding=(16, 12, 16, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Radiomics Demo GUI / 라디오믹스 시연용 GUI", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="DICOM metadata 기반으로 PET / SPECT / CT / RTSTRUCT를 자동 판별합니다. / Automatically identifies PET, SPECT, CT, and RTSTRUCT from DICOM metadata.", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=(4,0))
        ttk.Label(header, text="Feature extraction uses PyRadiomics: van Griethuysen et al., Cancer Res. 2017;77:e104-e107. DOI: 10.1158/0008-5472.CAN-17-0339", font=("Segoe UI", 9), foreground="#333").grid(row=2, column=0, sticky="w", pady=(3,0))
        ttk.Label(header, text="규칙 / Rule: 1 modality + RTSTRUCT = Unimodal, 2+ modalities + RTSTRUCT = Multimodal", font=("Segoe UI", 10, "bold"), foreground="#444").grid(row=3, column=0, sticky="w", pady=(3,0))

        # Step 1
        step1 = ttk.LabelFrame(self, text="1단계 / Step 1. 실행 환경 점검 / Environment check", padding=10)
        step1.grid(row=1, column=0, sticky="ew", padx=16, pady=(8,4))
        step1.columnconfigure(1, weight=1)
        self.btn_check = ttk.Button(step1, text="① PyRadiomics / SimpleITK 확인", command=self._check_env)
        self.btn_check.grid(row=0, column=0, padx=(0,10), pady=2, sticky="w")
        ttk.Label(step1, text="PyRadiomics, SimpleITK, pydicom 설치 상태를 확인합니다. / Check PyRadiomics, SimpleITK, and pydicom.").grid(row=0, column=1, sticky="w")

        # Step 2 paths
        step2 = ttk.LabelFrame(self, text="2단계 / Step 2. 데이터 폴더와 결과 저장 위치 선택 / Select folders", padding=10)
        step2.grid(row=2, column=0, sticky="ew", padx=16, pady=4)
        step2.columnconfigure(1, weight=1)
        self.root_var = tk.StringVar()
        self.out_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop", "radiomics_demo_output"))
        ttk.Label(step2, text="DICOM 최상위 폴더 / DICOM root folder").grid(row=0, column=0, sticky="w", padx=(0,10), pady=4)
        ttk.Entry(step2, textvariable=self.root_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(step2, text="폴더 선택", command=self._browse_root).grid(row=0, column=2, padx=6)
        ttk.Label(step2, text="결과 저장 폴더 / Output folder").grid(row=1, column=0, sticky="w", padx=(0,10), pady=4)
        ttk.Entry(step2, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(step2, text="폴더 선택", command=self._browse_out).grid(row=1, column=2, padx=6)

        # Step 3 and 4 buttons
        step3 = ttk.LabelFrame(self, text="3단계 → 4단계 / Step 3 → Step 4. Metadata scan → Settings → Run", padding=10)
        step3.grid(row=3, column=0, sticky="ew", padx=16, pady=4)
        for i in range(9):
            step3.columnconfigure(i, weight=0)
        self.btn_scan = ttk.Button(step3, text="② DICOM metadata 스캔", command=self._scan_async)
        self.btn_settings = ttk.Button(step3, text="③ Radiomics 설정 보기/수정", command=self._open_settings_window)
        self.btn_export = ttk.Button(step3, text="스캔 결과 CSV 저장", command=self._export_inventory)
        self.btn_uni = ttk.Button(step3, text="④ Unimodal 선택/실행 / Select & Run", command=self._choose_unimodal_and_run)
        self.btn_multi = ttk.Button(step3, text="⑤ Multimodal 실행 / Run", command=lambda: self._run_async("multimodal"))
        self.btn_stop = ttk.Button(step3, text="■ 실행 중지", command=self._request_stop)
        self.btn_rerun = ttk.Button(step3, text="↻ 마지막 실행 다시 실행", command=self._rerun_last)
        self.btn_open = ttk.Button(step3, text="결과 폴더 열기", command=lambda: open_folder(self.out_var.get()))
        self.btn_scan.grid(row=0, column=0, padx=5, pady=4)
        self.btn_settings.grid(row=0, column=1, padx=5, pady=4)
        self.btn_export.grid(row=0, column=2, padx=5, pady=4)
        self.btn_uni.grid(row=0, column=3, padx=5, pady=4)
        self.btn_multi.grid(row=0, column=4, padx=5, pady=4)
        self.btn_stop.grid(row=0, column=5, padx=5, pady=4)
        self.btn_rerun.grid(row=0, column=6, padx=5, pady=4)
        self.btn_open.grid(row=0, column=7, padx=5, pady=4)
        self.btn_stop.configure(state="disabled")
        self.btn_rerun.configure(state="disabled")
        ttk.Label(step3, text="Unimodal은 PET/SPECT/CT 중 실행할 modality를 직접 선택할 수 있습니다. 표에서 환자를 선택하면 선택 환자만 실행합니다. / Select modality for Unimodal; select rows to run selected patients only.", foreground="#555").grid(row=1, column=0, columnspan=8, sticky="w", pady=(4,0))

        main = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main.grid(row=4, column=0, sticky="nsew", padx=16, pady=8)

        table_frame = ttk.LabelFrame(main, text="자동 판별 결과 / Metadata-based detection result", padding=8)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        cols = ("patient", "date", "available", "uniplan", "multiplan", "pet", "spect", "ct", "rt", "note")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended")
        headings = {
            "patient":"PatientID", "date":"StudyDate", "available":"Detected modalities",
            "uniplan":"Unimodal 가능", "multiplan":"Multimodal 가능",
            "pet":"PET/PT folder", "spect":"SPECT/NM folder", "ct":"CT folder", "rt":"RTSTRUCT file", "note":"RT matching note"
        }
        widths = {"patient":120,"date":90,"available":150,"uniplan":220,"multiplan":260,"pet":210,"spect":210,"ct":210,"rt":240,"note":360}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        main.add(table_frame, weight=3)

        log_frame = ttk.LabelFrame(main, text="진행 로그 / Progress log", padding=8)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=11, wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.grid(row=0, column=1, sticky="ns")
        main.add(log_frame, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken", padding=(8,4)).grid(row=5, column=0, sticky="ew")


    def _default_radiomics_settings(self):
        return {
            "pet_spect_binCount": 20,
            "ct_binCount": 25,
            "normalize": True,
            "resample": True,
            "resampledPixelSpacing": [1.0, 1.0, 1.0],
            "removeOutliers": 4.0,
            "correctMask": True,
            "additionalInfo": True,
            "interpolator": "BSpline",
            "enable_original": True,
            "enable_log": True,
            "log_sigma": [1.0, 2.0, 3.0, 4.0, 5.0],
            "enable_wavelet": True,
            "save_preview_images": True,
        }

    def _settings_summary(self):
        s = self.radiomics_settings
        return "PET/SPECT binCount={}; CT binCount={}; normalize={}; resample={}; spacing={}; imageTypes={}".format(
            s.get("pet_spect_binCount"), s.get("ct_binCount"), s.get("normalize"),
            s.get("resample"), s.get("resampledPixelSpacing"),
            ",".join([name for name, key in [("Original","enable_original"),("LoG","enable_log"),("Wavelet","enable_wavelet")] if s.get(key)])
        )

    def _parse_float_list(self, text, default):
        try:
            vals = [float(x.strip()) for x in str(text).replace(";", ",").split(",") if x.strip()]
            return vals if vals else default
        except Exception:
            return default

    def _open_settings_window(self):
        win = tk.Toplevel(self)
        win.title("Radiomics extraction settings / 라디오믹스 추출 설정")
        win.geometry("620x640")
        win.transient(self)
        win.grab_set()
        s = self.radiomics_settings.copy()
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="Radiomics extraction settings / 라디오믹스 추출 설정", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,8))
        ttk.Label(frm, text="PyRadiomics 기반 feature extraction입니다. / This GUI uses PyRadiomics-based feature extraction. Ref: van Griethuysen et al., Cancer Research 2017;77:e104-e107. DOI: 10.1158/0008-5472.CAN-17-0339", foreground="#555", wraplength=560).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0,12))

        vars_ = {}
        def add_entry(row, label, key, value):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=5)
            v = tk.StringVar(value=str(value))
            ttk.Entry(frm, textvariable=v).grid(row=row, column=1, sticky="ew", pady=5)
            vars_[key] = v
        def add_check(row, label, key, value):
            v = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(frm, text=label, variable=v).grid(row=row, column=0, columnspan=2, sticky="w", pady=5)
            vars_[key] = v

        add_entry(2, "PET/SPECT binCount", "pet_spect_binCount", s.get("pet_spect_binCount", 20))
        add_entry(3, "CT binCount", "ct_binCount", s.get("ct_binCount", 25))
        add_check(4, "Intensity normalize 사용", "normalize", s.get("normalize", True))
        add_check(5, "Resampling 사용", "resample", s.get("resample", True))
        add_entry(6, "Resampled pixel spacing (x,y,z)", "resampledPixelSpacing", ", ".join(map(str, s.get("resampledPixelSpacing", [1,1,1]))))
        add_entry(7, "Remove outliers", "removeOutliers", s.get("removeOutliers", 4.0))
        add_check(8, "Correct mask 사용", "correctMask", s.get("correctMask", True))
        add_check(9, "Additional diagnostic info 저장", "additionalInfo", s.get("additionalInfo", True))

        ttk.Label(frm, text="Interpolator").grid(row=10, column=0, sticky="w", pady=5)
        interp = tk.StringVar(value=s.get("interpolator", "BSpline"))
        ttk.Combobox(frm, textvariable=interp, values=["BSpline", "Linear", "NearestNeighbor"], state="readonly").grid(row=10, column=1, sticky="ew", pady=5)
        vars_["interpolator"] = interp

        sep = ttk.Separator(frm, orient="horizontal")
        sep.grid(row=11, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(frm, text="Image type / Filter", font=("Segoe UI", 11, "bold")).grid(row=12, column=0, columnspan=2, sticky="w")
        add_check(13, "Original feature 사용", "enable_original", s.get("enable_original", True))
        add_check(14, "LoG feature 사용", "enable_log", s.get("enable_log", True))
        add_entry(15, "LoG sigma 목록", "log_sigma", ", ".join(map(str, s.get("log_sigma", [1,2,3,4,5]))))
        add_check(16, "Wavelet feature 사용", "enable_wavelet", s.get("enable_wavelet", True))
        add_check(17, "ROI preview image 저장", "save_preview_images", s.get("save_preview_images", True))

        btns = ttk.Frame(frm)
        btns.grid(row=18, column=0, columnspan=3, sticky="ew", pady=(18,0))
        btns.columnconfigure(0, weight=1)

        def reset_defaults():
            self.radiomics_settings = self._default_radiomics_settings()
            win.destroy()
            self._log("[설정] 기본값으로 초기화했습니다: " + self._settings_summary())
        def save_settings():
            try:
                new = {}
                new["pet_spect_binCount"] = int(vars_["pet_spect_binCount"].get())
                new["ct_binCount"] = int(vars_["ct_binCount"].get())
                for k in ["normalize", "resample", "correctMask", "additionalInfo", "enable_original", "enable_log", "enable_wavelet", "save_preview_images"]:
                    new[k] = bool(vars_[k].get())
                new["resampledPixelSpacing"] = self._parse_float_list(vars_["resampledPixelSpacing"].get(), [1.0,1.0,1.0])[:3]
                if len(new["resampledPixelSpacing"]) != 3:
                    raise ValueError("resampledPixelSpacing은 숫자 3개가 필요합니다. 예: 1,1,1")
                new["removeOutliers"] = float(vars_["removeOutliers"].get())
                new["interpolator"] = vars_["interpolator"].get()
                new["log_sigma"] = self._parse_float_list(vars_["log_sigma"].get(), [1.0,2.0,3.0,4.0,5.0])
                self.radiomics_settings = new
                self._log("[설정 저장] " + self._settings_summary())
                win.destroy()
            except Exception as e:
                messagebox.showerror("설정 오류", str(e))
        ttk.Button(btns, text="기본값으로 되돌리기", command=reset_defaults).pack(side="left")
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="right", padx=5)
        ttk.Button(btns, text="설정 저장", command=save_settings).pack(side="right", padx=5)

    def _request_stop(self):
        if self.running:
            self.stop_event.set()
            self._log("[중지 요청] 현재 처리 중인 ROI/환자 단위가 끝나는 즉시 안전하게 중지합니다.")
            self._set_status("Stop requested...")
        else:
            self._log("[중지] 현재 실행 중인 분석이 없습니다.")

    def _rerun_last(self):
        if not self.last_run:
            messagebox.showwarning("재실행할 작업 없음 / No previous run", "아직 실행한 작업이 없습니다. / No analysis has been run yet.")
            return
        mode, cases, selected_modalities = self.last_run
        self._run_async(mode, preset_cases=cases, selected_modalities=selected_modalities, is_rerun=True)

    def _save_settings_json(self, out_root):
        try:
            os.makedirs(out_root, exist_ok=True)
            fp = os.path.join(out_root, "radiomics_settings_used_{}.json".format(timestamp()))
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(self.radiomics_settings, f, ensure_ascii=False, indent=2)
            self._log("[설정 파일 저장] " + fp)
        except Exception as e:
            self._log("[설정 파일 저장 실패] " + str(e))

    def _browse_root(self):
        p = filedialog.askdirectory(title="DICOM 최상위 폴더 선택")
        if p:
            self.root_var.set(p)

    def _browse_out(self):
        p = filedialog.askdirectory(title="결과 저장 폴더 선택")
        if p:
            self.out_var.set(p)

    def _log(self, msg):
        self.q.put(("log", str(msg)))

    def _set_status(self, msg):
        self.q.put(("status", str(msg)))

    def _poll_queue(self):
        try:
            while True:
                typ, payload = self.q.get_nowait()
                if typ == "log":
                    self.log.insert("end", payload + "\n")
                    self.log.see("end")
                elif typ == "status":
                    self.status_var.set(payload)
                elif typ == "table":
                    self._refresh_table()
                elif typ == "done":
                    self._set_buttons_state("normal")
                    self.status_var.set(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _all_buttons(self):
        return [self.btn_check, self.btn_scan, self.btn_settings, self.btn_export, self.btn_uni, self.btn_multi, self.btn_open]

    def _set_buttons_state(self, state):
        for b in self._all_buttons():
            b.configure(state=state)
        if hasattr(self, "btn_stop"):
            self.btn_stop.configure(state="normal" if state == "disabled" else "disabled")
        if hasattr(self, "btn_rerun"):
            self.btn_rerun.configure(state="normal" if (not self.running and self.last_run is not None) else "disabled")

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(self.cases):
            self.tree.insert("", "end", iid=str(i), values=(
                c.patient_id, c.study_date, c.available_modalities, c.unimodal_plan, c.multimodal_plan,
                c.pet_dir, c.spect_dir, c.ct_dir, c.rt_path, c.match_note
            ))

    def _check_env(self):
        self._log("[1단계 환경 점검]")
        try:
            import radiomics
            from radiomics import featureextractor
            featureextractor.RadiomicsFeatureExtractor()
            self._log("  PyRadiomics OK: " + str(getattr(radiomics, "__version__", "version unknown")))
        except Exception as e:
            self._log("  PyRadiomics ERROR: " + str(e))
        try:
            import SimpleITK as sitk
            self._log("  SimpleITK OK: " + str(sitk.Version()).split("\n")[0])
        except Exception as e:
            self._log("  SimpleITK ERROR: " + str(e))
        try:
            import pydicom
            self._log("  pydicom OK: " + str(getattr(pydicom, "__version__", "version unknown")))
        except Exception as e:
            self._log("  pydicom ERROR: " + str(e))
        self._log("  Python: " + str(sys.executable))
        self._log("  PyRadiomics reference: van Griethuysen et al., Cancer Research 2017;77:e104-e107. DOI: 10.1158/0008-5472.CAN-17-0339")

    def _scan_async(self):
        root = self.root_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showerror("DICOM 폴더 필요", "2단계에서 DICOM 최상위 폴더를 먼저 선택하세요.")
            return
        self._set_buttons_state("disabled")
        threading.Thread(target=self._scan_worker, args=(root,), daemon=True).start()

    def _scan_worker(self, root):
        try:
            self._set_status("Scanning DICOM metadata...")
            self._log("[2단계 스캔 시작] " + root)
            self.series_list, self.rt_list, skipped = scan_dicom_tree(root, progress_callback=self._log)
            self.cases = build_patient_cases(self.series_list, self.rt_list)
            self._log("[스캔 완료] image series={}, RTSTRUCT={}, cases={}, skipped={}".format(len(self.series_list), len(self.rt_list), len(self.cases), skipped))
            ready_uni = sum(c.status_unimodal == "Ready" for c in self.cases)
            ready_multi = sum(c.status_multimodal == "Ready" for c in self.cases)
            self._log("  Unimodal Ready: {} case(s)".format(ready_uni))
            self._log("  Multimodal Ready: {} case(s)".format(ready_multi))
            self._log("  표에서 Detected modalities / 가능 분석을 확인하세요.")
            self.q.put(("table", None))
        except Exception:
            self._log(traceback.format_exc())
        finally:
            self.q.put(("done", "Scan finished"))

    def _export_inventory(self):
        if not self.cases:
            messagebox.showwarning("스캔 결과 없음", "먼저 DICOM metadata 스캔을 실행하세요.")
            return
        out = os.path.join(self.out_var.get().strip(), "_metadata_inventory")
        os.makedirs(out, exist_ok=True)
        case_csv, series_csv, rt_csv = export_inventory_csv(os.path.join(out, "cases_{}.csv".format(timestamp())), self.cases, self.series_list, self.rt_list)
        self._log("[CSV 저장 완료]")
        self._log("  " + case_csv)
        self._log("  " + series_csv)
        self._log("  " + rt_csv)
        open_folder(out)

    def _selected_cases(self, mode):
        if not self.cases:
            return []
        ids = self.tree.selection()
        selected = [self.cases[int(i)] for i in ids] if ids else self.cases
        if mode == "unimodal":
            return [c for c in selected if c.status_unimodal == "Ready"]
        return [c for c in selected if c.status_multimodal == "Ready"]

    def _modalities_for_case(self, c):
        mods = []
        if c.pet_dir:
            mods.append(("PET", c.pet_dir))
        if c.spect_dir:
            mods.append(("SPECT", c.spect_dir))
        if c.ct_dir:
            mods.append(("CT", c.ct_dir))
        return mods

    def _available_unimodal_counts(self, cases):
        counts = {m: 0 for m in MODALITIES}
        for c in cases:
            if c.status_unimodal != "Ready":
                continue
            for m, _ in self._modalities_for_case(c):
                if m in counts:
                    counts[m] += 1
        return counts

    def _choose_unimodal_and_run(self):
        cases = self._selected_cases("unimodal")
        if not cases:
            messagebox.showwarning("Ready case 없음 / No ready case", "실행 가능한 Unimodal case가 없습니다. 먼저 DICOM metadata 스캔 결과를 확인하세요.")
            return
        counts = self._available_unimodal_counts(cases)
        available = [m for m in MODALITIES if counts.get(m, 0) > 0]
        if not available:
            messagebox.showwarning("Modality 없음 / No modality", "선택된 환자에서 실행 가능한 PET/SPECT/CT가 없습니다.")
            return

        win = tk.Toplevel(self)
        win.title("Unimodal modality selection / 유니모달 선택")
        win.geometry("560x360")
        win.transient(self)
        win.grab_set()
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Unimodal 실행 항목 선택 / Select modality for Unimodal extraction", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0,8))
        ttk.Label(frm, text="PET, SPECT, CT 중 필요한 modality만 선택할 수 있습니다. / Choose one or more modalities to run.", foreground="#555", wraplength=510).pack(anchor="w", pady=(0,12))

        vars_ = {}
        for m in MODALITIES:
            v = tk.BooleanVar(value=(m in available))
            state = "normal" if m in available else "disabled"
            text = "{}  —  실행 가능 case {}개 / {} ready case(s)".format(m, counts.get(m, 0), counts.get(m, 0))
            cb = ttk.Checkbutton(frm, text=text, variable=v, state=state)
            cb.pack(anchor="w", pady=6)
            vars_[m] = v

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=14)
        ttk.Label(frm, text="표에서 환자를 선택했다면 선택 환자만 실행합니다. 아무것도 선택하지 않았다면 Ready 전체가 대상입니다. / Selected table rows limit the run; otherwise all Ready cases are used.", foreground="#666", wraplength=510).pack(anchor="w")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(18,0))
        def start():
            selected = [m for m, v in vars_.items() if v.get()]
            if not selected:
                messagebox.showwarning("선택 필요 / Selection required", "실행할 modality를 하나 이상 선택하세요.")
                return
            win.destroy()
            self._run_async("unimodal", preset_cases=cases, selected_modalities=selected)
        ttk.Button(btns, text="취소 / Cancel", command=win.destroy).pack(side="right", padx=5)
        ttk.Button(btns, text="선택 항목 실행 / Run selected", command=start).pack(side="right", padx=5)

    def _run_async(self, mode, preset_cases=None, selected_modalities=None, is_rerun=False):
        cases = list(preset_cases) if preset_cases is not None else self._selected_cases(mode)
        if not cases:
            messagebox.showwarning("Ready case 없음 / No ready case", "실행 가능한 case가 없습니다. 먼저 스캔 결과의 가능 분석을 확인하세요.")
            return
        if selected_modalities is None:
            selected_modalities = MODALITIES[:] if mode == "unimodal" else None
        self.stop_event.clear()
        self.running = True
        self.last_run = (mode, cases, selected_modalities)
        self._set_buttons_state("disabled")
        if is_rerun:
            self._log("[재실행 / Re-run] 마지막 {} 작업을 같은 case 목록과 현재 설정으로 다시 실행합니다. modalities={}".format(mode, selected_modalities or "all available"))
        threading.Thread(target=self._run_worker, args=(mode, cases, selected_modalities), daemon=True).start()

    def _run_worker(self, mode, cases, selected_modalities=None):
        try:
            out_root = self.out_var.get().strip()
            os.makedirs(out_root, exist_ok=True)
            log_dir = os.path.join(out_root, "_gui_logs")
            os.makedirs(log_dir, exist_ok=True)
            self._set_status("Running {}...".format(mode))
            self._log("[분석 시작 / Run started] mode={}, n_cases={}, selected_modalities={}".format(mode, len(cases), selected_modalities or "all available"))
            self._log("[적용 설정] " + self._settings_summary())
            self._save_settings_json(out_root)
            import unimodal_engine as engine
            writer = QueueWriter(self._log)
            if mode == "unimodal":
                for idx, c in enumerate(cases, 1):
                    if self.stop_event.is_set():
                        self._log("[중지 완료] 남은 Unimodal case는 실행하지 않았습니다.")
                        break
                    for modality, image_dir in self._modalities_for_case(c):
                        if selected_modalities and modality not in selected_modalities:
                            continue
                        if self.stop_event.is_set():
                            break
                        out_dir = os.path.join(out_root, "unimodal", modality.lower())
                        os.makedirs(out_dir, exist_ok=True)
                        try:
                            self._log("[{}/{}] Unimodal {}: {}".format(idx, len(cases), modality, c.patient_id))
                            with redirect_stdout(writer), redirect_stderr(writer):
                                engine.run_radiomics_pipeline(image_dir, c.rt_path, out_dir, c.patient_id, modality, radiomics_settings=self.radiomics_settings, stop_event=self.stop_event)
                        except Exception as e:
                            self._log("  ERROR {} {}: {}".format(c.patient_id, modality, e))
                            with open(os.path.join(log_dir, "error_unimodal_{}_{}_{}.txt".format(modality, c.patient_id, timestamp())), "w", encoding="utf-8") as f:
                                f.write(traceback.format_exc())
                for modality in (selected_modalities or MODALITIES):
                    self._merge_outputs(os.path.join(out_root, "unimodal", modality.lower()), modality, os.path.join(out_root, "merged_unimodal_{}_radiomics.xlsx".format(modality)))
            else:
                # Multimodal here means: run every available modality for cases that have >=2 modalities,
                # then create per-modality merged files and pairwise combined tables.
                for idx, c in enumerate(cases, 1):
                    if self.stop_event.is_set():
                        self._log("[중지 완료] 남은 Multimodal case는 실행하지 않았습니다.")
                        break
                    mods = self._modalities_for_case(c)
                    self._log("[{}/{}] Multimodal case {}: {}".format(idx, len(cases), c.patient_id, " + ".join([m for m, _ in mods])))
                    for modality, image_dir in mods:
                        if self.stop_event.is_set():
                            break
                        out_dir = os.path.join(out_root, "multimodal", modality.lower())
                        os.makedirs(out_dir, exist_ok=True)
                        try:
                            self._log("  Extract {}".format(modality))
                            with redirect_stdout(writer), redirect_stderr(writer):
                                engine.run_radiomics_pipeline(image_dir, c.rt_path, out_dir, c.patient_id, modality, radiomics_settings=self.radiomics_settings, stop_event=self.stop_event)
                        except Exception as e:
                            self._log("  ERROR {} {}: {}".format(c.patient_id, modality, e))
                            with open(os.path.join(log_dir, "error_multimodal_{}_{}_{}.txt".format(modality, c.patient_id, timestamp())), "w", encoding="utf-8") as f:
                                f.write(traceback.format_exc())
                modality_dirs = {}
                for modality in MODALITIES:
                    d = os.path.join(out_root, "multimodal", modality.lower())
                    modality_dirs[modality] = d
                    self._merge_outputs(d, modality, os.path.join(out_root, "merged_multimodal_{}_radiomics.xlsx".format(modality)))
                self._make_pairwise_combined_outputs(out_root, modality_dirs)
            writer.flush()
            self._log("[분석 완료]")
            open_folder(out_root)
        except Exception:
            self._log(traceback.format_exc())
        finally:
            self.running = False
            self.q.put(("done", "{} finished".format(mode)))

    def _merge_outputs(self, input_dir, modality, output_file):
        try:
            import pandas as pd
            files = glob.glob(os.path.join(input_dir, "{}_radiomics_*.xlsx".format(modality)))
            if not files:
                self._log("  Merge skipped: no {} files in {}".format(modality, input_dir))
                return None
            dfs = []
            for fp in files:
                pid = os.path.splitext(os.path.basename(fp))[0].replace("{}_radiomics_".format(modality), "")
                df = pd.read_excel(fp, engine="openpyxl")
                df.insert(0, "PatientID", pid)
                df.insert(1, "Modality", modality)
                dfs.append(df)
            merged = pd.concat(dfs, ignore_index=True)
            merged.to_excel(output_file, index=False, engine="openpyxl")
            self._log("  Merged: " + output_file)
            return output_file
        except Exception as e:
            self._log("  Merge ERROR {}: {}".format(modality, e))
            return None

    def _read_patient_feature_file(self, folder, modality, patient_id):
        import pandas as pd
        fp = os.path.join(folder, "{}_radiomics_{}.xlsx".format(modality, patient_id))
        if not os.path.exists(fp):
            return None
        df = pd.read_excel(fp, engine="openpyxl")
        # Convert feature rows to wide feature columns per ROI column.
        if "Feature" not in df.columns:
            return None
        roi_cols = [c for c in df.columns if c != "Feature"]
        rows = []
        for roi in roi_cols:
            row = {"PatientID": patient_id, "ROI": roi}
            for _, r in df.iterrows():
                row["{}_{}".format(modality, r["Feature"])] = r[roi]
            rows.append(row)
        return pd.DataFrame(rows)

    def _make_pairwise_combined_outputs(self, out_root, modality_dirs):
        try:
            import pandas as pd
            pairs = [("PET", "SPECT"), ("PET", "CT"), ("SPECT", "CT")]
            combo_dir = os.path.join(out_root, "multimodal_combined")
            os.makedirs(combo_dir, exist_ok=True)
            for a, b in pairs:
                rows = []
                for c in self.cases:
                    if c.status_multimodal != "Ready":
                        continue
                    available = [m for m, _ in self._modalities_for_case(c)]
                    if a not in available or b not in available:
                        continue
                    da = self._read_patient_feature_file(modality_dirs[a], a, c.patient_id)
                    db = self._read_patient_feature_file(modality_dirs[b], b, c.patient_id)
                    if da is None or db is None:
                        continue
                    merged = pd.merge(da, db, on=["PatientID", "ROI"], how="outer")
                    rows.append(merged)
                if rows:
                    out = os.path.join(combo_dir, "combined_{}_{}_wide_by_ROI.xlsx".format(a, b))
                    pd.concat(rows, ignore_index=True).to_excel(out, index=False, engine="openpyxl")
                    self._log("  Combined pairwise table: " + out)
        except Exception as e:
            self._log("  Pairwise combine ERROR: " + str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()
