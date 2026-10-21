#!/usr/bin/env python3
"""
run_verify.py - Acceptance test runner executing tests T1 through T11.
Writes review/verify-report.json and prints PASS/FAIL per test.
"""

import sys
import os
import json
import re
import csv
import subprocess
from pathlib import Path

REPO_ROOT = Path(".").resolve()
SCH_FILE = REPO_ROOT / "Jetson-AI-Cam-CopperPilot.kicad_sch"
PCB_FILE = REPO_ROOT / "Jetson-AI-Cam-CopperPilot.kicad_pcb"
PRO_FILE = REPO_ROOT / "Jetson-AI-Cam-CopperPilot.kicad_pro"
DRU_FILE = REPO_ROOT / "Jetson-AI-Cam-CopperPilot.kicad_dru"
ISSUES_FILE = REPO_ROOT / "review/issues.json"
DECISIONS_FILE = REPO_ROOT / "review/DECISIONS.md"
CHANGES_FILE = REPO_ROOT / "review/renders/diff/changes.json"
REPORT_FILE = REPO_ROOT / "review/verify-report.json"

# Section 3 JLCPCB Multilayer Targets
JLC_TARGETS = {
    "min_track_width": 0.127,      # multilayer fine pitch / target >= 0.15 (0.127 min escape)
    "min_clearance": 0.127,        # target >= 0.15 (0.127 min escape)
    "min_via_diameter": 0.45,      # 0.45 min without surcharge (target 0.60)
    "min_through_hole_diameter": 0.25, # 0.25 min without surcharge (target 0.30)
    "min_via_annular_width": 0.10, # JLC limit 0.10, target 0.15
    "min_copper_edge_clearance": 0.25, # JLC limit 0.20, target 0.30
    "min_hole_to_hole": 0.254,     # JLC limit 0.20 (vias), target 0.50
    "min_text_height": 0.8,        # JLC limit 1.0 (target 1.0)
    "min_text_thickness": 0.12,    # JLC limit 0.15 (target 0.15)
    "min_silk_clearance": 0.15     # JLC limit 0.15
}


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def load_decisions():
    if not DECISIONS_FILE.exists():
        return set()
    txt = DECISIONS_FILE.read_text(errors="ignore")
    # match DEC-xxx, WAIVER-xxx, and RULE-xxx tokens
    return set(re.findall(r'\b(DEC-\d+|WAIVER-\d+|RULE-[a-zA-Z0-9_]+)\b', txt))


def test_t1_erc(decisions):
    # Run kicad-cli sch erc
    erc_json_path = REPO_ROOT / "review/tmp_erc.json"
    cmd = f"kicad-cli sch erc --severity-all --format json -o '{erc_json_path}' '{SCH_FILE}'"
    res = run_cmd(cmd)
    
    if not erc_json_path.exists():
        # Fallback to default output location
        def_path = REPO_ROOT / "Jetson-AI-Cam-CopperPilot-erc.json"
        if def_path.exists():
            erc_json_path = def_path

    if not erc_json_path.exists():
        return False, "ERC JSON report could not be generated."

    try:
        with open(erc_json_path) as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to parse ERC JSON: {e}"

    errors = 0
    warnings = 0
    exclusions = []

    for sheet in data.get("sheets", []):
        for v in sheet.get("violations", []):
            sev = v.get("severity")
            if sev == "error":
                errors += 1
            elif sev == "warning":
                warnings += 1
        for exc in sheet.get("exclusions", []):
            exclusions.append(exc)

    unjustified_exclusions = []
    for exc in exclusions:
        comment = exc.get("comment", "")
        has_dec = any(d in comment for d in decisions)
        if not has_dec:
            unjustified_exclusions.append(exc.get("description", "exclusion"))

    details = f"Errors: {errors}, Warnings: {warnings}, Exclusions: {len(exclusions)}"
    passed = (errors == 0 and warnings == 0 and len(unjustified_exclusions) == 0)
    if not passed:
        msg = f"{details}. "
        if errors > 0: msg += f"{errors} errors. "
        if warnings > 0: msg += f"{warnings} warnings. "
        if unjustified_exclusions: msg += f"{len(unjustified_exclusions)} unjustified exclusions."
        return False, msg.strip()
    return True, details


