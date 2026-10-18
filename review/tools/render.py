#!/usr/bin/env python3
"""
render.py - Deterministic KiCad schematic, PCB, and 3D rendering pipeline.
Usage:
  render.py <git-ref> <out-dir> [--project-dir <path>]
  render.py --issue <ID> [--baseline-dir <dir>] [--current-dir <dir>] [--issues-json <file>]
"""

import sys
import os
import argparse
import subprocess
import shutil
import tempfile
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

DPI = 300
MM_TO_PX = DPI / 25.4

PCB_LAYERS = [
    ("F.Cu", "pcb_01_F_Cu.png"),
    ("In1.Cu", "pcb_02_In1_Cu.png"),
    ("In2.Cu", "pcb_03_In2_Cu.png"),
    ("In3.Cu", "pcb_04_In3_Cu.png"),
    ("In4.Cu", "pcb_05_In4_Cu.png"),
    ("In5.Cu", "pcb_06_In5_Cu.png"),
    ("In6.Cu", "pcb_07_In6_Cu.png"),
    ("B.Cu", "pcb_08_B_Cu.png"),
    ("F.Mask", "pcb_09_F_Mask.png"),
    ("B.Mask", "pcb_10_B_Mask.png"),
    ("F.SilkS", "pcb_11_F_SilkS.png"),
    ("B.SilkS", "pcb_12_B_SilkS.png"),
    ("F.Paste", "pcb_13_F_Paste.png"),
    ("B.Paste", "pcb_14_B_Paste.png"),
    ("Edge.Cuts", "pcb_15_Edge_Cuts.png"),
    ("F.CrtYd", "pcb_16_F_CrtYd.png"),
    ("B.CrtYd", "pcb_17_B_CrtYd.png"),
    ("F.Fab", "pcb_18_F_Fab.png"),
    ("B.Fab", "pcb_19_B_Fab.png"),
]

SCH_PAGES = [
    (1, "sch_01_Root.png", "Root - Top-Level Overview"),
    (2, "sch_02_ID_Serial.png", "ID Serial"),
    (3, "sch_03_Interfaces.png", "Interfaces"),
    (4, "sch_04_SoM.png", "SoM - Jetson Nano Connector"),
    (5, "sch_05_Display.png", "Display - HDMI & DP"),
    (6, "sch_06_Supply.png", "Supply - Power Regulators"),
    (7, "sch_07_CSI.png", "CSI - Camera Interfaces"),
    (8, "sch_08_USB.png", "USB - USB Hub & Debug"),
]


def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"Command failed ({res.returncode}): {cmd}\nStderr: {res.stderr[:400]}", file=sys.stderr)
    return res


def render_project(project_dir, out_dir):
    project_dir = Path(project_dir).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sch_file = project_dir / "Jetson-AI-Cam-CopperPilot.kicad_sch"
    pcb_file = project_dir / "Jetson-AI-Cam-CopperPilot.kicad_pcb"

    print(f"Rendering schematic from {sch_file} to {out_dir}...")
    tmp_pdf = out_dir / "sch_tmp.pdf"
    run_cmd(f"kicad-cli sch export pdf -o '{tmp_pdf}' '{sch_file}'", cwd=project_dir)
    if tmp_pdf.exists():
        run_cmd(f"pdftoppm -png -r 150 '{tmp_pdf}' '{out_dir}/sch_raw_page'")
        tmp_pdf.unlink()
        for page_num, target_name, _ in SCH_PAGES:
            cand = out_dir / f"sch_raw_page-{page_num}.png"
            if cand.exists():
                shutil.move(str(cand), str(out_dir / target_name))
        for extra in out_dir.glob("sch_raw_page-*.png"):
            extra.unlink()

    print(f"Rendering PCB layers from {pcb_file}...")
    for layer, target_name in PCB_LAYERS:
        tmp_layer_pdf = out_dir / f"layer_tmp_{layer}.pdf"
        run_cmd(f"kicad-cli pcb export pdf -o '{tmp_layer_pdf}' -l '{layer}' --cl Edge.Cuts --mode-single '{pcb_file}'", cwd=project_dir)
        if tmp_layer_pdf.exists():
            prefix = out_dir / f"layer_raw_{layer}"
            run_cmd(f"pdftoppm -png -r {DPI} '{tmp_layer_pdf}' '{prefix}'")
            tmp_layer_pdf.unlink()
            page1 = out_dir / f"layer_raw_{layer}-1.png"
            if page1.exists():
                shutil.move(str(page1), str(out_dir / target_name))
            for extra in out_dir.glob(f"layer_raw_{layer}-*.png"):
                extra.unlink()

    print(f"Rendering 3D views...")
    run_cmd(f"kicad-cli pcb render -o '{out_dir}/3d_top.png' --side top --quality high '{pcb_file}'", cwd=project_dir)
    run_cmd(f"kicad-cli pcb render -o '{out_dir}/3d_bottom.png' --side bottom --quality high '{pcb_file}'", cwd=project_dir)
    run_cmd(f"kicad-cli pcb render -o '{out_dir}/3d_iso.png' --rotate '-45,0,45' --quality high '{pcb_file}'", cwd=project_dir)
    print(f"Render complete: {out_dir}")


