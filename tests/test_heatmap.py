"""Tests for the gaze heatmap renderer."""

import numpy as np
import pytest

from eyetracker.core.heatmap import _build_density, generate_heatmap, save_heatmap


# ---------------------------------------------------------------------------
# Density map tests (pure numpy, no image I/O)
# ---------------------------------------------------------------------------

def test_density_empty_groups():
    density = _build_density([], 100, 80, 0.05)
    assert density.shape == (80, 100)
    assert density.max() == 0.0


def test_density_single_group_peak_near_point():
    groups = [{"x": 0.5, "y": 0.5, "count": 1}]
    density = _build_density(groups, 200, 200, 0.05)
    peak_y, peak_x = np.unravel_index(np.argmax(density), density.shape)
    assert abs(peak_x - 100) <= 2
    assert abs(peak_y - 100) <= 2


def test_density_count_scales_peak():
    groups_1 = [{"x": 0.5, "y": 0.5, "count": 1}]
    groups_5 = [{"x": 0.5, "y": 0.5, "count": 5}]
    d1 = _build_density(groups_1, 100, 100, 0.05)
    d5 = _build_density(groups_5, 100, 100, 0.05)
    assert pytest.approx(d5.max(), rel=1e-5) == d1.max() * 5


def test_density_multiple_groups_accumulate():
    groups = [
        {"x": 0.25, "y": 0.5, "count": 1},
        {"x": 0.75, "y": 0.5, "count": 1},
    ]
    density = _build_density(groups, 200, 200, 0.02)
    # Both blobs should be non-zero and symmetric-ish
    assert density[100, 50] > 0
    assert density[100, 150] > 0


def test_density_out_of_bounds_groups_dont_crash():
    # x/y at exactly 0 and 1 edges
    groups = [
        {"x": 0.0, "y": 0.0, "count": 3},
        {"x": 1.0, "y": 1.0, "count": 2},
    ]
    density = _build_density(groups, 100, 80, 0.05)
    assert density.max() > 0


# ---------------------------------------------------------------------------
# generate_heatmap / save_heatmap (requires a real image file)
# ---------------------------------------------------------------------------

def _make_image(tmp_path, w=200, h=150):
    """Write a solid grey PNG and return its path."""
    import cv2
    img = np.full((h, w, 3), 128, dtype=np.uint8)
    path = tmp_path / "test_img.png"
    cv2.imwrite(str(path), img)
    return path


def test_generate_heatmap_returns_correct_shape(tmp_path):
    img_path = _make_image(tmp_path)
    groups = [{"x": 0.5, "y": 0.5, "count": 10}]
    result = generate_heatmap(img_path, groups)
    assert result.shape == (150, 200, 3)
    assert result.dtype == np.uint8


def test_generate_heatmap_empty_groups_returns_original(tmp_path):
    img_path = _make_image(tmp_path)
    result = generate_heatmap(img_path, [])
    # Should equal the original image (converted to RGB)
    import cv2
    original_rgb = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)
    np.testing.assert_array_equal(result, original_rgb)


def test_generate_heatmap_hot_spot_differs_from_original(tmp_path):
    img_path = _make_image(tmp_path)
    groups = [{"x": 0.5, "y": 0.5, "count": 50}]
    result = generate_heatmap(img_path, groups)
    import cv2
    original_rgb = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)
    # At the hot spot the result should differ from original
    assert not np.array_equal(result[75, 100], original_rgb[75, 100])


def test_generate_heatmap_missing_image_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate_heatmap(tmp_path / "nonexistent.png", [])


def test_save_heatmap_writes_file(tmp_path):
    img_path = _make_image(tmp_path)
    out_path = tmp_path / "heatmap.png"
    save_heatmap(img_path, [{"x": 0.3, "y": 0.4, "count": 5}], out_path)
    assert out_path.exists()
    assert out_path.stat().st_size > 0
