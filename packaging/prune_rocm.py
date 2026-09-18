#!/usr/bin/env python3
"""Réduit une installation ROCm (roues Python) à ce dont CTranslate2 a besoin.

Une installation ROCm complète pèse ~3.7 Go, dont la quasi-totalité est soit de
l'outillage de compilation, soit des noyaux destinés à d'autres GPU. Pour
n'embarquer que l'utile dans une build « GPU », ce script supprime :

  * `_rocm_sdk_core/lib/llvm` — la chaîne de compilation LLVM/HIP. CTranslate2
    ne l'ouvre jamais à l'exécution (il n'ajoute que les dossiers `bin`).
  * les bibliothèques ROCm inutilisées (MIOpen, rocRAND, rocSPARSE, rocFFT…).
  * les noyaux Tensile (rocBLAS et hipBLASLt) des architectures non ciblées.

À CONSERVER impérativement, malgré les apparences :
  * `rocsolver` / `hipsolver`
  * `libhipblaslt` (la DLL ; seuls ses noyaux hors-cible sont supprimés)
Ce sont des dépendances de liaison de `ctranslate2.dll` : sans elles, la DLL ne
se charge plus du tout (erreur « Could not find module »).

Mesuré sur gfx1100 : 3718 Mo -> 619 Mo sur disque, 171 Mo une fois compressé.

Usage :
    python packaging/prune_rocm.py --site-packages <chemin> [--targets gfx1100,...]
    python packaging/prune_rocm.py --site-packages <chemin> --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# Familles RDNA3 (RX 7000) et RDNA3.5 (APU Strix). RDNA4 (gfx1200/gfx1201) est
# volontairement exclu par défaut : ses noyaux pèsent à eux seuls ~542 Mo et
# CTranslate2 4.7.1 y est signalé instable (OpenNMT/CTranslate2#2021).
DEFAULT_TARGETS = ("gfx1100", "gfx1101", "gfx1102", "gfx1150", "gfx1151")

# Dossiers entiers à supprimer (relatifs à site-packages).
DROP_DIRS = (
    "_rocm_sdk_core/lib/llvm",
)

# DLL inutiles à CTranslate2 (relatives à site-packages).
DROP_DLLS = (
    "_rocm_sdk_libraries_custom/bin/MIOpen.dll",
    "_rocm_sdk_libraries_custom/bin/rocrand.dll",
    "_rocm_sdk_libraries_custom/bin/hiprand.dll",
    "_rocm_sdk_libraries_custom/bin/rocsparse.dll",
    "_rocm_sdk_libraries_custom/bin/hipsparse.dll",
    "_rocm_sdk_libraries_custom/bin/rocfft.dll",
    "_rocm_sdk_libraries_custom/bin/hipfft.dll",
    "_rocm_sdk_libraries_custom/bin/hipfftw.dll",
)

# Dossiers de noyaux Tensile filtrés par architecture.
KERNEL_DIRS = (
    "_rocm_sdk_libraries_custom/bin/rocblas/library",
    "_rocm_sdk_libraries_custom/bin/hipblaslt/library",
)

_GFX_RE = re.compile(r"gfx\d{3,4}[a-z]?")


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} Mo"


def prune(site_packages: Path, targets: set[str], dry_run: bool) -> int:
    freed = 0

    def remove(path: Path, label: str) -> None:
        nonlocal freed
        if not path.exists():
            return
        size = _size(path)
        freed += size
        print(f"  - {label:<52} {_mb(size):>9}")
        if not dry_run:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    print("Dossiers d'outillage :")
    for rel in DROP_DIRS:
        remove(site_packages / rel, rel)

    print("Bibliothèques inutilisées :")
    for rel in DROP_DLLS:
        remove(site_packages / rel, Path(rel).name)

    print(f"Noyaux hors cibles {sorted(targets)} :")
    for rel in KERNEL_DIRS:
        d = site_packages / rel
        if not d.is_dir():
            continue
        victims = [
            f for f in d.rglob("*")
            if f.is_file()
            and _GFX_RE.search(f.name)
            and not any(t in f.name for t in targets)
        ]
        if not victims:
            continue
        size = sum(f.stat().st_size for f in victims)
        freed += size
        print(f"  - {rel + f' ({len(victims)} fichiers)':<52} {_mb(size):>9}")
        if not dry_run:
            for f in victims:
                f.unlink(missing_ok=True)

    return freed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-packages", required=True,
                    help="Dossier site-packages contenant _rocm_sdk_core.")
    ap.add_argument("--targets", default=",".join(DEFAULT_TARGETS),
                    help="Architectures GPU à conserver, séparées par des virgules.")
    ap.add_argument("--dry-run", action="store_true",
                    help="N'affiche que ce qui serait supprimé.")
    args = ap.parse_args()

    sp = Path(args.site_packages).resolve()
    if not (sp / "_rocm_sdk_core").is_dir():
        print(f"[!] _rocm_sdk_core introuvable dans {sp}", file=sys.stderr)
        return 2

    targets = {t.strip() for t in args.targets.split(",") if t.strip()}
    before = sum(_size(sp / p) for p in
                 ("_rocm_sdk_core", "_rocm_sdk_libraries_custom", "ctranslate2")
                 if (sp / p).exists())

    print(f"Avant : {_mb(before)}{'  (simulation)' if args.dry_run else ''}\n")
    freed = prune(sp, targets, args.dry_run)

    after = sum(_size(sp / p) for p in
                ("_rocm_sdk_core", "_rocm_sdk_libraries_custom", "ctranslate2")
                if (sp / p).exists())
    print(f"\nLibéré : {_mb(freed)}")
    print(f"Après  : {_mb(after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