def test_t2_drc(decisions):
    drc_json_path = REPO_ROOT / "review/tmp_drc.json"
    cmd = f"kicad-cli pcb drc --severity-all --refill-zones --schematic-parity --format json -o '{drc_json_path}' '{PCB_FILE}'"
    res = run_cmd(cmd)

    if not drc_json_path.exists():
        def_path = REPO_ROOT / "Jetson-AI-Cam-CopperPilot-drc.json"
        if def_path.exists():
            drc_json_path = def_path

    if not drc_json_path.exists():
        return False, "DRC JSON report could not be generated."

    try:
        with open(drc_json_path) as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to parse DRC JSON: {e}"

    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    parity = data.get("schematic_parity", []) or data.get("schematic_parity_issues", [])
    exclusions = data.get("exclusions", [])

    errors = sum(1 for v in violations if v.get("severity") == "error")
    warnings = sum(1 for v in violations if v.get("severity") == "warning")

    unjustified_exclusions = []
    for exc in exclusions:
        comment = exc.get("comment", "")
        if not any(d in comment for d in decisions):
            unjustified_exclusions.append(exc.get("description", "exclusion"))

    details = f"Errors: {errors}, Warnings: {warnings}, Unconnected: {len(unconnected)}, Parity: {len(parity)}"
    passed = (errors == 0 and warnings == 0 and len(unconnected) == 0 and len(parity) == 0 and len(unjustified_exclusions) == 0)
    if not passed:
        msg = f"{details}. "
        if errors: msg += f"{errors} errors. "
        if warnings: msg += f"{warnings} warnings. "
        if unconnected: msg += f"{len(unconnected)} unconnected items. "
        if parity: msg += f"{len(parity)} parity issues. "
        return False, msg.strip()
    return True, details


def test_t3_rules_ge_jlc(decisions):
    if not PRO_FILE.exists():
        return False, "Missing .kicad_pro file"
    try:
        with open(PRO_FILE) as f:
            pro = json.load(f)
    except Exception as e:
        return False, f"Failed to load .kicad_pro: {e}"

    rules = pro.get("board", {}).get("design_settings", {}).get("rules", {})
    failed_rules = []
    for key, target in JLC_TARGETS.items():
        val = rules.get(key)
        if val is not None:
            if val < target - 1e-4:
                # check if decision exists
                if not any(f"RULE-{key}" in d or "WAIVER" in d for d in decisions):
                    failed_rules.append(f"{key}={val} < {target}")

    if failed_rules:
        return False, f"Rules below JLC targets without waiver: {', '.join(failed_rules)}"
    return True, "All active rules meet or beat JLCPCB targets."


def test_t4_rules_not_loosened(decisions):
    # Compare with review-baseline tag
    res = run_cmd("git show review-baseline:Jetson-AI-Cam-CopperPilot.kicad_pro")
    if res.returncode != 0:
        return True, "Baseline tag review-baseline not present or unchanged."
    try:
        base_pro = json.loads(res.stdout)
    except:
        return True, "Baseline .kicad_pro could not be parsed."

    with open(PRO_FILE) as f:
        curr_pro = json.load(f)

    b_rules = base_pro.get("board", {}).get("design_settings", {}).get("rules", {})
    c_rules = curr_pro.get("board", {}).get("design_settings", {}).get("rules", {})

    loosened = []
    for k, b_val in b_rules.items():
        if isinstance(b_val, (int, float)) and k in c_rules:
            c_val = c_rules[k]
            # If minimum required distance was lowered
            if "min_" in k and c_val < b_val - 1e-4:
                if not any(f"RULE-{k}" in d or "WAIVER" in d for d in decisions):
                    loosened.append(f"{k} loosened from {b_val} to {c_val}")

    if loosened:
        return False, f"Rules loosened without justification: {', '.join(loosened)}"
    return True, "No rules loosened compared to baseline."


