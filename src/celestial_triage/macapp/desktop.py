from __future__ import annotations

import json
import sqlite3
import sys
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception as exc:  # pragma: no cover
    print("[celestial-triage] Tk runtime missing: unable to import tkinter/_tkinter.")
    print("Install a Tk-capable Python runtime, then relaunch the desktop app.")
    print("Suggested setup on macOS:")
    print("  brew install python@3.12")
    print("  brew install python-tk@3.12")
    print("  python3.12 -m venv .venv312")
    print("  source .venv312/bin/activate")
    print("  pip install -r requirements.txt")
    print(f"Details: {exc}")
    sys.exit(1)

from celestial_triage.config import DB_PATH
from celestial_triage.macapp.runner import SafeCliRunner
from celestial_triage.scoring.followup import build_followup_priority
from celestial_triage.scoring.interpretation import build_interpretation_summary
from celestial_triage.storage.db import Database


class AnalystConsoleApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Celestial Triage — Mac Analyst Console")
        self.geometry("1480x920")

        self.db_path = DB_PATH
        self.db = Database(self.db_path)
        self.runner = SafeCliRunner("python3")

        self.candidates: list[dict] = []
        self.selected_candidate_id: str | None = None
        self.command_history: list[dict] = []
        self._current_images: list[dict] = []

        self._build_layout()
        self.refresh_all()

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        pane.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(pane, padding=8)
        center = ttk.Frame(pane, padding=8)
        right = ttk.Frame(pane, padding=8)

        pane.add(left, weight=2)
        pane.add(center, weight=4)
        pane.add(right, weight=3)

        self._build_left(left)
        self._build_center(center)
        self._build_right(right)

    def _build_left(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        ttk.Label(parent, text="Candidate Queue", font=("SF Pro Text", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        filter_row = ttk.Frame(parent)
        filter_row.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Label(filter_row, text="Review filter:").pack(side=tk.LEFT)
        self.review_filter = tk.StringVar(value="all")
        ttk.Combobox(
            filter_row,
            textvariable=self.review_filter,
            values=["all", "new", "reviewing", "follow-up", "dismissed"],
            width=14,
            state="readonly",
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(filter_row, text="Refresh", command=self.refresh_all).pack(side=tk.LEFT)

        self.candidate_list = tk.Listbox(parent, height=30)
        self.candidate_list.grid(row=2, column=0, sticky="nsew")
        self.candidate_list.bind("<<ListboxSelect>>", self.on_select_candidate)

    def _build_center(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(parent, text="Candidate Detail", font=("SF Pro Text", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.detail_text = tk.Text(parent, wrap="word")
        self.detail_text.grid(row=1, column=0, sticky="nsew", pady=6)

    def _build_right(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        ttk.Label(parent, text="Images + Actions", font=("SF Pro Text", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        images_frame = ttk.LabelFrame(parent, text="Image Panel")
        images_frame.grid(row=1, column=0, sticky="ew", pady=6)
        images_frame.columnconfigure(0, weight=1)
        self.image_list = tk.Listbox(images_frame, height=8)
        self.image_list.grid(row=0, column=0, sticky="ew")
        ttk.Button(images_frame, text="Open selected image URL", command=self.open_selected_image).grid(
            row=1, column=0, sticky="ew", pady=4
        )

        notebook = ttk.Notebook(parent)
        notebook.grid(row=2, column=0, sticky="nsew")

        self.console_text = tk.Text(parent, height=12)

        self.tab_ingest = ttk.Frame(notebook, padding=6)
        self.tab_review = ttk.Frame(notebook, padding=6)
        self.tab_export = ttk.Frame(notebook, padding=6)
        self.tab_bundle = ttk.Frame(notebook, padding=6)
        self.tab_ops = ttk.Frame(notebook, padding=6)

        notebook.add(self.tab_ingest, text="Ingest")
        notebook.add(self.tab_review, text="Review")
        notebook.add(self.tab_export, text="Export")
        notebook.add(self.tab_bundle, text="Bundle")
        notebook.add(self.tab_ops, text="Ops")

        self._build_ingest_tab()
        self._build_review_tab()
        self._build_export_tab()
        self._build_bundle_tab()
        self._build_ops_tab()

        self.console_text.grid(row=3, column=0, sticky="nsew", pady=6)

    def _build_ingest_tab(self) -> None:
        f = self.tab_ingest
        self.ingest_mode = tk.StringVar(value="lsst")
        self.ingest_base_url = tk.StringVar(value="https://lasair.lsst.ac.uk/api")
        self.ingest_preset = tk.StringVar(value="")
        self.ingest_limit = tk.StringVar(value="25")
        self.ingest_days_back = tk.StringVar(value="3")
        self.ingest_query = tk.StringVar(value="")
        self.ingest_selected = tk.StringVar(value="diaObjectId, ra, decl")
        self.ingest_tables = tk.StringVar(value="objects")
        self.ingest_conditions = tk.StringVar(value="1=1")

        rows = [
            ("Mode", self.ingest_mode),
            ("Base URL", self.ingest_base_url),
            ("Preset", self.ingest_preset),
            ("Limit", self.ingest_limit),
            ("Days back", self.ingest_days_back),
            ("Query (ztf)", self.ingest_query),
            ("Selected (lsst)", self.ingest_selected),
            ("Tables (lsst)", self.ingest_tables),
            ("Conditions (lsst)", self.ingest_conditions),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w")
            if label == "Mode":
                ttk.Combobox(f, textvariable=var, values=["ztf", "lsst"], state="readonly", width=32).grid(
                    row=i, column=1, sticky="ew"
                )
            else:
                ttk.Entry(f, textvariable=var, width=40).grid(row=i, column=1, sticky="ew")
        ttk.Button(f, text="Run ingest-lasair", command=self.run_ingest_lasair).grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)

    def _build_review_tab(self) -> None:
        f = self.tab_review
        self.review_candidate = tk.StringVar(value="")
        self.review_state = tk.StringVar(value="reviewing")
        self.review_tags = tk.StringVar(value="")
        self.review_notes = tk.StringVar(value="")

        ttk.Label(f, text="Candidate ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.review_candidate, width=42).grid(row=0, column=1, sticky="ew")
        ttk.Label(f, text="State").grid(row=1, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.review_state, values=["new", "reviewing", "follow-up", "dismissed"], state="readonly").grid(row=1, column=1, sticky="ew")
        ttk.Label(f, text="Tags").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.review_tags, width=42).grid(row=2, column=1, sticky="ew")
        ttk.Label(f, text="Notes").grid(row=3, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.review_notes, width=42).grid(row=3, column=1, sticky="ew")
        ttk.Button(f, text="Run update-review", command=self.run_update_review).grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)

    def _build_export_tab(self) -> None:
        f = self.tab_export
        self.export_format = tk.StringVar(value="json")
        self.export_output = tk.StringVar(value="/tmp/celestial_export.json")
        ttk.Label(f, text="Format").grid(row=0, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.export_format, values=["json", "csv", "md"], state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Label(f, text="Output").grid(row=1, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.export_output).grid(row=1, column=1, sticky="ew")
        ttk.Button(f, text="Run export-candidates", command=self.run_export).grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)

    def _build_bundle_tab(self) -> None:
        f = self.tab_bundle
        self.bundle_output = tk.StringVar(value="/tmp/celestial_bundle")
        self.bundle_include_details = tk.BooleanVar(value=True)
        ttk.Label(f, text="Output dir").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.bundle_output).grid(row=0, column=1, sticky="ew")
        ttk.Checkbutton(f, text="Include details", variable=self.bundle_include_details).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Run bundle-cases", command=self.run_bundle).grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)

    def _build_ops_tab(self) -> None:
        f = self.tab_ops
        ttk.Button(f, text="init-db", command=lambda: self.run_command("init-db", {})).grid(row=0, column=0, sticky="ew")
        ttk.Button(f, text="seed-mock", command=lambda: self.run_command("seed-mock", {"count": 120})).grid(row=1, column=0, sticky="ew")
        ttk.Button(f, text="run-pipeline", command=lambda: self.run_command("run-pipeline", {})).grid(row=2, column=0, sticky="ew")
        ttk.Button(f, text="top-candidates", command=lambda: self.run_command("top-candidates", {"limit": 20})).grid(row=3, column=0, sticky="ew")
        ttk.Button(f, text="followup-report", command=lambda: self.run_command("followup-report", {"limit": 20})).grid(row=4, column=0, sticky="ew")
        ttk.Button(f, text="scenario-report", command=lambda: self.run_command("scenario-report", {})).grid(row=5, column=0, sticky="ew")

    def run_ingest_lasair(self) -> None:
        params = {
            "lasair_mode": self.ingest_mode.get(),
            "base_url": self.ingest_base_url.get(),
            "preset": self.ingest_preset.get() or None,
            "limit": self.ingest_limit.get(),
            "days_back": self.ingest_days_back.get(),
            "query": self.ingest_query.get(),
            "selected": self.ingest_selected.get(),
            "tables": self.ingest_tables.get(),
            "conditions": self.ingest_conditions.get(),
        }
        self.run_command("ingest-lasair", params)

    def run_update_review(self) -> None:
        cid = self.review_candidate.get() or self.selected_candidate_id
        if not cid:
            messagebox.showerror("Missing candidate", "Select or enter a candidate id")
            return
        self.run_command(
            "update-review",
            {
                "candidate_id": cid,
                "state": self.review_state.get(),
                "tags": self.review_tags.get(),
                "notes": self.review_notes.get(),
            },
        )

    def run_export(self) -> None:
        self.run_command(
            "export-candidates",
            {
                "format": self.export_format.get(),
                "output": self.export_output.get(),
            },
        )

    def run_bundle(self) -> None:
        self.run_command(
            "bundle-cases",
            {
                "output_dir": self.bundle_output.get(),
                "include_details": self.bundle_include_details.get(),
            },
        )

    def run_command(self, name: str, params: dict) -> None:
        preview = self.runner.preview(name, params)
        self.log(f"\n[{name}] preview: {preview}")
        result = self.runner.run(name, params, cwd=Path.cwd())
        self.command_history.append({"name": name, "success": result.success, "at": result.ran_at})
        self.log(f"[{name}] success={result.success} rc={result.return_code} at={result.ran_at}")
        if result.stdout.strip():
            self.log("stdout:\n" + result.stdout.strip())
        if result.stderr.strip():
            self.log("stderr:\n" + result.stderr.strip())
        self.refresh_all()

    def log(self, text: str) -> None:
        self.console_text.insert("end", text + "\n")
        self.console_text.see("end")

    def refresh_all(self) -> None:
        self.db.init()
        self.load_candidates()
        self.refresh_detail()

    def load_candidates(self) -> None:
        if not self.db_path.exists():
            self.candidates = []
            return
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT candidate_id, review_status FROM candidates ORDER BY last_seen DESC").fetchall()]
        conn.close()
        rf = self.review_filter.get()
        if rf != "all":
            rows = [r for r in rows if (r.get("review_status") or "new") == rf]
        self.candidates = rows
        self.candidate_list.delete(0, tk.END)
        for r in rows:
            self.candidate_list.insert(tk.END, f"{r['candidate_id']}  [{r.get('review_status','new')}]")

    def on_select_candidate(self, _event=None) -> None:
        idx = self.candidate_list.curselection()
        if not idx:
            return
        row = self.candidates[idx[0]]
        self.selected_candidate_id = row["candidate_id"]
        self.review_candidate.set(self.selected_candidate_id)
        self.refresh_detail()

    def refresh_detail(self) -> None:
        self.detail_text.delete("1.0", tk.END)
        self.image_list.delete(0, tk.END)
        cid = self.selected_candidate_id
        if not cid:
            return

        try:
            cand = self.db.get_candidate_with_features(cid)
            scores = self.db.get_latest_scores(cid)
            dets = self.db.get_detections_for_candidate(cid)
            images = self.db.get_images_for_candidate(cid)
        except Exception as exc:
            self.detail_text.insert("end", f"Error loading candidate: {exc}\n")
            return

        score_map = {s["detector_name"]: float(s["score"]) for s in scores}
        interp = build_interpretation_summary(cand.get("features", {}), score_map)
        follow = build_followup_priority(cand.get("features", {}), score_map, cand.get("review_status", "new"))

        payload = {
            "candidate": {k: v for k, v in cand.items() if k != "features"},
            "features": cand.get("features", {}),
            "detector_scores": score_map,
            "interpretation": interp,
            "followup": follow,
            "trajectory_summary": {
                "motion_rate": cand.get("features", {}).get("motion_rate_deg_per_hour"),
                "trajectory_quality": cand.get("features", {}).get("trajectory_quality"),
                "heading_change_consistency": cand.get("features", {}).get("heading_change_consistency"),
            },
            "timeline_count": len(dets),
            "provenance_sources": sorted({d.get("broker_name", "unknown") for d in dets}),
        }
        self.detail_text.insert("end", json.dumps(payload, indent=2))

        self._current_images = images
        for img in images:
            self.image_list.insert(
                tk.END,
                f"{img.get('kind','unknown')} | {img.get('fetch_status','linked')} | {img.get('remote_url','')}"
            )

    def open_selected_image(self) -> None:
        idx = self.image_list.curselection()
        if not idx:
            return
        img = self._current_images[idx[0]]
        url = img.get("remote_url")
        if url:
            webbrowser.open(url)


def main() -> None:
    app = AnalystConsoleApp()
    app.mainloop()


if __name__ == "__main__":
    main()
