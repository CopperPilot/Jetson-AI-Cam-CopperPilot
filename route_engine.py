import os, sys, shutil, subprocess, json

KICAD_PYTHON = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PRIMARY_PCB = "Jetson-AI-Cam-CopperPilot.kicad_pcb"
PRIMARY_PRO = "Jetson-AI-Cam-CopperPilot.kicad_pro"

def run_drc(pcb_path, rpt_path=None):
    if rpt_path is None:
        rpt_path = pcb_path + ".drc.json"
    cmd = [KICAD_CLI, "pcb", "drc", "--format", "json", "-o", rpt_path, pcb_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(rpt_path):
        return -1, -1, -1, []
    with open(rpt_path) as f:
        d = json.load(f)
    violations = d.get("violations", [])
    errors = [v for v in violations if v.get("severity") == "error"]
    unconn = d.get("unconnected_items", [])
    return len(errors), len(violations), len(unconn), errors, unconn

def try_route(op_id, items, commit_msg=None):
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
    
    b_err, b_viol, b_unconn, _, _ = run_drc(base_pcb)
    
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
        
    refill_cmd = [KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", cand_pcb]
    subprocess.run(refill_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    c_err, c_viol, c_unconn, errors, unconn = run_drc(cand_pcb)
    print(f"[{op_id}] Baseline: {b_unconn} unconn, {b_err} err | Candidate: {c_unconn} unconn, {c_err} err")
    
    if c_err > b_err:
        print(f"[{op_id}] ERRORS introduced ({c_err} errors):")
        for e in errors[:5]:
            descs = [it.get('description', '') for it in e.get('items', [])]
            print(f"  {e.get('type')}: {' <--> '.join(descs)}")
        return False
        
    if c_unconn < b_unconn and c_err == 0:
        print(f"[{op_id}] SUCCESS! {b_unconn} -> {c_unconn} unconnected. Promoting.")
        shutil.copy2(cand_pcb, PRIMARY_PCB)
        p_err, p_viol, p_unconn, _, _ = run_drc(PRIMARY_PCB)
        print(f"[{op_id}] Verified primary: {p_unconn} unconnected, {p_err} errors.")
        shutil.rmtree(staging_dir, ignore_errors=True)
        if commit_msg:
            subprocess.run(["git", "add", PRIMARY_PCB])
            subprocess.run(["git", "commit", "-m", commit_msg])
            print(f"[{op_id}] Committed: {commit_msg}")
        return True
    elif c_unconn == b_unconn and c_err == 0:
        print(f"[{op_id}] NEUTRAL: no reduction in unconnected items.")
        return False
    else:
        print(f"[{op_id}] REJECTED.")
        return False
