#!/usr/bin/env python3
"""
Synchronize schematic-to-PCB parity:
1. Updates component properties (Value, Datasheet, Description, Tolerance, MPN) from schematic.
2. Synchronizes DNP and ExcludeFromBOM attributes.
3. Updates pad net assignments on PCB to match schematic netlist.
"""

import sys, os, re, json, glob, subprocess, pcbnew

def sync_schematic_parity(pcb_path, sch_path, netlist_path=None):
    if netlist_path is None:
        netlist_path = "/tmp/schematic_netlist.net"
    
    # Export schematic netlist
    cmd = ["kicad-cli", "sch", "export", "netlist", "-o", netlist_path, sch_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not os.path.exists(netlist_path):
        print(f"Error: Netlist export failed to {netlist_path}")
        return False
        
    with open(netlist_path, "r", errors="ignore") as f:
        txt = f.read()

    # 1. Parse DNP and Exclude from BOM directly from schematic sheets
    dnp_refs = set()
    ex_bom_refs = set()
    for f_sch in glob.glob("*.kicad_sch"):
        sch_txt = open(f_sch, errors="ignore").read()
        symbols = re.findall(r'\(symbol\s+.*?\n\t\)', sch_txt, re.DOTALL)
        for s in symbols:
            ref_m = re.search(r'\(property "Reference" "([^"]+)"', s)
            if ref_m:
                ref = ref_m.group(1)
                if "(dnp yes)" in s:
                    dnp_refs.add(ref)
                if "(in_bom no)" in s:
                    ex_bom_refs.add(ref)

    # 2. Parse components from netlist
    comps_txt = txt[txt.find("(components"):txt.find("(nets")]
    comp_blocks = re.findall(r'\(comp\s+\(ref\s+"([^"]+)"\)(.*?)\n\t\t\)', comps_txt, re.DOTALL)
    
    comp_data = {}
    for ref, block in comp_blocks:
        val_m = re.search(r'\(value\s+"([^"]*)"\)', block)
        val = val_m.group(1) if val_m else ""
        ds_m = re.search(r'\(datasheet\s+"([^"]*)"\)', block)
        ds = ds_m.group(1) if ds_m else ""
        desc_m = re.search(r'\(field\s+\(name\s+"Description"\)\s+"([^"]*)"\)', block)
        desc = desc_m.group(1) if desc_m else ""
        tol_m = re.search(r'\(field\s+\(name\s+"Tolerance"\)\s+"([^"]*)"\)', block)
        tol = tol_m.group(1) if tol_m else ""
        mpn_m = re.search(r'\(field\s+\(name\s+"MPN"\)\s+"([^"]*)"\)', block)
        mpn = mpn_m.group(1) if mpn_m else ""
        comp_data[ref] = {"value": val, "datasheet": ds, "description": desc, "tolerance": tol, "mpn": mpn}

    # 3. Parse nets: map (ref, pin) -> netname
    nets_txt = txt[txt.find("(nets"):]
    net_blocks = re.findall(r'\(net\s+\(code\s+"[0-9]+"\)\s+\(name\s+"([^"]+)"\)(.*?)\n\t\t\)', nets_txt, re.DOTALL)
    
    pin_to_net = {}
    for netname, nblock in net_blocks:
        nodes = re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)', nblock)
        for r, p in nodes:
            pin_to_net[(r, p)] = netname

    # 4. Load PCB
    abs_pcb = os.path.abspath(pcb_path)
    board = pcbnew.LoadBoard(abs_pcb)
    if not board:
        print(f"Error: failed to load board from {abs_pcb}")
        return False
        
    updated_fields = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Set DNP and ExcludeFromBOM attributes
        fp.SetDNP(ref in dnp_refs)
        fp.SetExcludedFromBOM(ref in ex_bom_refs)
        
        if ref in comp_data:
            data = comp_data[ref]
            if data["value"] and fp.GetValue() != data["value"]:
                fp.SetValue(data["value"])
                updated_fields += 1
            # Always sync Datasheet, Description, Tolerance, MPN
            fp.SetField("Datasheet", data["datasheet"])
            fp.SetField("Description", data["description"])
            fp.SetField("Tolerance", data["tolerance"])
            if data["mpn"]:
                fp.SetField("MPN", data["mpn"])
            updated_fields += 4

    # 5. Update pad nets from schematic pin_to_net mapping
    updated_pads = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            p_num = pad.GetName()
            target_net = pin_to_net.get((ref, p_num))
            if target_net:
                # Normalize escape backslashes e.g. /Supply/~{PWR_SET}
                clean_target = target_net.replace(r"\~", "~").replace(r"\\~", "~")
                current_clean = pad.GetNetname().replace(r"\~", "~").replace(r"\\~", "~")
                if current_clean != clean_target or pad.GetNetname() != target_net:
                    netinfo = board.FindNet(target_net)
                    if not netinfo:
                        netinfo = board.FindNet(clean_target)
                    if not netinfo:
                        netinfo = pcbnew.NETINFO_ITEM(board, target_net)
                        board.Add(netinfo)
                    pad.SetNet(netinfo)
                    updated_pads += 1

    # Reconcile escaped net names
    for code, net in board.GetNetsByName().items():
        if "PWR_SET" in net.GetNetname():
            net.SetNetname(r"/Supply/\~{PWR_SET}")

    board.Save(abs_pcb)
    print(f"Parity sync complete: {updated_fields} fields updated, {updated_pads} pad nets updated.")
    return True

if __name__ == "__main__":
    pcb = sys.argv[1] if len(sys.argv) > 1 else "Jetson-AI-Cam-CopperPilot.kicad_pcb"
    sch = sys.argv[2] if len(sys.argv) > 2 else "Jetson-AI-Cam-CopperPilot.kicad_sch"
    sync_schematic_parity(pcb, sch)
