from __future__ import annotations

import json
import os
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
from celestial_triage.context import build_candidate_context
from celestial_triage.macapp.runner import SafeCliRunner
from celestial_triage.scoring.followup import build_followup_priority
from celestial_triage.scoring.interpretation import build_interpretation_summary
from celestial_triage.storage.db import Database
from celestial_triage.ui.sky_map import nearest_point, prepare_candidate_sky_points


def _looks_like_repo_root(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "src" / "celestial_triage" / "cli.py").exists()


def _resolve_repo_root() -> Path:
    env_repo = Path((os.environ.get("CELESTIAL_TRIAGE_REPO") or "").strip()).expanduser()
    if str(env_repo) and _looks_like_repo_root(env_repo):
        return env_repo

    candidates = [
        Path.cwd(),
        Path.home() / ".openclaw" / "workspace" / "celestial-triage",
        Path(__file__).resolve().parents[3],
    ]
    for c in candidates:
        if _looks_like_repo_root(c):
            return c
    return Path.cwd()


def _resolve_ui_python(repo_root: Path) -> str:
    env_py = (os.environ.get("CELESTIAL_TRIAGE_PYTHON") or "").strip()
    if env_py:
        return env_py
    for rel in (".venv312/bin/python3", ".venv/bin/python3", ".venv/bin/python"):
        p = repo_root / rel
        if p.exists():
            return str(p)
    return "python3"


def _settings_path() -> Path:
    cfg = Path.home() / ".config" / "celestial-triage"
    cfg.mkdir(parents=True, exist_ok=True)
    return cfg / "macapp_settings.json"


class AnalystConsoleApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Celestial Triage — Mac Analyst Console")
        self.geometry("1480x920")

        self.repo_root = _resolve_repo_root()
        self.db_path = self.repo_root / DB_PATH
        self.db = Database(self.db_path)
        self.runner = SafeCliRunner(_resolve_ui_python(self.repo_root))
        self.settings_file = _settings_path()
        self.settings = self._load_settings()

        self.candidates: list[dict] = []
        self.selected_candidate_id: str | None = None
        self.command_history: list[dict] = []
        self._current_images: list[dict] = []
        self._image_photos: list[tk.PhotoImage] = []
        self._sky_points: list[dict] = []

        self._build_layout()
        self.refresh_all()

    def _load_settings(self) -> dict[str, str]:
        if not self.settings_file.exists():
            return {}
        try:
            return json.loads(self.settings_file.read_text())
        except Exception:
            return {}

    def _save_settings(self) -> None:
        payload = {
            "lasair_api_token": self.lasair_token_var.get().strip(),
            "lasair_api_base_url": self.lasair_base_url_var.get().strip(),
        }
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps(payload, indent=2))
        try:
            os.chmod(self.settings_file, 0o600)
        except Exception:
            pass
        self.settings = payload
        self.log(f"[settings] saved: {self.settings_file}")

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
        parent.rowconfigure(1, weight=3)
        parent.rowconfigure(2, weight=1)
        parent.rowconfigure(3, weight=2)

        ttk.Label(parent, text="Candidate Detail", font=("SF Pro Text", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.detail_text = tk.Text(parent, wrap="word")
        self.detail_text.grid(row=1, column=0, sticky="nsew", pady=6)

        self.context_frame = ttk.LabelFrame(parent, text="Context Panel")
        self.context_frame.grid(row=2, column=0, sticky="nsew", pady=6)
        self.context_text = tk.Text(self.context_frame, height=8, wrap="word")
        self.context_text.pack(fill="both", expand=True)

        self.sky_map_frame = ttk.LabelFrame(parent, text="Sky Map (RA/DEC)")
        self.sky_map_frame.grid(row=3, column=0, sticky="nsew", pady=6)
        self.sky_map_canvas = tk.Canvas(self.sky_map_frame, height=220, background="#0f1115", highlightthickness=0)
        self.sky_map_canvas.pack(fill="both", expand=True)
        self.sky_map_canvas.bind("<Button-1>", self.on_sky_map_click)

    def _build_right(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        ttk.Label(parent, text="Images + Actions", font=("SF Pro Text", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        images_frame = ttk.LabelFrame(parent, text="Image Panel")
        images_frame.grid(row=1, column=0, sticky="nsew", pady=6)
        images_frame.columnconfigure(0, weight=1)
        images_frame.rowconfigure(0, weight=1)

        self.image_canvas = tk.Canvas(images_frame, height=260, highlightthickness=0)
        self.image_scroll = ttk.Scrollbar(images_frame, orient="vertical", command=self.image_canvas.yview)
        self.image_canvas.configure(yscrollcommand=self.image_scroll.set)
        self.image_canvas.grid(row=0, column=0, sticky="nsew")
        self.image_scroll.grid(row=0, column=1, sticky="ns")

        self.image_panel_container = ttk.Frame(self.image_canvas)
        self.image_canvas_window = self.image_canvas.create_window((0, 0), window=self.image_panel_container, anchor="nw")

        def _on_frame_configure(_event=None):
            self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all"))

        def _on_canvas_configure(event):
            self.image_canvas.itemconfigure(self.image_canvas_window, width=event.width)

        self.image_panel_container.bind("<Configure>", _on_frame_configure)
        self.image_canvas.bind("<Configure>", _on_canvas_configure)

        notebook = ttk.Notebook(parent)
        notebook.grid(row=2, column=0, sticky="nsew")

        self.console_text = tk.Text(parent, height=12)

        self.tab_ingest = ttk.Frame(notebook, padding=6)
        self.tab_review = ttk.Frame(notebook, padding=6)
        self.tab_export = ttk.Frame(notebook, padding=6)
        self.tab_bundle = ttk.Frame(notebook, padding=6)
        self.tab_ops = ttk.Frame(notebook, padding=6)
        self.tab_settings = ttk.Frame(notebook, padding=6)

        notebook.add(self.tab_ingest, text="Ingest")
        notebook.add(self.tab_review, text="Review")
        notebook.add(self.tab_export, text="Export")
        notebook.add(self.tab_bundle, text="Bundle")
        notebook.add(self.tab_ops, text="Ops")
        notebook.add(self.tab_settings, text="Settings")

        self._build_ingest_tab()
        self._build_review_tab()
        self._build_export_tab()
        self._build_bundle_tab()
        self._build_ops_tab()
        self._build_settings_tab()

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
        ttk.Button(f, text="run-pipeline", command=lambda: self.run_command("run-pipeline", {})).grid(row=1, column=0, sticky="ew")
        ttk.Button(f, text="top-candidates", command=lambda: self.run_command("top-candidates", {"limit": 20})).grid(row=2, column=0, sticky="ew")
        ttk.Button(f, text="followup-report", command=lambda: self.run_command("followup-report", {"limit": 20})).grid(row=3, column=0, sticky="ew")
        ttk.Button(f, text="scenario-report", command=lambda: self.run_command("scenario-report", {})).grid(row=4, column=0, sticky="ew")

    def _build_settings_tab(self) -> None:
        f = self.tab_settings
        self.lasair_token_var = tk.StringVar(value=self.settings.get("lasair_api_token", ""))
        self.lasair_base_url_var = tk.StringVar(
            value=self.settings.get("lasair_api_base_url", "https://lasair.lsst.ac.uk/api")
        )

        ttk.Label(f, text="Lasair API token").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.lasair_token_var, show="*", width=42).grid(row=0, column=1, sticky="ew")

        ttk.Label(f, text="Lasair API base URL").grid(row=1, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.lasair_base_url_var, width=42).grid(row=1, column=1, sticky="ew")

        ttk.Button(f, text="Save Settings", command=self._save_settings).grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(
            f,
            text=f"Stored at: {self.settings_file}",
            foreground="#666",
        ).grid(row=3, column=0, columnspan=2, sticky="w")

    def run_ingest_lasair(self) -> None:
        params = {
            "lasair_mode": self.ingest_mode.get(),
            "base_url": self.ingest_base_url.get() or self.lasair_base_url_var.get(),
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
        extra_env: dict[str, str] = {}
        token = (self.lasair_token_var.get() if hasattr(self, "lasair_token_var") else "").strip()
        base_url = (self.lasair_base_url_var.get() if hasattr(self, "lasair_base_url_var") else "").strip()
        if token:
            extra_env["LASAIR_API_TOKEN"] = token
        if base_url:
            extra_env["LASAIR_API_BASE_URL"] = base_url

        result = self.runner.run(name, params, cwd=self.repo_root, extra_env=extra_env)
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
        self.render_sky_map()
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
        self.render_sky_map()

    def _priority_color(self, p: str) -> str:
        return {
            "urgent": "#ff4d4f",
            "high": "#ffa940",
            "medium": "#69c0ff",
            "low": "#8c8c8c",
        }.get(p, "#8c8c8c")

    def render_sky_map(self) -> None:
        c = self.sky_map_canvas
        c.delete("all")

        points = prepare_candidate_sky_points(self.db)
        self._sky_points = points
        if not points:
            c.create_text(12, 12, anchor="nw", fill="#ddd", text="No plottable candidates with RA/DEC")
            return

        width = max(320, c.winfo_width() or 320)
        height = max(220, c.winfo_height() or 220)
        pad = 22

        ras = [p["ra"] for p in points]
        decs = [p["dec"] for p in points]
        rmin, rmax = min(ras), max(ras)
        dmin, dmax = min(decs), max(decs)
        if rmax == rmin:
            rmax += 1e-6
        if dmax == dmin:
            dmax += 1e-6

        def x_of(ra: float) -> float:
            return pad + (ra - rmin) / (rmax - rmin) * (width - 2 * pad)

        def y_of(dec: float) -> float:
            return height - pad - (dec - dmin) / (dmax - dmin) * (height - 2 * pad)

        c.create_rectangle(pad, pad, width - pad, height - pad, outline="#2b2f36")
        c.create_text(pad, height - 6, anchor="sw", fill="#999", text=f"RA [{rmin:.2f}..{rmax:.2f}]")
        c.create_text(width - pad, 6, anchor="ne", fill="#999", text=f"DEC [{dmin:.2f}..{dmax:.2f}]")

        for p in points:
            x = x_of(float(p["ra"]))
            y = y_of(float(p["dec"]))
            p["_px"] = x
            p["_py"] = y
            color = self._priority_color(str(p.get("followup_priority", "low")))
            r = 5 if str(p.get("followup_priority")) in ("urgent", "high") else 4
            outline = "#ffffff" if p.get("candidate_id") == self.selected_candidate_id else ""
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=outline)

        c.create_text(
            pad,
            6,
            anchor="nw",
            fill="#bbb",
            text="Color by follow-up priority (red=urgent, orange=high, blue=medium, gray=low)",
        )

    def on_sky_map_click(self, event) -> None:
        pt = nearest_point(self._sky_points, float(event.x), float(event.y), max_px_dist=12.0)
        if not pt:
            return
        cid = str(pt["candidate_id"])
        self.selected_candidate_id = cid
        self.review_candidate.set(cid)

        # Sync queue selection if candidate is visible in current filter.
        for i, row in enumerate(self.candidates):
            if row.get("candidate_id") == cid:
                self.candidate_list.selection_clear(0, tk.END)
                self.candidate_list.selection_set(i)
                self.candidate_list.see(i)
                break

        self.refresh_detail()
        self.render_sky_map()

    def refresh_detail(self) -> None:
        self.detail_text.delete("1.0", tk.END)
        self.context_text.delete("1.0", tk.END)
        for child in self.image_panel_container.winfo_children():
            child.destroy()
        self._image_photos = []
        self._sky_points = []
        cid = self.selected_candidate_id
        if not cid:
            return

        try:
            cand = self.db.get_candidate_with_features(cid)
            scores = self.db.get_latest_scores(cid)
            dets = self.db.get_detections_for_candidate(cid)
            images = self.db.get_images_for_candidate(cid)
            context = build_candidate_context(self.db, cid)
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
        self.context_text.insert("end", json.dumps(context, indent=2))

        self._current_images = images
        self._image_photos = []
        self._render_images_panel(images)

    def _image_kind_label(self, kind: str) -> str:
        mapping = {
            "science": "Science",
            "reference": "Reference",
            "difference": "Difference",
            "survey_context_panstarrs": "Survey Context (Pan-STARRS)",
            "survey_context_skyview": "Survey Context (SkyView DSS)",
        }
        return mapping.get(kind, kind)

    def _render_images_panel(self, images: list[dict]) -> None:
        if not images:
            ttk.Label(self.image_panel_container, text="No images available for selected candidate").grid(
                row=0, column=0, sticky="w", padx=4, pady=6
            )
            return

        row_idx = 0
        for img in images:
            kind = str(img.get("kind") or "unknown")
            header = ttk.Label(
                self.image_panel_container,
                text=self._image_kind_label(kind),
                font=("SF Pro Text", 11, "bold"),
            )
            header.grid(row=row_idx, column=0, sticky="w", padx=4, pady=(6, 2))
            row_idx += 1

            local_path = img.get("local_path")
            remote_url = img.get("remote_url")

            rendered = False
            if local_path and Path(local_path).exists():
                try:
                    photo = tk.PhotoImage(file=local_path)
                    self._image_photos.append(photo)
                    lbl = ttk.Label(self.image_panel_container, image=photo)
                    lbl.grid(row=row_idx, column=0, sticky="w", padx=8)
                    rendered = True
                except Exception:
                    rendered = False

            if not rendered:
                fallback_text = f"No local preview\n{remote_url or 'No remote URL'}"
                ttk.Label(self.image_panel_container, text=fallback_text).grid(
                    row=row_idx, column=0, sticky="w", padx=8
                )

            btns = ttk.Frame(self.image_panel_container)
            btns.grid(row=row_idx + 1, column=0, sticky="w", padx=8, pady=(2, 8))
            if local_path and Path(local_path).exists():
                ttk.Button(btns, text="Open Local", command=lambda p=local_path: webbrowser.open(f"file://{p}")).pack(side=tk.LEFT)
            if remote_url and str(remote_url).startswith(("http://", "https://")):
                ttk.Button(btns, text="Open Remote", command=lambda u=remote_url: webbrowser.open(str(u))).pack(side=tk.LEFT, padx=6)

            row_idx += 2


def main() -> None:
    app = AnalystConsoleApp()
    app.mainloop()


if __name__ == "__main__":
    main()