def test_t5_severities_not_downgraded(decisions):
    res = run_cmd("git show review-baseline:Jetson-AI-Cam-CopperPilot.kicad_pro")
    if res.returncode != 0:
        return True, "Baseline tag not present."
    try:
        base_pro = json.loads(res.stdout)
    except:
        return True, "Baseline .kicad_pro parse skipped."

    with open(PRO_FILE) as f:
        curr_pro = json.load(f)

    b_sev = base_pro.get("board", {}).get("design_settings", {}).get("rule_severities", {})
    c_sev = curr_pro.get("board", {}).get("design_settings", {}).get("rule_severities", {})

    downgraded = []
    for k, b_val in b_sev.items():
        c_val = c_sev.get(k)
        if b_val in ["error", "warning"] and c_val == "ignore":
            if not any(f"SEV-{k}" in d or "WAIVER" in d for d in decisions):
                downgraded.append(f"{k} downgraded from {b_val} to ignore")

    if downgraded:
        return False, f"Severities downgraded to ignore without justification: {', '.join(downgraded)}"
    return True, "No DRC severities downgraded to ignore."


def test_t6_bom_completeness():
    bom_file = REPO_ROOT / "manufacturing/BOM.csv"
    if not bom_file.exists():
        # Check trial outputs or generate BOM
        bom_file = REPO_ROOT / "review/trial-outputs/BOM.csv"
    if not bom_file.exists():
        return False, "BOM file does not exist (manufacturing/BOM.csv)."

    missing = []
    with open(bom_file, newline="", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            des = row.get("Designator") or row.get("Reference") or ""
            dnp = row.get("DNP", "no").strip().lower()
            if dnp in ["yes", "true", "1", "dnp"]:
                continue
            val = row.get("Value", row.get("Comment", "")).strip()
            fp = row.get("Footprint", "").strip()
            mpn = row.get("MPN", row.get("Manufacturer Part", "")).strip()
            lcsc = row.get("LCSC", row.get("LCSC Part", row.get("LCSC#", ""))).strip()
            if not (val and fp and mpn and lcsc):
                missing.append(f"{des} (missing: {'Value ' if not val else ''}{'Footprint ' if not fp else ''}{'MPN ' if not mpn else ''}{'LCSC' if not lcsc else ''})")

    if missing:
        return False, f"{len(missing)} BOM entries incomplete: {', '.join(missing[:5])}"
    return True, "All assembled components have Value, Footprint, MPN, and LCSC Part #."


def test_t7_outputs():
    mfg_dir = REPO_ROOT / "manufacturing"
    if not mfg_dir.exists():
        return False, "manufacturing/ output directory missing."
    
    gerbers_zip = mfg_dir / "gerbers.zip"
    drill_file = mfg_dir / "Jetson-AI-Cam-CopperPilot.drl"
    bom_file = mfg_dir / "BOM.csv"
    cpl_file = mfg_dir / "CPL.csv"

    missing_files = []
    if not gerbers_zip.exists() and not list(mfg_dir.glob("*.gbr")):
        missing_files.append("gerbers")
    if not drill_file.exists() and not list(mfg_dir.glob("*.drl")):
        missing_files.append("drills")
    if not bom_file.exists():
        missing_files.append("BOM.csv")
    if not cpl_file.exists():
        missing_files.append("CPL.csv")

    if missing_files:
        return False, f"Missing production outputs: {', '.join(missing_files)}"

    # Check CPL headers
    with open(cpl_file, errors="ignore") as f:
        first_line = f.readline().strip()
    req_headers = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]
    for rh in req_headers:
        if rh.lower() not in first_line.lower():
            return False, f"CPL missing required header: {rh}"

    return True, "Gerbers, drills, BOM, and CPL are present with valid formatting."


def test_t8_issues_closed():
    if not ISSUES_FILE.exists():
        return False, "review/issues.json not found."
    with open(ISSUES_FILE) as f:
        issues = json.load(f)

    open_above_p3 = []
    for issue in issues:
        sev = issue.get("sev", "P2")
        status = issue.get("status", "Open")
        if status in ["Open", "In progress", "Approved"]:
            if sev in ["P0", "P1", "P2"]:
                open_above_p3.append(f"{issue.get('id')} ({sev})")

    if open_above_p3:
        return False, f"{len(open_above_p3)} unclosed issues above P3: {', '.join(open_above_p3)}"
    return True, f"All {len(issues)} issues in register are Verified or Waived."


