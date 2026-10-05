import os, sys, shutil, subprocess, json, uuid

KICAD_PYTHON = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3" # wait, kicad-cli is at:
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PRIMARY_PCB = "Jetson-AI-Cam-CopperPilot.kicad_pcb"
PRIMARY_PRO = "Jetson-AI-Cam-CopperPilot.kicad_pro"

def run_drc(pcb_path, rpt_path=None):
    if rpt_path is None:
        rpt_path = pcb_path + ".drc.json"
    cmd = [KICAD_CLI, "pcb", "drc", "--format", "json", "-o", rpt_path, pcb_path]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(rpt_path):
        return -1, -1, -1, []
    with open(rpt_path) as f:
        d = json.load(f)
    violations = d.get("violations", [])
    errors = [v for v in violations if v.get("severity") == "error"]
    unconn = d.get("unconnected_items", [])
    return len(errors), len(violations), len(unconn), unconn

def apply_staged_routing(op_id, items, commit_msg=None):
    """
    items is a list of dicts:
      For track: {'type': 'track', 'layer': 'F.Cu', 'start': (x1, y1), 'end': (x2, y2), 'width': 0.15, 'net': 'GND'}
      For via:   {'type': 'via', 'pos': (x, y), 'size': 0.4, 'drill': 0.15, 'net': 'GND', 'layers': ['F.Cu', 'B.Cu']}
    """
    staging_dir = os.path.join(".copperpilot/tmp/staging", op_id)
    baseline_dir = os.path.join(staging_dir, "baseline")
    candidate_dir = os.path.join(staging_dir, "candidate")
    
    os.makedirs(baseline_dir, exist_ok=True)
    os.makedirs(candidate_dir, exist_ok=True)
    
    base_pcb = os.path.join(baseline_dir, PRIMARY_PCB)
    base_pro = os.path.join(baseline_dir, PRIMARY_PRO)
    cand_pcb = os.path.join(candidate_dir, PRIMARY_PCB)
    cand_pro = os.path.join(candidate_dir, PRIMARY_PRO)
    
    shutil.copy2(PRIMARY_PCB, base_pcb)
    shutil.copy2(PRIMARY_PRO, base_pro)
    shutil.copy2(PRIMARY_PCB, cand_pcb)
    shutil.copy2(PRIMARY_PRO, cand_pro)
    
    # 1. Run baseline DRC
    b_err, b_viol, b_unconn, _ = run_drc(base_pcb)
    print(f"[{op_id}] Baseline DRC: {b_err} errors, {b_viol} violations, {b_unconn} unconnected")
    
    # 2. Modify candidate using KiCad python script
    items_json = os.path.join(staging_dir, "items.json")
    with open(items_json, "w") as f:
        json.dump(items, f)
        
    py_script = f"""
import pcbnew, json

board = pcbnew.LoadBoard('{cand_pcb}')

with open('{items_json}') as f:
    items = json.load(f)

for item in items:
    itype = item.get('type')
    netname = item.get('net')
    netinfo = board.FindNet(netname)
    if not netinfo:
        print(f"ERROR: Net {{netname}} not found on board!")
        continue
    netcode = netinfo.GetNetCode()
    
    if itype == 'track':
        layer_name = item.get('layer', 'F.Cu')
        layer_id = board.GetLayerID(layer_name)
        track = pcbnew.PCB_TRACK(board)
        p1 = item['start']
        p2 = item['end']
        track.SetStart(pcbnew.VECTOR2I(int(p1[0]*1e6), int(p1[1]*1e6)))
        track.SetEnd(pcbnew.VECTOR2I(int(p2[0]*1e6), int(p2[1]*1e6)))
        track.SetWidth(int(item.get('width', 0.15)*1e6))
        track.SetLayer(layer_id)
        track.SetNetCode(netcode)
        board.Add(track)
    elif itype == 'via':
        pos = item['pos']
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(int(pos[0]*1e6), int(pos[1]*1e6)))
        via.SetWidth(int(item.get('size', 0.4)*1e6))
        via.SetDrill(int(item.get('drill', 0.15)*1e6))
        via.SetNetCode(netcode)
        board.Add(via)

board.Save('{cand_pcb}')
"""
    script_path = os.path.join(staging_dir, "apply.py")
    with open(script_path, "w") as f:
        f.write(py_script)
        
    res = subprocess.run([KICAD_PYTHON, script_path], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[{op_id}] Python error applying edits: {res.stderr}")
        return False
        
    # 3. Refill zones on candidate
    refill_cmd = [KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", cand_pcb]
    subprocess.run(refill_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 4. Run DRC on candidate
    c_err, c_viol, c_unconn, _ = run_drc(cand_pcb)
    print(f"[{op_id}] Candidate DRC: {c_err} errors, {c_viol} violations, {c_unconn} unconnected")
    
    # Check gates
    if c_err > b_err:
        print(f"[{op_id}] REJECTED: Candidate introduced {c_err - b_err} new errors!")
        return False
    if c_unconn > b_unconn:
        print(f"[{op_id}] REJECTED: Candidate increased unconnected count ({b_unconn} -> {c_unconn})")
        return False
    if c_err == 0 and c_unconn < b_unconn:
        print(f"[{op_id}] PASSED: {b_unconn} -> {c_unconn} unconnected ({b_unconn - c_unconn} resolved), 0 errors.")
        # Promote candidate to primary
        shutil.copy2(cand_pcb, PRIMARY_PCB)
        # Verify primary
        p_err, p_viol, p_unconn, _ = run_drc(PRIMARY_PCB)
        print(f"[{op_id}] Primary verified: {p_err} errors, {p_unconn} unconnected")
        # Clean up staging
        shutil.rmtree(staging_dir, ignore_errors=True)
        # Commit if commit_msg provided
        if commit_msg:
            subprocess.run(["git", "add", PRIMARY_PCB])
            subprocess.run(["git", "commit", "-m", commit_msg])
            print(f"[{op_id}] Committed to git: {commit_msg}")
        return True
    elif c_err == 0 and c_unconn == b_unconn:
        print(f"[{op_id}] NEUTRAL: unconnected count unchanged ({c_unconn}). Staging kept for inspection.")
        return False
    else:
        print(f"[{op_id}] REJECTED: Errors present ({c_err} errors).")
        return False

if __name__ == "__main__":
    print("Staged Route Runner loaded successfully.")
