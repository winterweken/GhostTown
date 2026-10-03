"""Download the shapely wheels the extension bundles into ghosttown/wheels/ (checksums verified).

    python3 tools/fetch_wheels.py
"""
import hashlib
import json
import os
import sys
import urllib.request

VERSION = "2.1.2"
TAGS = (
    "cp313-cp313-macosx_11_0_arm64",
    "cp313-cp313-macosx_10_13_x86_64",
    "cp313-cp313-win_amd64",
    "cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64",
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "ghosttown", "wheels")


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    os.makedirs(DEST, exist_ok=True)
    with urllib.request.urlopen(f"https://pypi.org/pypi/shapely/{VERSION}/json", timeout=60) as r:
        files = {f["filename"]: f for f in json.load(r)["urls"]}
    for tag in TAGS:
        name = f"shapely-{VERSION}-{tag}.whl"
        info = files[name]
        path = os.path.join(DEST, name)
        if os.path.exists(path) and _sha256(path) == info["digests"]["sha256"]:
            print("ok ", name)
            continue
        with urllib.request.urlopen(info["url"], timeout=300) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != info["digests"]["sha256"]:
            sys.exit(f"checksum mismatch for {name}")
        with open(path, "wb") as f:
            f.write(data)
        print("got", name)


if __name__ == "__main__":
    main()
