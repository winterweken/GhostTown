"""Ground heights in local metres. Milestone 1 has flat ground; NRCan and Terrarium come in milestone 2."""
import numpy as np


class FlatTerrain:
    source = "flat"
    ground_at_centre_m = None
    cell_m = None

    def z(self, xs, ys):
        return np.zeros(np.shape(xs), dtype=float)

    def min_under(self, polygon):
        return 0.0
