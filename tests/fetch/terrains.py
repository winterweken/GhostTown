import numpy as np
import shapely


class Ramp:
    """z = 0.1·x: the ground rises 1 m every 10 m eastwards."""
    source = "test"
    ground_at_centre_m = 80.0
    cell_m = 1.0

    def z(self, xs, ys):
        return 0.1 * np.asarray(xs, dtype=float)

    def min_under(self, polygon):
        return 0.1 * float(shapely.get_coordinates(polygon)[:, 0].min())
