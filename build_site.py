#!/usr/bin/env python3
"""Build HarmoHOI local project page from PPT + paper assets."""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
PPTX = Path("/Users/danglingwei/files/siggraphasia26_rebuttal/harmohoi_260721.pptx")
PAPER_DIR = Path("/Users/danglingwei/files/siggraphasia26_rebuttal/codes/siggraph_asia_26_arxiv")
CODANCE = Path(
    "/Users/danglingwei/files/赵恒爽SiggraphAsia26正文及补充材料范本/"
    "papers_2196s2_files/CoDance_supp/CoDance_demo"
)

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def parse_rels(z: zipfile.ZipFile, slide_idx: int) -> dict[str, str]:
    rel_path = f"ppt/slides/_rels/slide{slide_idx}.xml.rels"
    mapping: dict[str, str] = {}
    if rel_path not in z.namelist():
        return mapping
    root = ET.fromstring(z.read(rel_path))
    for rel in root:
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rid and target:
            mapping[rid] = os.path.basename(target.replace("\\", "/"))
    return mapping


def get_box(sp_pr):
    if sp_pr is None:
        return None
    xfrm = sp_pr.find("a:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return {
        "x": int(off.get("x")),
        "y": int(off.get("y")),
        "cx": int(ext.get("cx")),
        "cy": int(ext.get("cy")),
    }


def slide_videos(z: zipfile.ZipFile, slide_idx: int):
    rels = parse_rels(z, slide_idx)
    root = ET.fromstring(z.read(f"ppt/slides/slide{slide_idx}.xml"))
    videos = []
    for pic in root.iter("{http://schemas.openxmlformats.org/presentationml/2006/main}pic"):
        blip = pic.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
        nv_pr = pic.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}nvPr")
        sp_pr = pic.find("{http://schemas.openxmlformats.org/presentationml/2006/main}spPr")
        box = get_box(sp_pr)
        rid = None
        if blip is not None:
            rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        video_rid = None
        if nv_pr is not None:
            for el in nv_pr.iter():
                if el.tag.endswith("}videoFile") or el.tag.endswith("}media"):
                    video_rid = (
                        el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link")
                        or el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                        or video_rid
                    )
        video_name = rels.get(video_rid) if video_rid else None
        poster = rels.get(rid) if rid else None
        if video_name and video_name.endswith(".mp4"):
            videos.append({"video": video_name, "poster": poster, "box": box})
    videos.sort(key=lambda e: ((e["box"] or {}).get("y", 0), (e["box"] or {}).get("x", 0)))
    return videos


def extract_member(z: zipfile.ZipFile, name: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return
    with z.open(f"ppt/media/{name}") as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)