def crop_issue(issue_id, baseline_dir, current_dir, issues_json_path, out_issue_dir):
    baseline_dir = Path(baseline_dir).resolve()
    current_dir = Path(current_dir).resolve()
    out_issue_dir = Path(out_issue_dir).resolve()
    out_issue_dir.mkdir(parents=True, exist_ok=True)

    with open(issues_json_path) as f:
        issues = json.load(f)

    issue = None
    for item in issues:
        if item.get("id") == issue_id:
            issue = item
            break
    if not issue:
        print(f"Issue {issue_id} not found in {issues_json_path}", file=sys.stderr)
        sys.exit(1)

    region = issue.get("region", {})
    layer_name = region.get("layer") or region.get("sheet") or "F.Cu"
    x_min_mm = float(region.get("x_min", 85.0))
    y_min_mm = float(region.get("y_min", 75.0))
    x_max_mm = float(region.get("x_max", 120.0))
    y_max_mm = float(region.get("y_max", 110.0))

    target_filename = None
    is_sch = False
    for l, fname in PCB_LAYERS:
        if l.lower() == layer_name.lower():
            target_filename = fname
            break
    if not target_filename:
        for page_num, fname, title in SCH_PAGES:
            if layer_name.lower() in fname.lower() or layer_name.lower() in title.lower():
                target_filename = fname
                is_sch = True
                break

    if not target_filename:
        target_filename = "pcb_01_F_Cu.png"

    base_img_path = baseline_dir / target_filename
    curr_img_path = current_dir / target_filename
    if not base_img_path.exists() or not curr_img_path.exists():
        print(f"Layer image {target_filename} not found in {baseline_dir} or {current_dir}", file=sys.stderr)
        sys.exit(1)

    base_img = Image.open(base_img_path).convert("RGB")
    curr_img = Image.open(curr_img_path).convert("RGB")

    scale = 150 / 25.4 if is_sch else DPI / 25.4
    margin_mm = 2.0
    crop_x1 = max(0, int(round((x_min_mm - margin_mm) * scale)))
    crop_y1 = max(0, int(round((y_min_mm - margin_mm) * scale)))
    crop_x2 = min(base_img.width, int(round((x_max_mm + margin_mm) * scale)))
    crop_y2 = min(base_img.height, int(round((y_max_mm + margin_mm) * scale)))

    if crop_x2 - crop_x1 < 50:
        crop_x2 = min(base_img.width, crop_x1 + 100)
    if crop_y2 - crop_y1 < 50:
        crop_y2 = min(base_img.height, crop_y1 + 100)

    box_x1 = int(round((x_min_mm) * scale)) - crop_x1
    box_y1 = int(round((y_min_mm) * scale)) - crop_y1
    box_x2 = int(round((x_max_mm) * scale)) - crop_x1
    box_y2 = int(round((y_max_mm) * scale)) - crop_y1

    crop_base = base_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    crop_curr = curr_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

    draw_b = ImageDraw.Draw(crop_base)
    draw_b.rectangle([box_x1, box_y1, box_x2, box_y2], outline=(255, 0, 0), width=3)
    draw_b.text((box_x1 + 4, max(0, box_y1 - 18)), issue_id, fill=(255, 0, 0))

    draw_c = ImageDraw.Draw(crop_curr)
    draw_c.rectangle([box_x1, box_y1, box_x2, box_y2], outline=(0, 200, 0), width=3)
    draw_c.text((box_x1 + 4, max(0, box_y1 - 18)), issue_id, fill=(0, 200, 0))

    crop_base.save(out_issue_dir / "before.png")
    crop_curr.save(out_issue_dir / "after.png")

    arr_b = np.array(crop_base.convert("RGB")).astype(int)
    arr_c = np.array(crop_curr.convert("RGB")).astype(int)
    diff_mask = np.abs(arr_c - arr_b).sum(axis=2) > 30

    diff_img_arr = np.full_like(arr_b, 220)
    for y in range(diff_mask.shape[0]):
        for x in range(diff_mask.shape[1]):
            if diff_mask[y, x]:
                if arr_c[y, x].mean() < arr_b[y, x].mean():
                    diff_img_arr[y, x] = [0, 180, 0]  # green added
                else:
                    diff_img_arr[y, x] = [220, 0, 0]  # red removed

    diff_img = Image.fromarray(diff_img_arr.astype(np.uint8))
    draw_d = ImageDraw.Draw(diff_img)
    draw_d.rectangle([box_x1, box_y1, box_x2, box_y2], outline=(0, 0, 255), width=2)
    diff_img.save(out_issue_dir / "diff.png")
    print(f"Generated issue crops for {issue_id} in {out_issue_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("git_ref", nargs="?", default="HEAD")
    parser.add_argument("out_dir", nargs="?", default="review/renders/baseline")
    parser.add_argument("--issue", dest="issue_id")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--baseline-dir", default="review/renders/baseline")
    parser.add_argument("--current-dir", default="review/renders/final")
    parser.add_argument("--issues-json", default="review/issues.json")
    args = parser.parse_args()

    if args.issue_id:
        out_issue_dir = Path("review/renders/issues") / args.issue_id
        crop_issue(args.issue_id, args.baseline_dir, args.current_dir, args.issues_json, out_issue_dir)
        return

    git_ref = args.git_ref
    out_dir = Path(args.out_dir).resolve()
    repo_root = Path(".").resolve()

    if git_ref in ["working", "local", "current"]:
        render_project(repo_root, out_dir)
    else:
        wt_dir = Path(tempfile.mkdtemp(prefix="kicad_wt_"))
        print(f"Creating worktree at {wt_dir} for ref {git_ref}...")
        try:
            run_cmd(f"git worktree add --detach '{wt_dir}' '{git_ref}'", cwd=repo_root)
            render_project(wt_dir, out_dir)
        finally:
            print(f"Cleaning up worktree {wt_dir}...")
            run_cmd(f"git worktree remove --force '{wt_dir}'", cwd=repo_root)
            run_cmd(f"git worktree prune", cwd=repo_root)
            if wt_dir.exists():
                shutil.rmtree(wt_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
