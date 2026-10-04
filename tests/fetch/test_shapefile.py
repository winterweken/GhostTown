import struct

import numpy as np
import pytest

from ghosttown_fetch import shapefile
from shapefile_samples import FIELDS, part, square, write


def test_offsets_boxes_and_rings_read_back():
    records = [part(square(0, 0, 10), 20.0), part(square(30, 0, 10), 5.0, holes=[square(33, 3, 4)])]
    shp, shx, _ = write(records)
    shapefile.check_header(shp)
    offsets = shapefile.record_offsets(shx)
    assert len(offsets) == 2 and offsets[0] == 100
    shell = np.array(records[0][0][0])
    boxes = shapefile.bounding_boxes(shp, offsets)
    assert boxes[0] == pytest.approx([shell[:, 0].min(), shell[:, 1].min(), shell[:, 0].max(), shell[:, 1].max()])
    rings = shapefile.polygon_rings(shp, offsets[1])
    assert len(rings) == 2 and np.allclose(rings[0][:-1], np.array(records[1][0][0]))


def test_holes_go_into_their_shell():
    shp, shx, _ = write([part(square(0, 0, 20), 9.0, holes=[square(5, 5, 4)])])
    poly, = shapefile.polygons_from_rings(shapefile.polygon_rings(shp, shapefile.record_offsets(shx)[0]))
    assert len(poly.interiors) == 1 and poly.is_valid


def test_several_shells_make_several_polygons():
    rings = part(square(0, 0, 10), 9.0)[0] + part(square(50, 0, 10), 9.0)[0]
    shp, shx, _ = write([(rings, part(square(0, 0, 1), 1.0)[1])])
    assert len(shapefile.polygons_from_rings(shapefile.polygon_rings(shp, shapefile.record_offsets(shx)[0]))) == 2


def test_a_hole_with_no_shell_around_it_becomes_a_shell():
    lonely = part(square(0, 0, 10), 9.0, holes=[square(100, 100, 5)])[0]
    shp, shx, _ = write([(lonely, part(square(0, 0, 1), 1.0)[1])])
    polys = shapefile.polygons_from_rings(shapefile.polygon_rings(shp, shapefile.record_offsets(shx)[0]))
    assert len(polys) == 2 and all(len(p.interiors) == 0 for p in polys)


def test_null_shapes_have_no_box_and_no_rings():
    shp, shx, _ = write([([], {"AVG_HEIGHT": 1.0}), part(square(0, 0, 10), 9.0)])
    offsets = shapefile.record_offsets(shx)
    boxes = shapefile.bounding_boxes(shp, offsets)
    assert np.isnan(boxes[0]).all() and not np.isnan(boxes[1]).any()
    assert shapefile.polygon_rings(shp, offsets[0]) == []


def test_the_table_reads_numbers_and_text():
    _, _, dbf = write([part(square(0, 0, 10), 75.85, ground=85.4071, source="Site Plan"),
                       ([], {"HEIGHT_SRC": "3D Model"})])
    table = shapefile.DBF(dbf)
    assert len(table) == 2 and [f[0] for f in table.fields] == [f[0] for f in FIELDS]
    row = table.record(0)
    assert row["HEIGHT_MSL"] - row["SURF_ELEV"] == pytest.approx(75.85, abs=1e-6)
    assert row["HEIGHT_SRC"] == "Site Plan" and row["AVG_HEIGHT"] == pytest.approx(75.85)
    assert table.record(1)["AVG_HEIGHT"] is None and table.record(1)["HEIGHT_SRC"] == "3D Model"


@pytest.mark.parametrize("damage", ["code", "type", "index"])
def test_damaged_files_are_refused(damage):
    shp, shx, _ = write([part(square(0, 0, 10), 9.0)])
    with pytest.raises(shapefile.ShapefileError):
        if damage == "code":
            shapefile.check_header(b"\0\0\0\0" + shp[4:])
        elif damage == "type":
            shapefile.check_header(shp[:32] + struct.pack("<i", 1) + shp[36:])  # points, not polygons
        else:
            shapefile.record_offsets(shx[:-3])
