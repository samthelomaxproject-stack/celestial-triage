from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVED_COMMANDS = {
    "init-db",
    "seed-mock",
    "ingest-jsonl",
    "ingest-lasair",
    "run-pipeline",
    "top-candidates",
    "scenario-report",
    "update-review",
    "followup-report",
    "export-candidates",
    "bundle-cases",
}


@dataclass
class CommandResult:
    name: str
    args: list[str]
    success: bool
    return_code: int
    stdout: str
    stderr: str
    ran_at: str


class SafeCliRunner:
    def __init__(self, python_bin: str = "python3") -> None:
        self.python_bin = python_bin

    def build_args(self, command: str, params: dict[str, Any]) -> list[str]:
        if command not in APPROVED_COMMANDS:
            raise ValueError(f"command not allowed: {command}")

        args = [self.python_bin, "-m", "celestial_triage.cli", command]

        def add_opt(flag: str, value: Any) -> None:
            if value is None or value == "":
                return
            args.extend([flag, str(value)])

        if command == "seed-mock":
            add_opt("--count", params.get("count"))
        elif command == "ingest-jsonl":
            add_opt("--input", params.get("input"))
            add_opt("--broker", params.get("broker"))
        elif command == "ingest-lasair":
            add_opt("--preset", params.get("preset"))
            add_opt("--lasair-mode", params.get("lasair_mode"))
            add_opt("--base-url", params.get("base_url"))
            add_opt("--limit", params.get("limit"))
            add_opt("--query", params.get("query"))
            add_opt("--days-back", params.get("days_back"))
            add_opt("--selected", params.get("selected"))
            add_opt("--tables", params.get("tables"))
            add_opt("--conditions", params.get("conditions"))
        elif command == "top-candidates":
            add_opt("--detector", params.get("detector"))
            add_opt("--band", params.get("band"))
            add_opt("--limit", params.get("limit"))
        elif command == "scenario-report":
            add_opt("--top-iso-limit", params.get("top_iso_limit"))
        elif command == "update-review":
            add_opt("--candidate-id", params.get("candidate_id"))
            add_opt("--state", params.get("state"))
            add_opt("--tags", params.get("tags"))
            add_opt("--notes", params.get("notes"))
        elif command == "followup-report":
            add_opt("--limit", params.get("limit"))
        elif command == "export-candidates":
            add_opt("--format", params.get("format"))
            add_opt("--output", params.get("output"))
            add_opt("--review-state", params.get("review_state"))
            add_opt("--followup-priority", params.get("followup_priority"))
            add_opt("--detector", params.get("detector"))
            if params.get("high_iso"):
                args.append("--high-iso")
            if params.get("tagged_only"):
                args.append("--tagged-only")
            add_opt("--broker", params.get("broker"))
        elif command == "bundle-cases":
            add_opt("--output-dir", params.get("output_dir"))
            add_opt("--review-state", params.get("review_state"))
            add_opt("--followup-priority", params.get("followup_priority"))
            add_opt("--detector", params.get("detector"))
            if params.get("high_iso"):
                args.append("--high-iso")
            if params.get("tagged_only"):
                args.append("--tagged-only")
            add_opt("--broker", params.get("broker"))
            if params.get("include_details"):
                args.append("--include-details")

        return args

    def preview(self, command: str, params: dict[str, Any]) -> str:
        args = self.build_args(command, params)
        return " ".join(shlex.quote(a) for a in args)

    def run(self, command: str, params: dict[str, Any], cwd: Path | None = None) -> CommandResult:
        args = self.build_args(command, params)
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        return CommandResult(
            name=command,
            args=args,
            success=proc.returncode == 0,
            return_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            ran_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_json(self, result: CommandResult) -> str:
        return json.dumps(
            {
                "name": result.name,
                "args": result.args,
                "success": result.success,
                "return_code": result.return_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "ran_at": result.ran_at,
            },
            indent=2,
        )
