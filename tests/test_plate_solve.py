"""Tests for plate solving integration."""
from celestial_triage.ingest.plate_solve import PlateSolveResult, solve_image


def test_plate_solve_result_to_dict():
    """Test PlateSolveResult serialization."""
    result = PlateSolveResult(
        status="success",
        ra_center=123.456,
        dec_center=-45.123,
        field_width_deg=0.5,
        field_height_deg=0.5,
        orientation_deg=15.0,
        pixel_scale_arcsec=1.5,
        backend="astrometry.net",
        job_id="12345",
        error_message=None,
        metadata={"test": "data"}
    )
    
    d = result.to_dict()
    
    assert d["status"] == "success"
    assert d["ra_center"] == 123.456
    assert d["dec_center"] == -45.123
    assert d["backend"] == "astrometry.net"
    assert d["metadata"] == {"test": "data"}


def test_plate_solve_missing_api_key(tmp_path):
    """Test solve fails gracefully without API key."""
    test_image = tmp_path / "test.fits"
    test_image.write_text("mock")
    
    result = solve_image(
        image_path=test_image,
        backend="astrometry.net",
        api_key=""  # Explicitly empty
    )
    
    assert result.status == "error"
    assert "API key required" in result.error_message
    assert result.backend == "astrometry.net"


def test_plate_solve_missing_file():
    """Test solve fails gracefully for missing file."""
    result = solve_image(
        image_path="/nonexistent/file.fits",
        backend="astrometry.net",
        api_key="fake_key"
    )
    
    assert result.status == "error"
    assert "not found" in result.error_message


def test_plate_solve_unsupported_backend(tmp_path):
    """Test solve fails for unsupported backend."""
    test_image = tmp_path / "test.fits"
    test_image.write_text("mock")
    
    result = solve_image(
        image_path=test_image,
        backend="unsupported_solver",
        api_key="fake"
    )
    
    assert result.status == "error"
    assert "Unsupported" in result.error_message
