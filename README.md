# HarmoHOI Project Page (Local)

Local project homepage for **HarmoHOI: Harmonizing Appearance and 3D Motion for Multi-view Hand-Object Interaction Synthesis** (SIGGRAPH Asia 2026, Manuscript ID 1048).

## Open

```bash
open index.html
```

Or serve locally:

```bash
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Rebuild from PPT

```bash
python3 build_site.py
```

This extracts demo videos from `harmohoi_260721.pptx`, copies paper figures/PDF, and regenerates `index.html`.

## Layout notes

- Comparison video columns are ordered left→right by slide position as: Source / DaS / SynCamMaster / SV4D 2.0 / Ours / Viewport. Please spot-check against the PPT if any label looks swapped.
- Videos use `controls` (click to play) instead of autoplay, to keep local browsing responsive with ~180 clips.
- `Comparison of 3D Motions` clips are center-padded to **1920×1032** during `build_site.py`.
- Large demo videos remain in `static/videos/` (~485MB). For GitHub Pages, consider [Git LFS](https://git-lfs.github.com/) if the repo feels slow to clone.
