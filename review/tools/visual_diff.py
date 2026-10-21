#!/usr/bin/env python3
"""
visual_diff.py - Compute pixel diffs, cluster changed regions, match with issues.json,
and perform Netlist and BOM diffs.
Usage:
  visual_diff.py <before-dir> <after-dir> [--issues review/issues.json] [--out-dir review/renders/diff]
"""

import sys
import os
import argparse
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

DPI = 300
MM_TO_PX = DPI / 25.4


def bbox_overlap(b1, b2, margin=3.0):
    # b1, b2 format: (xmin, ymin, xmax, ymax) in mm
    return not (b1[2] + margin < b2[0] or b1[0] - margin > b2[2] or
                b1[3] + margin < b2[1] or b1[1] - margin > b2[3])


def cluster_diff_pixels(diff_mask, scale):
    # diff_mask is 2D boolean array (H, W)
    # Downsample for fast connected-component bounding box clustering
    try:
        from scipy.ndimage import label, find_objects
        labeled, num_features = label(diff_mask)
        objects = find_objects(labeled)
        regions = []
        for obj in objects:
            y_slice, x_slice = obj
            h = y_slice.stop - y_slice.start
            w = x_slice.stop - x_slice.start
            # Filter noise < 10 pixels
            if w * h < 16:
                continue
            x_min_mm = round(x_slice.start / scale, 2)
            y_min_mm = round(y_slice.start / scale, 2)
            x_max_mm = round(x_slice.stop / scale, 2)
            y_max_mm = round(y_slice.stop / scale, 2)
            regions.append({
                "x_min": x_min_mm,
                "y_min": y_min_mm,
                "x_max": x_max_mm,
                "y_max": y_max_mm,
                "pixel_count": int(diff_mask[y_slice, x_slice].sum())
            })
        return regions
    except ImportError:
        # Fallback grid clustering without scipy
        grid_size = 20
        h, w = diff_mask.shape
        gh = (h + grid_size - 1) // grid_size
        gw = (w + grid_size - 1) // grid_size
        active = []
        for gy in range(gh):
            for gx in range(gw):
                sub = diff_mask[gy*grid_size:(gy+1)*grid_size, gx*grid_size:(gx+1)*grid_size]
                if sub.sum() > 4:
                    active.append((gx, gy))
        
        # Merge neighbor cells
        if not active:
            return []
        
        # Simple bounding boxes of connected components
        visited = set()
        components = []
        for cell in active:
            if cell in visited:
                continue
            comp = []
            queue = [cell]
            visited.add(cell)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                cx, cy = curr
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        neighbor = (cx + dx, cy + dy)
                        if neighbor in active and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
            components.append(comp)
        
        regions = []
        for comp in components:
            min_gx = min(c[0] for c in comp)
            max_gx = max(c[0] for c in comp)
            min_gy = min(c[1] for c in comp)
            max_gy = max(c[1] for c in comp)
            regions.append({
                "x_min": round((min_gx * grid_size) / scale, 2),
                "y_min": round((min_gy * grid_size) / scale, 2),
                "x_max": round(((max_gx + 1) * grid_size) / scale, 2),
                "y_max": round(((max_gy + 1) * grid_size) / scale, 2),
                "pixel_count": len(comp) * grid_size
            })
        return regions


def compute_layer_diff(before_path, after_path, out_overlay_path, is_sch=False):
    before_img = Image.open(before_path).convert("RGB")
    after_img = Image.open(after_path).convert("RGB")

    w = min(before_img.width, after_img.width)
    h = min(before_img.height, after_img.height)
    b_arr = np.array(before_img.crop((0, 0, w, h))).astype(int)
    a_arr = np.array(after_img.crop((0, 0, w, h))).astype(int)

    # Difference mask
    diff = np.abs(a_arr - b_arr).sum(axis=2)
    changed = diff > 40

    overlay = np.full((h, w, 3), 235, dtype=np.uint8)  # grey background

    # Dim unchanged background features
    unchanged_dark = (b_arr.mean(axis=2) < 220) & (~changed)
    overlay[unchanged_dark] = [170, 170, 170]

    # Added in green, removed in red
    for y in range(h):
        for x in range(w):
            if changed[y, x]:
                if a_arr[y, x].mean() < b_arr[y, x].mean():
                    overlay[y, x] = [0, 200, 0]  # Green (added copper/lines)
                else:
                    overlay[y, x] = [220, 0, 0]  # Red (removed)

    overlay_img = Image.fromarray(overlay)
    out_overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_img.save(out_overlay_path)

    scale = 150 / 25.4 if is_sch else MM_TO_PX
    regions = cluster_diff_pixels(changed, scale)
    return regions, int(changed.sum())


