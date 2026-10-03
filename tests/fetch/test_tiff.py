import gzip
from pathlib import Path

import numpy as np
import pytest

from ghosttown_fetch import tiff
from tiff_samples import write_tiff

FIX = Path(__file__).parent / "fixtures"
GRID = np.arange(12, dtype=float).reshape(3, 4) + 100.0


@pytest.mark.parametrize("big_endian", [False, True])
@pytest.mark.parametrize("tile", [None, 16])
def test_reads_values_and_position(big_endian, tile):
    grid, x0, y0, dx, dy = tiff.read(write_tiff(GRID, -8836852.0, 5411587.0, 2.0, 2.01, big_endian=big_endian, tile=tile))
    assert grid.shape == (3, 4) and np.array_equal(grid, GRID)
    assert (x0, y0, dx, dy) == (-8836852.0, 5411587.0, 2.0, 2.01)


def test_nodata_becomes_nan():
    g = GRID.copy()
    g[1, 2] = -32767
    grid, *_ = tiff.read(write_tiff(g, 0.0, 0.0, 1.0, 1.0))
    assert np.isnan(grid[1, 2]) and int(np.isnan(grid).sum()) == 1


def test_a_tiepoint_on_another_pixel_is_moved_to_the_corner():
    _, x0, y0, _, _ = tiff.read(write_tiff(GRID, 100.0, 200.0, 2.0, 2.0, tie_pixel=(1, 1)))
    assert (x0, y0) == (98.0, 202.0)


@pytest.mark.parametrize("data, words", [(b"not a tiff", "isn't a TIFF"), (b"II*\x00\x00\x00\x00\x00", "cut short")])
def test_bad_files_are_refused_in_a_sentence(data, words):
    with pytest.raises(tiff.TiffError, match=words):
        tiff.read(data)


def test_compressed_files_are_refused():
    with pytest.raises(tiff.TiffError, match="Compressed"):
        tiff.read(write_tiff(GRID, 0.0, 0.0, 1.0, 1.0, compression=5))


def test_real_nrcan_tile_at_bay_street():
    grid, x0, y0, dx, dy = tiff.read(gzip.decompress((FIX / "bay" / "nrcan_dtm.tif.gz").read_bytes()))
    assert grid.shape == (200, 201) and (x0, y0, dx, dy) == (-8836852.0, 5411587.0, 2.0, 2.01)
    assert not np.isnan(grid).any() and abs(grid[100, 100] - 84.73) < 0.05


def test_real_placeholder_outside_canada_is_one_pixel():
    grid, *_ = tiff.read(gzip.decompress((FIX / "london" / "nrcan_dtm.tif.gz").read_bytes()))
    assert grid.shape == (1, 1)
