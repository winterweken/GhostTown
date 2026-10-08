"""A plain file cache: <root>/<source>/<sha1(key)>, used for max_age_days; prune() deletes what is older."""
import hashlib
import os
import tempfile
import time


class Cache:
    def __init__(self, root, *, max_age_days=30, clock=time.time):
        self.root = str(root)
        self.max_age_s = max_age_days * 86400
        self.clock = clock

    def _path(self, source, key):
        return os.path.join(self.root, source, hashlib.sha1(key.encode("utf-8")).hexdigest())

    def read(self, source, key):
        path = self._path(source, key)
        try:
            if self.clock() - os.path.getmtime(path) > self.max_age_s:
                return None
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def prune(self, source):
        """Delete the files in `source`'s folder older than max_age_days, which reads no longer use."""
        folder = os.path.join(self.root, source)
        try:
            names = os.listdir(folder)
        except OSError:
            return
        now = self.clock()
        for name in names:
            path = os.path.join(folder, name)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > self.max_age_s:
                    os.unlink(path)
            except OSError:
                pass

    def write(self, source, key, body):
        path = self._path(source, key)
        atomic_write(path, body)
        now = self.clock()
        os.utime(path, (now, now))


def atomic_write(path, data):
    """Write bytes so readers never see a half-written file."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