def normalize_motion_video(src: Path, dest: Path, width: int = 1920, height: int = 1032):
    """Center-pad and resize motion comparison clips to a unified canvas."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(tmp),
        ],
        check=True,
    )
    tmp.replace(dest)


def normalize_comparison_motion_videos(comp_dir: Path):
    import tempfile

    for mp4 in sorted(comp_dir.glob("*.mp4")):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_raw:
            raw_path = Path(tmp_raw.name)
        try:
            shutil.copy2(mp4, raw_path)
            normalize_motion_video(raw_path, mp4)
        finally:
            raw_path.unlink(missing_ok=True)


def copy_tree_files(src_dir: Path, dst_dir: Path, names: list[str]):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        s = src_dir / name
        d = dst_dir / name
        if s.exists():
            shutil.copy2(s, d)


def cluster_rows(videos, y_tol=400000):
    rows = []
    for v in videos:
        y = v["box"]["y"]
        placed = False
        for row in rows:
            if abs(row[0]["box"]["y"] - y) <= y_tol:
                row.append(v)
                placed = True
                break
        if not placed:
            rows.append([v])
    for row in rows:
        row.sort(key=lambda e: e["box"]["x"])
    return rows


def setup_static():
    copy_tree_files(CODANCE / "static/css", ROOT / "static/css", ["bulma.min.css"])

    img = ROOT / "static/images"
    img.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PAPER_DIR / "fig/teaser2.png", img / "teaser.png")
    shutil.copy2(PAPER_DIR / "fig/hybrid_data.png", img / "hybrid_data.png")
    with zipfile.ZipFile(PPTX) as z:
        extract_member(z, "image31.png", img / "method.png")


def build_media_manifest(z: zipfile.ZipFile):
    """Return structured manifest and extract files with semantic names."""
    videos_root = ROOT / "static/videos"
    videos_root.mkdir(parents=True, exist_ok=True)
    manifest = {}

    # Teaser: large cover video on slide 1
    extract_member(z, "media1.mp4", videos_root / "teaser.mp4")
    manifest["teaser"] = "static/videos/teaser.mp4"

    # 3.1 Multi-view synchronized HOI — wide showcase clips
    mv_dir = videos_root / "multiview_sync"
    cases_31 = [
        ("case1", "media39.mp4", "Use spatula to scrape the bowl."),
        ("case2", "media40.mp4", "Use spatula to scrape the pan."),
        ("case3", "media42.mp4", "Use brush to scrape the pot."),
        ("case4", "media43.mp4", "Use shovel to shovel the plate."),
    ]
    # also keep 3-view strips for case1/2 from top row
    view_strips = {
        "case1_views": ["media36.mp4", "media37.mp4", "media38.mp4"],
        "case2_views": ["media34.mp4", "media35.mp4", "media33.mp4"],
        "case3_views": ["media47.mp4", "media48.mp4", "media49.mp4"],
        "case4_views": ["media44.mp4", "media45.mp4", "media46.mp4"],
    }
    manifest["multiview_sync"] = []
    for key, media, caption in cases_31:
        dest = mv_dir / f"{key}.mp4"
        extract_member(z, media, dest)
        views = []
        for i, vm in enumerate(view_strips[f"{key}_views"], 1):
            vdest = mv_dir / f"{key}_v{i}.mp4"
            extract_member(z, vm, vdest)
            views.append(f"static/videos/multiview_sync/{key}_v{i}.mp4")
        manifest["multiview_sync"].append(
            {
                "id": key,
                "caption": caption,
                "main": f"static/videos/multiview_sync/{key}.mp4",
                "views": views,
            }
        )

    # 3.2 Unseen generalization
    unseen_dir = videos_root / "unseen"
    unseen_cases = [
        ("case1", "media63.mp4", "Use ruler to measure the wheel."),
        ("case2", "media77.mp4", "Use hammer to hit the gun."),
    ]
    # view grids from slides 7/8 (left 3x4-ish)
    for slide_idx, case_id in [(7, "case1"), (8, "case2")]:
        vids = [v for v in slide_videos(z, slide_idx) if v["video"] not in ("media63.mp4", "media77.mp4")]
        # exclude the large right composite by width
        small = [v for v in vids if v["box"]["cx"] < 3000000]
        small = sorted(small, key=lambda e: (e["box"]["y"], e["box"]["x"]))
        keep_idx = [1, 2, 3, 10, 11, 12]
        for i, v in enumerate(small, 1):
            if i not in keep_idx:
                continue
            extract_member(z, v["video"], unseen_dir / f"{case_id}_v{i}.mp4")
    manifest["unseen"] = []
    for key, media, caption in unseen_cases:
        extract_member(z, media, unseen_dir / f"{key}.mp4")
        views = sorted((unseen_dir).glob(f"{key}_v*.mp4"))
        manifest["unseen"].append(
            {
                "id": key,
                "caption": caption,
                "main": f"static/videos/unseen/{key}.mp4",
                "views": [f"static/videos/unseen/{p.name}" for p in views],
            }
        )

    # 3.3 In-the-wild single-view: RGB / Motion / 3D track per case
    wild_s = videos_root / "wild_single"
    # slide 9: cases 1-5, slide 10: cases 6-10
    wild_single = []
    captions_9 = [
        "Make a pizza.",
        "Mix white liquid with mixer.",
        "Remove the blue-silver smart device.",
        "Chop the chili peppers.",
        "Break the cookies into pieces.",
    ]
    captions_10 = [
        "Unfasten the ribbon on the cake.",
        "Making fruit and vegetable juice.",
        "Cutting vegetables on the chopping board.",
        "Have a glass of champagne.",
        "Arrange the wooden blocks.",
    ]
    for slide_idx, captions, start in [(9, captions_9, 1), (10, captions_10, 6)]:
        rows = cluster_rows(slide_videos(z, slide_idx))
        # expect 3 rows: RGB, Motion, 3D
        if len(rows) < 3:
            continue
        rgb, motion, track = rows[0], rows[1], rows[2]
        # ensure 5 columns
        n = min(len(rgb), len(motion), len(track), 5)
        for i in range(n):
            case_id = f"case{start + i}"
            for kind, row in [("rgb", rgb), ("motion", motion), ("track", track)]:
                extract_member(z, row[i]["video"], wild_s / f"{case_id}_{kind}.mp4")
            wild_single.append(
                {
                    "id": case_id,
                    "caption": captions[i],
                    "rgb": f"static/videos/wild_single/{case_id}_rgb.mp4",
                    "motion": f"static/videos/wild_single/{case_id}_motion.mp4",
                    "track": f"static/videos/wild_single/{case_id}_track.mp4",
                }
            )
    manifest["wild_single"] = wild_single

    # 3.4 In-the-wild multi-view consistency
    wild_m = videos_root / "wild_multiview"
    prompts = {
        11: "Close-up of hands in a green apron slicing red chilies on a dark wooden board.",
        12: "A person making dumplings, right hand holding a spoon, lightly tapping the filling on the left palm.",
        13: "A person rolling dough on a board, pushing and pulling a rolling pin back and forth.",
        14: "A person slicing green zucchini on a cutting board with a kitchen knife.",
        15: "Asian woman walking barefoot on a sun-drenched tropical beach, photorealistic side-tracking shot.",
    }
    large_map = {
        11: "media117.mp4",
        12: "media124.mp4",
        13: "media131.mp4",
        14: "media138.mp4",
        15: "media145.mp4",
    }
    manifest["wild_multiview"] = []
    for slide_idx in range(11, 16):
        case_id = f"case{slide_idx - 10}"
        extract_member(z, large_map[slide_idx], wild_m / f"{case_id}.mp4")
        # six small multi-view clips (left grid)
        small = [v for v in slide_videos(z, slide_idx) if v["box"]["cx"] < 4000000]
        for i, v in enumerate(sorted(small, key=lambda e: (e["box"]["y"], e["box"]["x"])), 1):
            extract_member(z, v["video"], wild_m / f"{case_id}_v{i}.mp4")
        views = sorted(wild_m.glob(f"{case_id}_v*.mp4"))
        manifest["wild_multiview"].append(
            {
                "id": case_id,
                "caption": prompts[slide_idx],
                "main": f"static/videos/wild_multiview/{case_id}.mp4",
                "views": [f"static/videos/wild_multiview/{p.name}" for p in views],
            }
        )

    # 4.1 Video comparison grids
    comp_v = videos_root / "comparison_video"
    col_labels = ["Source View", "View 2", "View 3", "View 4", "View 5", "View 6"]
    row_labels = ["DaS", "SynCamMaster", "SV4D 2.0", "Ours"]
    manifest["comparison_video"] = []
    for slide_idx, case_i in [(16, 1), (17, 2), (18, 3)]:
        rows = cluster_rows(slide_videos(z, slide_idx))
        case = {"id": f"case{case_i}", "rows": [], "labels": col_labels, "row_labels": row_labels}
        for r_i, row in enumerate(rows):
            row_files = []
            for c_i, v in enumerate(row[:6]):
                name = f"case{case_i}_r{r_i}_c{c_i}.mp4"
                extract_member(z, v["video"], comp_v / name)
                row_files.append(f"static/videos/comparison_video/{name}")
            case["rows"].append(row_files)
        manifest["comparison_video"].append(case)

    # 4.2 Motion comparison 2x2
    comp_m = videos_root / "comparison_motion"
    motion_labels = ["Geo4D", "Depth Anything 3", "GeoCrafter", "Ours"]
    motion_caps = {
        19: "Pour water from the kettle into the bowl.",
        20: "Use a brush to scrub the pot.",
        21: "Scrape the plate with a spatula.",
    }
    manifest["comparison_motion"] = []
    for slide_idx, case_i in [(19, 1), (20, 2), (21, 3)]:
        vids = slide_videos(z, slide_idx)
        files = []
        for i, v in enumerate(vids[:4]):
            name = f"case{case_i}_{i}.mp4"
            extract_member(z, v["video"], comp_m / name)
            files.append(f"static/videos/comparison_motion/{name}")
        manifest["comparison_motion"].append(
            {
                "id": f"case{case_i}",
                "caption": motion_caps[slide_idx],
                "labels": motion_labels,
                "videos": files,
            }
        )

    return manifest


def video_tag(src: str, extra_class: str = "", controls: bool = True) -> str:
    attrs = 'playsinline muted loop preload="metadata"'
    if controls:
        attrs += " controls"
    cls = f' class="{extra_class}"' if extra_class else ""
    return f'<video{cls} {attrs}><source src="{src}" type="video/mp4"></video>'


def render_html(manifest: dict) -> str:
    abstract = (
        "Hand-Object Interaction (HOI) synthesis is a cornerstone for animation production and embodied AI. "
        "Despite the strong priors of video foundation models, multi-view consistent HOI synthesis remains "
        "challenging due to complex hand motions and occlusions. We present <b>HarmoHOI</b>, a unified "
        "diffusion framework that jointly and harmoniously generates synchronized multi-view HOI videos and "
        "globally aligned 3D point tracks. Our core insight is that robust multi-view consistency fundamentally "
        "requires globally aligned 3D geometry and motion. To this end, we propose a Mixture of Multi-view "
        "Diffusion Transformer that co-models RGB videos and 3D point tracks. By representing point tracks as "
        "pseudo-videos, we align 3D geometric signals with the 2D latent space of foundation models, thereby "
        "minimizing the domain gap and easing adaptation of priors. To further ensure geometry consistency, we "
        "introduce Global Motion Aligning Diffusion, which refines coarse point tracks into metric-scale, "
        "globally aligned 3D trajectories. HarmoHOI enables on-the-fly co-evolution of 2D appearance and 3D "
        "motion during denoising. To overcome the scarcity of multi-view HOI data, we employ a hybrid data "
        "curriculum learning strategy that successfully transfers generic priors from single-view data to "
        "synchronized multi-view generation. Experimental results show that HarmoHOI achieves state-of-the-art "
        "performance in visual quality, motion plausibility, and multi-view geometric consistency."
    )

    authors = [
        ("Lingwei Dang", "South China University of Technology"),
        ("Juntong Li", "South China University of Technology"),
        ("Zonghan Li", "South China University of Technology"),
        ("Hongwen Zhang", "Beijing Normal University"),
        ("Liang An", "Tsinghua University"),
        ("Wei Min", "Shadow AI"),
        ("Yebin Liu", "Tsinghua University"),
        ("Qingyao Wu†", "South China University of Technology"),
    ]
    author_html = " ".join(
        f'<span class="author-block">{name}<sup>{i+1}</sup>,</span>' if i < len(authors) - 1
        else f'<span class="author-block">{name}<sup>{i+1}</sup></span>'
        for i, (name, _) in enumerate(authors)
    )
    # unique affiliations with numbers
    aff_map = {}
    aff_list = []
    for name, aff in authors:
        if aff not in aff_map:
            aff_map[aff] = len(aff_list) + 1
            aff_list.append(aff)
    # rebuild with correct superscripts
    author_html = []
    for i, (name, aff) in enumerate(authors):
        comma = "," if i < len(authors) - 1 else ""
        author_html.append(f'<span class="author-block">{name}<sup>{aff_map[aff]}</sup>{comma}</span>')
    author_html = "\n            ".join(author_html)
    aff_html = "<br>".join(f"<span class=\"author-block\"><sup>{i}</sup>{a}</span>" for i, a in enumerate(aff_list, 1))

    # sections
    parts = []

    # multiview sync
    mv_items = []
    for case in manifest["multiview_sync"]:
        views = "".join(f'<div class="view-cell">{video_tag(v, "thumb")}</div>' for v in case["views"])
        mv_items.append(
            f"""
        <div class="demo-card">
          <h3 class="subtitle is-5">{case['id'].replace('case','Case ').title()}: {case['caption']}</h3>
          <div class="view-row">{views}</div>
          <div class="main-video">{video_tag(case['main'], "wide")}</div>
        </div>"""
        )
    parts.append(("Multi-view Synchronized HOI Appearance & Geometry", "".join(mv_items),
                  "Synchronized multi-view HOI videos with jointly generated 3D motion."))

    # unseen
    un_items = []
    for case in manifest["unseen"]:
        views = "".join(f'<div class="view-cell">{video_tag(v, "thumb")}</div>' for v in case["views"][:6])
        un_items.append(
            f"""
        <div class="demo-card">
          <h3 class="subtitle is-5">{case['id'].replace('case','Case ').title()}: {case['caption']}</h3>
          <div class="view-row cols-3">{views}</div>
          <div class="main-video">{video_tag(case['main'], "wide")}</div>
        </div>"""
        )
    parts.append(("Unseen Generalization for Multi-view HOI", "".join(un_items),
                  "Generalization to unseen object–tool combinations."))

    # wild single
    ws_items = []
    for case in manifest["wild_single"]:
        ws_items.append(
            f"""
        <div class="demo-card">
          <h3 class="subtitle is-5">{case['id'].replace('case','Case ').title()}: {case['caption']}</h3>
          <div class="triple-grid">
            <div><div class="label">RGB Video</div><div class="media-frame">{video_tag(case['rgb'], "cell")}</div></div>
            <div><div class="label">Motion Video</div><div class="media-frame">{video_tag(case['motion'], "cell")}</div></div>
            <div><div class="label">3D Points Track</div><div class="media-frame">{video_tag(case['track'], "cell")}</div></div>
          </div>
        </div>"""
        )
    parts.append(("In-the-wild Single-view Appearance & Geometry", "".join(ws_items),
                  "Joint appearance and geometry on diverse in-the-wild single-view HOI videos."))

    # wild multiview
    wm_items = []
    for case in manifest["wild_multiview"]:
        views = "".join(f'<div class="view-cell">{video_tag(v, "thumb")}</div>' for v in case["views"])
        wm_items.append(
            f"""
        <div class="demo-card">
          <h3 class="subtitle is-5">{case['id'].replace('case','Case ').title()}</h3>
          <p class="prompt">{case['caption']}</p>
          <div class="view-row cols-3">{views}</div>
          <div class="main-video">{video_tag(case['main'], "wide")}</div>
        </div>"""
        )
    parts.append(("In-the-wild Multi-view Appearance Consistency", "".join(wm_items),
                  "Multi-view consistent generation from in-the-wild prompts."))

    # comparison video
    cv_items = []
    for case in manifest["comparison_video"]:
        labels = "".join(f'<div class="label">{lb}</div>' for lb in case["labels"])
        row_labels = case.get("row_labels", ["DaS", "SynCamMaster", "SV4D 2.0", "Ours"])
        rows_html = []
        for r_i, row in enumerate(case["rows"]):
            cells = "".join(
                f'<div class="media-frame">{video_tag(v, "cell")}</div>' for v in row
            )
            rname = row_labels[r_i] if r_i < len(row_labels) else f"Row {r_i+1}"
            rows_html.append(
                f'<div class="comp-row-wrap"><div class="row-label">{rname}</div>'
                f'<div class="comp-row">{cells}</div></div>'
            )
        cv_items.append(
            f"""
        <div class="demo-card">
          <h3 class="subtitle is-5">{case['id'].replace('case','Case ').title()}</h3>
          <div class="comp-grid">
            <div class="comp-corner"></div>
            <div class="comp-labels cols-6">{labels}</div>
            {''.join(rows_html)}
          </div>
        </div>"""
        )
    parts.append(("Comparison of Novel-view Videos", "".join(cv_items),
                  "Each case is a 4×6 grid: rows are methods (DaS / SynCamMaster / SV4D 2.0 / Ours); columns are Source View and View 2–6."))

    # comparison motion
    cm_items = []
    for case in manifest["comparison_motion"]:
        cells = []
        for lb, v in zip(case["labels"], case["videos"]):
            cells.append(f'<div><div class="label">{lb}</div><div class="media-frame">{video_tag(v, "cell")}</div></div>')
        cm_items.append(
            f"""
        <div class="demo-card">
          <h3 class="subtitle is-5">{case['id'].replace('case','Case ').title()}: {case['caption']}</h3>
          <div class="quad-grid">{''.join(cells)}</div>
        </div>"""
        )
    parts.append(("Comparison of 3D Motions", "".join(cm_items),
                  "Comparison against Geo4D, Depth Anything 3, and GeoCrafter."))

    sections_html = []
    for i, (title, body, desc) in enumerate(parts):
        bg = "is-light" if i % 2 == 0 else ""
        sections_html.append(
            f"""
  <section class="section hero {bg}" id="sec-{i}">
    <div class="hero-body">
      <div class="container is-max-desktop">
        <h2 class="title is-3 has-text-centered">{title}</h2>
        <p class="subtitle is-6 has-text-centered section-desc">{desc}</p>
        {body}
      </div>
    </div>
  </section>"""
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta property="og:title" content="HarmoHOI: Harmonizing Appearance and 3D Motion for Multi-view Hand-Object Interaction Synthesis" />
  <title>HarmoHOI</title>
  <link rel="icon" type="image/png" href="static/images/favicon.png">
  <link rel="apple-touch-icon" href="static/images/logo.png">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="static/css/bulma.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/jpswalsh/academicons@1/css/academicons.min.css">
  <link rel="stylesheet" href="static/css/index.css">
</head>
<body>

  <section class="hero banner">
    <div class="hero-body">
      <div class="container is-max-desktop">
        <div class="columns is-centered">
          <div class="column has-text-centered">
            <h1 class="title is-1 publication-title">
              <img class="brand-mark" src="static/images/logo.png" alt="HarmoHOI icon"/>
              <span class="brand">HarmoHOI</span>
            </h1>
            <h2 class="title is-2">
              Harmonizing Appearance and 3D Motion for Multi-view Hand-Object Interaction Synthesis
            </h2>
            <div class="is-size-5 publication-authors">
              {author_html}
            </div>
            <div class="is-size-6 publication-authors affiliations">
              {aff_html}
            </div>
            <div class="is-size-6 publication-venue">
              Arxiv preprint, 2026
            </div>
            <div class="publication-links">
              <span class="link-block">
                <a href="https://arxiv.org/abs/2607.17097" class="external-link button is-normal is-rounded is-dark">
                  <span class="icon"><i class="fas fa-file-pdf"></i></span>
                  <span>Paper</span>
                </a>
              </span>
              <span class="link-block">
                <a href="https://droliven.github.io/me/" class="external-link button is-normal is-rounded is-dark">
                  <span class="icon"><i class="fas fa-home"></i></span>
                  <span>Home</span>
                </a>
              </span>
              <span class="link-block">
                <a href="https://droliven.github.io/HarmoHOI_project" class="external-link button is-normal is-rounded is-dark">
                  <span class="icon"><i class="fas fa-code"></i></span>
                  <span>Codes</span>
                </a>
              </span>
            </div>
            <p class="is-size-7 note">† Corresponding author</p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="hero teaser">
    <div class="hero-body">
      <div class="container is-max-desktop">
        <img src="static/images/teaser.png" alt="HarmoHOI teaser" class="teaser-img"/>
      </div>
    </div>
  </section>

  <section class="hero teaser">
    <div class="hero-body">
      <div class="container is-max-desktop">
        {video_tag(manifest['teaser'], 'teaser-video')}
        <p class="has-text-centered is-size-6 teaser-cap">
          HarmoHOI jointly synthesizes synchronized multi-view HOI videos and globally aligned 3D point tracks.
        </p>
      </div>
    </div>
  </section>

  <section class="section hero is-light">
    <div class="hero-body">
      <div class="container is-max-desktop has-text-centered">
        <h2 class="title is-3">Abstract</h2>
        <div class="content has-text-justified">
          <p>{abstract}</p>
        </div>
      </div>
    </div>
  </section>

  <section class="section hero" id="introduction">
    <div class="hero-body">
      <div class="container is-max-desktop has-text-centered">
        <h2 class="title is-3">Introduction</h2>
        <div class="content has-text-justified">
          <p>
            Video foundation models such as <b>Seedance 2.0</b> and <b>WAN 2.7</b> provide strong visual priors for
            hand–object interaction (HOI) synthesis. In practice, however, directly applying them to HOI still falls short:
            they often produce <b>hallucinated contacts</b>, <b>poor instruction adherence</b>, <b>geometric distortion</b>,
            and <b>unrealistic floating motions</b>. More critically, most remain single-view generators and lack explicit,
            globally aligned 3D geometry–motion awareness, which limits synchronized multi-view consistency under heavy occlusion.
          </p>
        </div>
        <div class="intro-fail-grid">
          <div class="intro-fail-card">
            <h3>Seedance 2.0</h3>
            <video playsinline muted loop preload="metadata" controls poster="static/images/intro_seedance_poster.png">
              <source src="static/videos/intro/seedance.mp4" type="video/mp4">
            </video>
            <div class="fail-tags">
              <span class="fail-tag">Hallucination</span>
              <span class="fail-tag">Poor instruction adherence</span>
            </div>
          </div>
          <div class="intro-fail-card">
            <h3>WAN 2.7</h3>
            <video playsinline muted loop preload="metadata" controls poster="static/images/intro_wan_poster.png">
              <source src="static/videos/intro/wan.mp4" type="video/mp4">
            </video>
            <div class="fail-tags">
              <span class="fail-tag">Distortion</span>
              <span class="fail-tag">Unrealistic floating motion</span>
            </div>
          </div>
        </div>
        <p class="is-size-7 has-text-centered" style="color:#666; margin-bottom:1rem;">
          Prompt: “A person is arranging pieces of wood to form a frame-like structure on a wooden workbench.”
        </p>
        <img src="static/images/intro_schematic.png" alt="Comparison of novel-view / multi-view video synthesis methods" class="method-img"/>
        <p class="fig-caption">
          <b>Comparison of novel-view / multi-view video synthesis methods.</b>
          Existing paradigms either generate views sequentially or lack joint 3D motion modeling.
          Our core insight: robust synchronized multi-view consistency requires
          <b>globally aligned 3D geometry &amp; motion awareness</b>.
        </p>
        <div class="insight-box content">
          <p style="margin:0;">
            <b>HarmoHOI</b> addresses these failure modes by jointly diffusing multi-view RGB videos and
            globally aligned 3D point tracks, enabling appearance and geometry to co-evolve during denoising.
          </p>
        </div>
      </div>
    </div>
  </section>

  <section class="section hero is-light">
    <div class="hero-body">
      <div class="container is-max-desktop has-text-centered">
        <h2 class="title is-3">Method Overview</h2>
        <img src="static/images/method.png" alt="HarmoHOI method" class="method-img"/>
        <div class="content has-text-justified">
          <p>
            HarmoHOI is the first synchronized multi-view joint diffusion framework for HOI video and motion synthesis.
            It integrates a <b>Mixture of Multi-view DiT</b> for joint appearance–motion modeling with
            <b>Global Motion Aligning Diffusion</b> for 3D trajectory refinement, forming a mutual enhancement loop.
            A hybrid data and progressive curriculum learning strategy transfers single-view priors to multi-view generation.
          </p>
        </div>
        <img src="static/images/hybrid_data.png" alt="Hybrid data curriculum" class="method-img secondary"/>
        <p class="fig-caption">
          <b>Hybrid-data progressive curriculum learning.</b>
          HarmoHOI is trained in three stages of increasing geometric fidelity and multi-view consistency:
          (1) in-the-wild single-view HOI videos with estimated depth for appearance–geometry correspondence;
          (2) multi-view videos rendered in Unreal Engine for cross-view appearance consistency;
          (3) lab-captured multi-view HOI videos with 3D motion tracks for joint appearance–geometry learning.
          This curriculum preserves pretrained video priors while progressively injecting multi-view geometric awareness.
        </p>
      </div>
    </div>
  </section>

  <div id="demos"></div>
  {''.join(sections_html)}

  <section class="section hero is-light" id="bibtex">
    <div class="hero-body">
      <div class="container is-max-desktop">
        <h2 class="title is-3 has-text-centered">BibTeX</h2>
        <p class="subtitle is-6 has-text-centered section-desc">
          Citation for <a href="https://arxiv.org/abs/2607.17097" target="_blank" rel="noopener">arXiv:2607.17097</a>
        </p>
        <div class="bibtex-card">
          <button id="copy-bibtex" class="button is-small is-rounded is-dark bibtex-copy" type="button">
            <span class="icon"><i class="fas fa-copy"></i></span>
            <span>Copy BibTeX</span>
          </button>
          <pre id="bibtex-code" class="bibtex-code"><code>@misc{{dang2026harmohoiharmonizingappearance3d,
      title={{HarmoHOI: Harmonizing Appearance and 3D Motion for Multi-view Hand-Object Interaction Synthesis}},
      author={{Lingwei Dang and Juntong Li and Zonghan Li and Hongwen Zhang and Liang An and Wei Min and Yebin Liu and Qingyao Wu}},
      year={{2026}},
      eprint={{2607.17097}},
      archivePrefix={{arXiv}},
      primaryClass={{cs.CV}},
      url={{https://arxiv.org/abs/2607.17097}},
}}</code></pre>
        </div>
      </div>
    </div>
  </section>

  <footer class="footer">
    <div class="container">
      <div class="content has-text-centered">
        <p>
          <b>HarmoHOI</b> project page (local demo build from supplementary PPT materials).<br>
          Page layout adapted from academic project-page templates (Bulma).
        </p>
      </div>
    </div>
  </footer>

  <script>
    // Copy BibTeX to clipboard
    (function () {{
      const btn = document.getElementById('copy-bibtex');
      const code = document.getElementById('bibtex-code');
      if (!btn || !code) return;
      btn.addEventListener('click', async () => {{
        const text = code.textContent;
        try {{
          await navigator.clipboard.writeText(text);
          const label = btn.querySelector('span:last-child');
          const old = label.textContent;
          label.textContent = 'Copied!';
          setTimeout(() => {{ label.textContent = old; }}, 2000);
        }} catch (err) {{
          const ta = document.createElement('textarea');
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
        }}
      }});
    }})();

    // Pause offscreen videos to keep local browsing responsive
    (function () {{
      const videos = Array.from(document.querySelectorAll('video'));
      if (!('IntersectionObserver' in window)) return;
      const io = new IntersectionObserver((entries) => {{
        entries.forEach((e) => {{
          const v = e.target;
          if (e.isIntersecting) {{
            // do not autoplay; user controls playback
          }} else if (!v.paused) {{
            v.pause();
          }}
        }});
      }}, {{ rootMargin: '200px' }});
      videos.forEach((v) => io.observe(v));
    }})();
  </script>
</body>
</html>
"""


def write_css():
    """Keep CSS editable in static/css/index.css; only seed if missing."""
    css_path = ROOT / "static/css/index.css"
    if css_path.exists() and css_path.stat().st_size > 0:
        return
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text("/* run once then edit static/css/index.css */\n", encoding="utf-8")


def main():
    print("Setting up static assets...")
    setup_static()
    write_css()
    print("Extracting videos from PPT (this may take a while)...")
    with zipfile.ZipFile(PPTX) as z:
        manifest = build_media_manifest(z)
    comp_motion = ROOT / "static/videos/comparison_motion"
    if comp_motion.exists() and any(comp_motion.glob("*.mp4")):
        print("Normalizing 3D motion comparison videos to 1920x1032...")
        normalize_comparison_motion_videos(comp_motion)
    print("Writing index.html...")
    html = render_html(manifest)
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    # quick stats
    n_vid = sum(1 for _ in (ROOT / "static/videos").rglob("*.mp4"))
    size_mb = sum(p.stat().st_size for p in (ROOT / "static/videos").rglob("*.mp4")) / 1e6
    print(f"Done. Videos: {n_vid}, size: {size_mb:.1f} MB")
    print(f"Open: {ROOT / 'index.html'}")


if __name__ == "__main__":
    main()