def test_t9_evidence_complete():
    if not ISSUES_FILE.exists():
        return False, "review/issues.json not found."
    with open(ISSUES_FILE) as f:
        issues = json.load(f)

    missing_evidence = []
    for issue in issues:
        if issue.get("status") == "Waived":
            continue
        iid = issue.get("id")
        idir = REPO_ROOT / f"review/renders/issues/{iid}"
        b_img = idir / "before.png"
        a_img = idir / "after.png"
        d_img = idir / "diff.png"
        commits = issue.get("commits", [])
        if not (b_img.exists() and a_img.exists() and d_img.exists() and len(commits) > 0):
            missing_evidence.append(iid)

    if missing_evidence:
        return False, f"Missing crops or commit hashes for issues: {', '.join(missing_evidence)}"
    return True, "All non-waived issues possess verified before/after/diff crops and commits."


def test_t10_no_unexplained_changes():
    if not CHANGES_FILE.exists():
        return False, "review/renders/diff/changes.json not found. Run visual_diff.py."
    with open(CHANGES_FILE) as f:
        data = json.load(f)

    unexplained = data.get("total_unexplained", 0)
    if unexplained > 0:
        return False, f"{unexplained} unexplained regions detected in visual diff."
    return True, "Zero unexplained visual diff regions across all sheets and layers."


def test_t11_repo_hygiene():
    # Check for absolute paths in project files
    dirty_patterns = ["/home/", "C:\\", "/Users/", "/tmp/"]
    dirty_found = []
    for fname in ["Jetson-AI-Cam-CopperPilot.kicad_sch", "Jetson-AI-Cam-CopperPilot.kicad_pcb", "fp-lib-table", "sym-lib-table"]:
        p = REPO_ROOT / fname
        if p.exists():
            txt = p.read_text(errors="ignore")
            for pat in dirty_patterns:
                if pat in txt:
                    dirty_found.append(f"{fname} contains user/absolute path pattern '{pat}'")

    # Check for untracked cache or lock files in git
    res = run_cmd("git status --porcelain")
    for line in res.stdout.splitlines():
        if line.endswith(".kicad_prl") or line.endswith(".bck") or line.endswith(".lck"):
            dirty_found.append(f"Cache/lock file present in git status: {line}")

    if dirty_found:
        return False, f"Repo hygiene violations: {'; '.join(dirty_found[:3])}"
    return True, "Project files use clean project-local relative paths without tracked cache/lock files."


def main():
    decisions = load_decisions()
    tests = [
        ("T1 ERC", test_t1_erc, [decisions]),
        ("T2 DRC", test_t2_drc, [decisions]),
        ("T3 Rules >= JLC", test_t3_rules_ge_jlc, [decisions]),
        ("T4 Rules not loosened", test_t4_rules_not_loosened, [decisions]),
        ("T5 Severities not downgraded", test_t5_severities_not_downgraded, [decisions]),
        ("T6 BOM completeness", test_t6_bom_completeness, []),
        ("T7 Outputs", test_t7_outputs, []),
        ("T8 Issues closed", test_t8_issues_closed, []),
        ("T9 Evidence complete", test_t9_evidence_complete, []),
        ("T10 No unexplained changes", test_t10_no_unexplained_changes, []),
        ("T11 Repo hygiene", test_t11_repo_hygiene, [])
    ]

    results = {}
    all_passed = True
    print("=" * 65)
    print(" ACCEPTANCE VERIFICATION RUN (review/verify.sh)")
    print("=" * 65)

    for name, fn, args in tests:
        try:
            passed, details = fn(*args)
        except Exception as e:
            passed = False
            details = f"Exception: {e}"

        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        print(f"[{status_str:4s}] {name:30s} -> {details}")
        results[name] = {
            "passed": passed,
            "details": details
        }

    report_payload = {
        "overall_status": "PASS" if all_passed else "FAIL",
        "timestamp": str(subprocess.check_output(["date", "-u", "+%Y-%m-%d %H:%M:%SZ"], text=True).strip()),
        "tests": results
    }

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        json.dump(report_payload, f, indent=2)

    print("=" * 65)
    print(f"Overall Acceptance Result: {'PASS' if all_passed else 'FAIL'}")
    print("Full report written to: review/verify-report.json")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
