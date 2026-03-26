"""
Plate solving integration for image-first workflows.

Supports:
- Astrometry.net remote API (current)
- Future: local plate solver backends

Design allows swapping backends without changing caller interface.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal

import requests


SolveStatus = Literal["success", "failed", "timeout", "error"]


class PlateSolveResult:
    """Structured plate solve result."""
    
    def __init__(
        self,
        status: SolveStatus,
        ra_center: float | None = None,
        dec_center: float | None = None,
        field_width_deg: float | None = None,
        field_height_deg: float | None = None,
        orientation_deg: float | None = None,
        pixel_scale_arcsec: float | None = None,
        backend: str = "unknown",
        job_id: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.status = status
        self.ra_center = ra_center
        self.dec_center = dec_center
        self.field_width_deg = field_width_deg
        self.field_height_deg = field_height_deg
        self.orientation_deg = orientation_deg
        self.pixel_scale_arcsec = pixel_scale_arcsec
        self.backend = backend
        self.job_id = job_id
        self.error_message = error_message
        self.metadata = metadata or {}
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ra_center": self.ra_center,
            "dec_center": self.dec_center,
            "field_width_deg": self.field_width_deg,
            "field_height_deg": self.field_height_deg,
            "orientation_deg": self.orientation_deg,
            "pixel_scale_arcsec": self.pixel_scale_arcsec,
            "backend": self.backend,
            "job_id": self.job_id,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


def solve_image_astrometry_net(
    image_path: Path | str,
    api_key: str | None = None,
    timeout_sec: int = 300,
    scale_low: float | None = None,
    scale_high: float | None = None,
) -> PlateSolveResult:
    """
    Solve image using Astrometry.net remote API.
    
    Args:
        image_path: Path to FITS or image file
        api_key: Astrometry.net API key (or env ASTROMETRY_API_KEY)
        timeout_sec: Max wait time for solve
        scale_low: Lower bound for pixel scale (arcsec/pixel)
        scale_high: Upper bound for pixel scale (arcsec/pixel)
    
    Returns:
        PlateSolveResult with coordinates and metadata
    
    Note: Requires API key from http://nova.astrometry.net/api_help
    """
    api_key = api_key or os.getenv("ASTROMETRY_API_KEY", "")
    
    if not api_key:
        return PlateSolveResult(
            status="error",
            error_message="Astrometry.net API key required. Set ASTROMETRY_API_KEY or pass api_key parameter.",
            backend="astrometry.net"
        )
    
    if not Path(image_path).exists():
        return PlateSolveResult(
            status="error",
            error_message=f"Image file not found: {image_path}",
            backend="astrometry.net"
        )
    
    try:
        # Step 1: Login
        login_url = "http://nova.astrometry.net/api/login"
        login_response = requests.post(login_url, json={"apikey": api_key}, timeout=30)
        login_response.raise_for_status()
        session_key = login_response.json().get("session")
        
        if not session_key:
            return PlateSolveResult(
                status="error",
                error_message="Failed to obtain session key from Astrometry.net",
                backend="astrometry.net"
            )
        
        # Step 2: Upload image
        upload_url = "http://nova.astrometry.net/api/upload"
        
        with open(image_path, "rb") as f:
            files = {"file": f}
            data = {
                "session": session_key,
                "allow_commercial_use": "n",
                "allow_modifications": "n",
                "publicly_visible": "n",
            }
            
            # Optional scale hints
            if scale_low is not None:
                data["scale_lower"] = scale_low
            if scale_high is not None:
                data["scale_upper"] = scale_high
            data["scale_units"] = "arcsecperpix"
            
            upload_response = requests.post(upload_url, files=files, data=data, timeout=60)
            upload_response.raise_for_status()
        
        subid = upload_response.json().get("subid")
        
        if not subid:
            return PlateSolveResult(
                status="error",
                error_message="Failed to get submission ID from Astrometry.net",
                backend="astrometry.net"
            )
        
        # Step 3: Poll for job completion
        job_url = f"http://nova.astrometry.net/api/submissions/{subid}"
        start_time = time.time()
        job_id = None
        
        while time.time() - start_time < timeout_sec:
            time.sleep(5)
            
            job_response = requests.get(job_url, timeout=30)
            job_response.raise_for_status()
            job_data = job_response.json()
            
            jobs = job_data.get("jobs", [])
            if jobs:
                job_id = jobs[0]
                break
        
        if not job_id:
            return PlateSolveResult(
                status="timeout",
                error_message=f"Solve timed out after {timeout_sec} seconds",
                backend="astrometry.net",
                job_id=str(subid)
            )
        
        # Step 4: Get solve results
        job_info_url = f"http://nova.astrometry.net/api/jobs/{job_id}/info"
        
        while time.time() - start_time < timeout_sec:
            time.sleep(3)
            
            info_response = requests.get(job_info_url, timeout=30)
            info_response.raise_for_status()
            info = info_response.json()
            
            status = info.get("status")
            
            if status == "success":
                # Get calibration data
                calib_url = f"http://nova.astrometry.net/api/jobs/{job_id}/calibration"
                calib_response = requests.get(calib_url, timeout=30)
                calib_response.raise_for_status()
                calib = calib_response.json()
                
                return PlateSolveResult(
                    status="success",
                    ra_center=calib.get("ra"),
                    dec_center=calib.get("dec"),
                    field_width_deg=calib.get("width_arcsec", 0) / 3600.0 if calib.get("width_arcsec") else None,
                    field_height_deg=calib.get("height_arcsec", 0) / 3600.0 if calib.get("height_arcsec") else None,
                    orientation_deg=calib.get("orientation"),
                    pixel_scale_arcsec=calib.get("pixscale"),
                    backend="astrometry.net",
                    job_id=str(job_id),
                    metadata={"calibration": calib, "info": info}
                )
            
            elif status == "failure":
                return PlateSolveResult(
                    status="failed",
                    error_message=info.get("error", "Solve failed"),
                    backend="astrometry.net",
                    job_id=str(job_id)
                )
        
        # Timeout on job polling
        return PlateSolveResult(
            status="timeout",
            error_message=f"Job polling timed out after {timeout_sec} seconds",
            backend="astrometry.net",
            job_id=str(job_id)
        )
    
    except Exception as e:
        return PlateSolveResult(
            status="error",
            error_message=f"Astrometry.net error: {str(e)}",
            backend="astrometry.net"
        )


def solve_image(
    image_path: Path | str,
    backend: str = "astrometry.net",
    **kwargs
) -> PlateSolveResult:
    """
    Solve image using configured plate-solving backend.
    
    Args:
        image_path: Path to image file
        backend: Solver backend ('astrometry.net' or future: 'local')
        **kwargs: Backend-specific options
    
    Returns:
        PlateSolveResult
    """
    if backend == "astrometry.net":
        return solve_image_astrometry_net(image_path, **kwargs)
    else:
        return PlateSolveResult(
            status="error",
            error_message=f"Unsupported plate solve backend: {backend}",
            backend=backend
        )
