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


def _replace(tag, typ, vals):
    return lambda entries: [e for e in entries if e[0] != tag] + [(tag, typ, vals)]


@pytest.mark.parametrize("edit", [
    _replace(33922, 12, [0.0, 0.0]),   # tiepoint cut short
    _replace(33550, 12, [2.0]),        # pixel scale cut short
    _replace(322, 4, [0]),             # zero tile width
])
def test_damaged_tags_are_refused_in_a_sentence(edit):
    with pytest.raises(tiff.TiffError):
        tiff.read(write_tiff(GRID, 0.0, 0.0, 1.0, 1.0, tile=16, edit=edit))


def test_tiles_left_out_of_a_sparse_file_have_no_data():
    grid = np.arange(36, dtype=float).reshape(6, 6)
    got, *_ = tiff.read(write_tiff(grid, 0.0, 0.0, 1.0, 1.0, tile=4, nodata=None, sparse=(1, 2)))
    assert np.isnan(got[:4, 4:]).all() and np.isnan(got[4:, :4]).all()
    assert np.array_equal(got[:4, :4], grid[:4, :4]) and np.array_equal(got[4:, 4:], grid[4:, 4:])


def test_a_file_with_every_tile_left_out_is_all_nodata():
    got, *_ = tiff.read(write_tiff(np.ones((6, 6)), 0.0, 0.0, 1.0, 1.0, tile=4, nodata=None, sparse=(0, 1, 2, 3)))
    assert got.shape == (6, 6) and np.isnan(got).all()
