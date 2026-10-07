import io

import numpy as np
from PIL import Image

from ghosttown_fetch import imagery
from mvt_samples import detection


def _jpeg(rgb, size=(64, 48)):
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_kinds():
    k = imagery.kind_of
    assert k("construction--structure--building") == imagery.BUILDING and k("nature--sky") == imagery.SKY
    assert k("construction--flat--road") == imagery.GROUND and k("nature--terrain") == imagery.GROUND
    assert k("object--wire-group") == imagery.THIN and k("object--support--pole") == imagery.THIN
    assert k("object--vehicle--car") == imagery.CLUTTER and k("nature--vegetation") == imagery.CLUTTER
    assert k("void--unlabeled") == imagery.UNKNOWN


def test_decode_gives_linear_light():
    img = imagery.decode_linear(_jpeg((128, 128, 128)))
    assert img.shape == (48, 64, 3) and abs(float(img.mean()) - 0.2159) < 0.01
    assert np.allclose(imagery.srgb_to_linear([0.0, 1.0]), [0.0, 1.0])


SKY = detection("nature--sky", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)])
ROAD = detection("construction--flat--road", [(0, 0.5), (1, 0.5), (1, 1), (0, 1)])
HOUSE = detection("construction--structure--building", [(0.4, 0.3), (0.6, 0.3), (0.6, 0.7), (0.4, 0.7)])


def test_labels_paint_small_regions_over_big_ones():
    lab = imagery.Labels([SKY, ROAD, HOUSE], aspect=0.75)
    kinds = lab.at(np.array([0.1, 0.5, 0.5, 0.1, 1.5]), np.array([0.1, 0.4, 0.6, 0.9, 0.5]))
    assert kinds.tolist() == [imagery.SKY, imagery.BUILDING, imagery.BUILDING, imagery.GROUND, imagery.UNKNOWN]


def test_broken_label_geometry_is_skipped():
    lab = imagery.Labels([{"value": "nature--sky", "geometry": "not base64!"}, HOUSE], aspect=0.75)
    assert lab.at(np.array([0.5]), np.array([0.5]))[0] == imagery.BUILDING


def test_road_luminance_needs_enough_road():
    img = np.full((384, 512, 3), 0.1, dtype=np.float32)
    assert abs(imagery.road_luminance(img, imagery.Labels([ROAD, HOUSE], aspect=0.75)) - 0.1) < 1e-6
    corner = detection("construction--flat--road", [(0, 0.99), (0.01, 0.99), (0.01, 1), (0, 1)])
    assert imagery.road_luminance(img, imagery.Labels([corner], aspect=0.75)) is None


def test_sample_reads_colours_at_picture_fractions():
    img = np.zeros((10, 20, 3), dtype=np.float32)
    img[2, 5] = (1, 0, 0)
    assert np.allclose(imagery.sample(img, np.array([5.5 / 20]), np.array([2.5 / 10])), [[1, 0, 0]])