def diff_netlists(before_netlist, after_netlist):
    # Parse simple s-expression netlists
    import re
    def parse_nets(path):
        if not path or not Path(path).exists():
            return {}
        txt = Path(path).read_text(errors="ignore")
        nets = {}
        for m in re.finditer(r'\(net\s+\(code\s+\d+\)\s+\(name\s+\"([^\"]+)\"\)(.*?)\)\n\t\)', txt, re.DOTALL):
            name = m.group(1)
            nodes = re.findall(r'\(node\s+\(ref\s+\"([^\"]+)\"\)\s+\(pin\s+\"([^\"]+)\"\)', m.group(2))
            nets[name] = set(f"{ref}.{pin}" for ref, pin in nodes)
        return nets

    b_nets = parse_nets(before_netlist)
    a_nets = parse_nets(after_netlist)

    added_nets = [n for n in a_nets if n not in b_nets]
    removed_nets = [n for n in b_nets if n not in a_nets]
    modified_nets = []
    for n in a_nets:
        if n in b_nets and a_nets[n] != b_nets[n]:
            modified_nets.append({
                "net": n,
                "added_nodes": list(a_nets[n] - b_nets[n]),
                "removed_nodes": list(b_nets[n] - a_nets[n])
            })
    return {
        "added_nets": added_nets,
        "removed_nets": removed_nets,
        "modified_nets": modified_nets
    }


def diff_boms(before_bom, after_bom):
    import csv
    def read_bom(p):
        if not p or not Path(p).exists():
            return {}
        res = {}
        with open(p, newline="", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                des = row.get("Designator") or row.get("Reference") or row.get("Refs")
                if des:
                    for d in [x.strip() for x in des.split(",") if x.strip()]:
                        res[d] = {
                            "Value": row.get("Value", row.get("Comment", "")),
                            "Footprint": row.get("Footprint", ""),
                            "LCSC": row.get("LCSC", row.get("LCSC Part", row.get("LCSC#", ""))),
                            "MPN": row.get("MPN", row.get("Manufacturer Part", ""))
                        }
        return res

    b_bom = read_bom(before_bom)
    a_bom = read_bom(after_bom)

    added = [k for k in a_bom if k not in b_bom]
    removed = [k for k in b_bom if k not in a_bom]
    changed = []
    for k in a_bom:
        if k in b_bom and a_bom[k] != b_bom[k]:
            changed.append({
                "designator": k,
                "before": b_bom[k],
                "after": a_bom[k]
            })
    return {
        "added_parts": added,
        "removed_parts": removed,
        "changed_parts": changed
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before_dir")
    parser.add_argument("after_dir")
    parser.add_argument("--issues", default="review/issues.json")
    parser.add_argument("--out-dir", default="review/renders/diff")
    parser.add_argument("--before-netlist")
    parser.add_argument("--after-netlist")
    parser.add_argument("--before-bom")
    parser.add_argument("--after-bom")
    args = parser.parse_args()

    before_dir = Path(args.before_dir).resolve()
    after_dir = Path(args.after_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    issues = []
    if Path(args.issues).exists():
        with open(args.issues) as f:
            issues = json.load(f)

    all_changes = []
    total_unexplained = 0

    image_files = sorted(list(before_dir.glob("*.png")))
    for img_path in image_files:
        fname = img_path.name
        if fname.startswith("3d_"):
            continue
        after_path = after_dir / fname
        if not after_path.exists():
            continue

        overlay_path = out_dir / fname
        is_sch = fname.startswith("sch_")
        regions, num_changed_px = compute_layer_diff(img_path, after_path, overlay_path, is_sch=is_sch)

        layer_name = fname.replace(".png", "")
        for reg in regions:
            reg_bbox = (reg["x_min"], reg["y_min"], reg["x_max"], reg["y_max"])
            matched_issues = []
            for issue in issues:
                ireg = issue.get("region", {})
                ilays = ireg.get("layers") or [ireg.get("layer") or ireg.get("sheet") or ""]
                if not isinstance(ilays, list):
                    ilays = [ilays]

                layer_matched = False
                for ilay in ilays:
                    if not ilay or ilay == "all_pcb":
                        layer_matched = True
                        break
                    if ilay == "all_copper" and ("Cu" in layer_name or "_Cu" in layer_name):
                        layer_matched = True
                        break
                    if ilay == "all_silkscreen" and "Silk" in layer_name:
                        layer_matched = True
                        break
                    if ilay.lower() in layer_name.lower() or layer_name.lower() in ilay.lower():
                        layer_matched = True
                        break

                if not layer_matched:
                    continue

                ibox = (float(ireg.get("x_min", 0)), float(ireg.get("y_min", 0)),
                        float(ireg.get("x_max", 0)), float(ireg.get("y_max", 0)))
                if bbox_overlap(reg_bbox, ibox, margin=6.0):
                    matched_issues.append(issue.get("id"))

            status = "MATCHED" if matched_issues else "UNEXPLAINED"
            if status == "UNEXPLAINED":
                total_unexplained += 1
            all_changes.append({
                "layer": layer_name,
                "region": reg,
                "matched_issues": matched_issues,
                "status": status
            })

    netlist_diff = diff_netlists(args.before_netlist, args.after_netlist)
    bom_diff = diff_boms(args.before_bom, args.after_bom)

    result_payload = {
        "total_changed_regions": len(all_changes),
        "total_unexplained": total_unexplained,
        "regions": all_changes,
        "netlist_diff": netlist_diff,
        "bom_diff": bom_diff
    }

    changes_json_path = out_dir / "changes.json"
    with open(changes_json_path, "w") as f:
        json.dump(result_payload, f, indent=2)

    print(f"Visual diff complete: {len(all_changes)} regions detected ({total_unexplained} unexplained).")
    print(f"Results saved to {changes_json_path}")
    if total_unexplained > 0:
        print(f"WARNING: {total_unexplained} unexplained regions detected!", file=sys.stderr)


if __name__ == "__main__":
    main()
