"""Re-generates our ground cover and far forest of exported stages (wr_groundcover.append), without a WRCG export:
-m wr_regen_gc <slug> [...]"""
import sys

from wr import ROOT


def main():
    import wr_groundcover
    for slug in sys.argv[1:]:
        wr_groundcover.append(ROOT / "work" / "wrcg" / slug, log=lambda s, slug=slug: print(f"[{slug}] {s}", flush=True))
    return 0
