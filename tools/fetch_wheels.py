"""Download the wheels the extension bundles into ghosttown/wheels/ (checksums verified) and list them in
ghosttown/blender_manifest.toml.

    python3 tools/fetch_wheels.py
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

PACKAGES = {"shapely": "2.1.2", "pillow": "11.3.0"}
PLATFORMS = (  # one wheel per Blender platform; the first match in name order has the widest reach
    re.compile(r"-cp313-cp313-macosx_\d+_\d+_arm64\.whl$"),
    re.compile(r"-cp313-cp313-macosx_\d+_\d+_x86_64\.whl$"),
    re.compile(r"-cp313-cp313-win_amd64\.whl$"),
    re.compile(r"-cp313-cp313-manylinux[^-]*x86_64\.whl$"),
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "ghosttown", "wheels")
MANIFEST = os.path.join(ROOT, "ghosttown", "blender_manifest.toml")


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _pick(files, pattern):
    names = sorted(n for n in files if pattern.search(n))
    if not names:
        sys.exit(f"no wheel matches {pattern.pattern}")
    return names[0]


def _download(info, path):
    if os.path.exists(path) and _sha256(path) == info["digests"]["sha256"]:
        print("ok ", os.path.basename(path))
        return
    with urllib.request.urlopen(info["url"], timeout=300) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != info["digests"]["sha256"]:
        sys.exit(f"checksum mismatch for {os.path.basename(path)}")
    with open(path, "wb") as f:
        f.write(data)
    print("got", os.path.basename(path))


def _write_manifest(names):
    with open(MANIFEST, encoding="utf-8") as f:
        text = f.read()
    block = "wheels = [\n" + "".join(f'  "./wheels/{n}",\n' for n in names) + "]"
    new, count = re.subn(r'wheels = \[\n(?:  "[^"\n]*",\n)*\]', block, text)
    if count != 1:
        sys.exit("couldn't find the wheels list in blender_manifest.toml")
    if new != text:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write(new)
        print("updated blender_manifest.toml")


def main():
    os.makedirs(DEST, exist_ok=True)
    names = []
    for package, version in PACKAGES.items():
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/{version}/json", timeout=60) as r:
            files = {f["filename"]: f for f in json.load(r)["urls"]}
        for pattern in PLATFORMS:
            name = _pick(files, pattern)
            _download(files[name], os.path.join(DEST, name))
            names.append(name)
    _write_manifest(names)


if __name__ == "__main__":
    main()
