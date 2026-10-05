
import os, sys, shutil, subprocess, json, uuid
import pcbnew

PRIMARY_PCB = "Jetson-AI-Cam-CopperPilot.kicad_pcb"
PRIMARY_PRO = "Jetson-AI-Cam-CopperPilot.kicad_pro"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

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

def test_staged(op_id, items_to_add, commit_msg=None, promote=False):
    staging_dir = os.path.join(".copperpilot/tmp/staging", op_id)
    cand_dir = os.path.join(staging_dir, "candidate")
    base_dir = os.path.join(staging_dir, "baseline")
    os.makedirs(cand_dir, exist_ok=True)
    os.makedirs(base_dir, exist_ok=True)
    
    cand_pcb = os.path.join(cand_dir, PRIMARY_PCB)
    base_pcb = os.path.join(base_dir, PRIMARY_PCB)
    cand_pro = os.path.join(cand_dir, PRIMARY_PRO)
    base_pro = os.path.join(base_dir, PRIMARY_PRO)
    
    shutil.copy2(PRIMARY_PCB, cand_pcb)
    shutil.copy2(PRIMARY_PCB, base_pcb)
    shutil.copy2(PRIMARY_PRO, cand_pro)
    shutil.copy2(PRIMARY_PRO, base_pro)
    
    b_err, b_viol, b_unconn, _, _ = run_drc(base_pcb)
    print(f"[{op_id}] Baseline: {b_err} errors, {b_viol} violations, {b_unconn} unconnected")
    
    board = pcbnew.LoadBoard(cand_pcb)
    for it in items_to_add:
        netname = it["net"]
        netinfo = board.FindNet(netname)
        if not netinfo:
            print(f"Error: Net {netname} not found!")
            return False
            
        if it["type"] == "track":
            t = pcbnew.PCB_TRACK(board)
            p1 = it["start"]
            p2 = it["end"]
            t.SetStart(pcbnew.VECTOR2I_MM(p1[0], p1[1]))
            t.SetEnd(pcbnew.VECTOR2I_MM(p2[0], p2[1]))
            t.SetWidth(pcbnew.FromMM(it.get("width", 0.15)))
            layer_id = board.GetLayerID(it.get("layer", "F.Cu"))
            t.SetLayer(layer_id)
            t.SetNetCode(netinfo.GetNetCode())
            board.Add(t)
        elif it["type"] == "via":
            v = pcbnew.PCB_VIA(board)
            pos = it["pos"]
            v.SetPosition(pcbnew.VECTOR2I_MM(pos[0], pos[1]))
            v_type_str = it.get("via_type", "through").lower()
            if v_type_str == "microvia":
                v.SetViaType(pcbnew.VIATYPE_MICROVIA)
                v.SetWidth(pcbnew.FromMM(it.get("size", 0.25)))
                v.SetDrill(pcbnew.FromMM(it.get("drill", 0.1)))
            elif v_type_str == "blind":
                v.SetViaType(pcbnew.VIATYPE_BLIND)
                v.SetWidth(pcbnew.FromMM(it.get("size", 0.35)))
                v.SetDrill(pcbnew.FromMM(it.get("drill", 0.15)))
            else:
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetWidth(pcbnew.FromMM(it.get("size", 0.4)))
                v.SetDrill(pcbnew.FromMM(it.get("drill", 0.15)))
            
            if "top_layer" in it and "bottom_layer" in it:
                l1 = board.GetLayerID(it["top_layer"])
                l2 = board.GetLayerID(it["bottom_layer"])
                v.SetLayerPair(l1, l2)
            v.SetNetCode(netinfo.GetNetCode())
            board.Add(v)
            
    board.Save(cand_pcb)
    
    # Refill zones and save
    refill_cmd = [KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", cand_pcb]
    subprocess.run(refill_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    c_err, c_viol, c_unconn, errs, uncs = run_drc(cand_pcb)
    print(f"[{op_id}] Candidate: {c_err} errors, {c_viol} violations, {c_unconn} unconnected")
    
    if c_err > b_err:
        print(f"[{op_id}] FAILED: {c_err - b_err} new errors introduced:")
        for e in errs[:5]:
            descs = [i.get("description", "") for i in e.get("items", [])]
            print("  ", e.get("type"), ":", " <-> ".join(descs))
        return False
        
    delta = b_unconn - c_unconn
    print(f"[{op_id}] Delta: -{delta} unconnected ({b_unconn} -> {c_unconn})")
    
    if promote and c_err == 0 and c_unconn < b_unconn:
        shutil.copy2(cand_pcb, PRIMARY_PCB)
        p_err, p_viol, p_unconn, _, _ = run_drc(PRIMARY_PCB)
        print(f"[{op_id}] Promoted! Primary verified: {p_err} errors, {p_unconn} unconnected")
        shutil.rmtree(staging_dir, ignore_errors=True)
        if commit_msg:
            subprocess.run(["git", "add", PRIMARY_PCB])
            subprocess.run(["git", "commit", "-m", commit_msg])
            print(f"[{op_id}] Committed: {commit_msg}")
        return True
    return False

if __name__ == "__main__":
    print("Test script ready.")
