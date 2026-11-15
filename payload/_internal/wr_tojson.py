"""Converts legacy .uasset/.umap files to UAssetAPI JSON next to them: -m wr_tojson <file> [...]"""
import sys
from pathlib import Path
def main():
    import wr, os, tools.exporter.pipeline as pl
    w, a = wr._installs(); os.environ.update(pl._env(w, a, a / "acr/Content/Paks"))
    import tools.acrmod.common as c
    for p in sys.argv[1:]:
        p = Path(p); out = p.with_suffix(".json"); c.asset_json(p, out); print(out)
