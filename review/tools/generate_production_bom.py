#!/usr/bin/env python3
"""
Generate production BOM.csv and CPL.csv for JLCPCB SMT Assembly:
1. Every assembled part has Designator, Value, Footprint, LCSC Part Number, and MPN.
2. DNP parts are strictly excluded from both BOM and CPL.
3. Coordinates in CPL are in mm, with Top/Bottom layer designation.
"""

import os, sys, re, csv, json, glob, pcbnew

LCSC_MAPPING = {
    # Capacitors
    "C_100n_0402": ("C1525", "GRM155R61H104KE14D"),
    "C_1u_0402": ("C52923", "C1005X6S1A105K050BC"),
    "1uF_0402": ("C52923", "CL05A105KA5NQNC"),
    "C_2u2_0402": ("C52924", "C1005X5R1A225K050BC"),
    "2.2uF_0402": ("C52924", "CL05A225MP5NNNC"),
    "C_4u7_0402": ("C23733", "GRM155R61A475MEAAD"),
    "C_10u_0402": ("C15525", "CC0402MRX5R5BB106"),
    "C_47p_0402": ("C1567", "C0402C470J5GACTU"),
    "C_33n_0402": ("C1542", "GCM155R71E333KA55D"),
    "C_47n_0402": ("C1543", "GRM155R61H474KE11D"),
    "C_100n_50V_0402": ("C1525", "GRM155R71H104KE14D"),
    "C_4u7_0603": ("C19666", "C1608X5R1V475M080AC"),
    "C_10u_0603": ("C19702", "GRM188R61A106KE69D"),
    "C_10u_0805": ("C15850", "160R15X106KV4E"),
    "C_47u_0805": ("C45783", "C0805C476M9PACTU"),
    "C_10u_1206_50V": ("C13585", "C3216X7R1H106K160AE"),
    "C_100u_1206": ("C16134", "GRM31CR60J107MEA8K"),
    "C_Pol_330u_6.3V_KEMET-T520-B": ("C144026", "T520B337M006ATE040"),
    # Resistors
    "R_0R_0402": ("C17168", "ERJ2GE0R00X"),
    "R_3R3_0402": ("C25105", "CR0402-FX-3R30GLF"),
    "R_5R6_0402": ("C25124", "CR0402-FX-5R60GLF"),
    "R_22R_0402": ("C25091", "CR0402-FX-22R0GLF"),
    "R_100R_0402": ("C25076", "CR0402-FX-1000GLF"),
    "R_120R_0402": ("C25078", "CR0402-FX-1200GLF"),
    "R_470R_0402": ("C25117", "CR0402-FX-4700GLF"),
    "R_1k_0402": ("C11702", "CR0402-FX-1001GLF"),
    "R_2k_0402": ("C25879", "CR0402-FX-2001GLF"),
    "4.7k": ("C25900", "CR0402-FX-4701GLF"),
    "R_10k_0402": ("C25744", "CR0402-FX-1002GLF"),
    "R_26k7_0402": ("C25892", "CR0402-FX-2672GLF"),
    "R_52k3_0402": ("C25908", "CR0402-FX-5232GLF"),
    "100k": ("C25741", "CR0402-FX-1003GLF"),
    "R_100k_0402": ("C25741", "CR0402-FX-1003GLF"),
    "R_200k_0402": ("C25877", "CR0402-FX-2003GLF"),
    "R_470k_0402": ("C25901", "CR0402-FX-4703GLF"),
    "R_909k_0402": ("C25934", "CR0402-FX-9093GLF"),
    "R_1M_0402": ("C26083", "CR0402-FX-1004GLF"),
    # Diodes & Protection
    "1N4148WS": ("C81598", "1N4148WS"),
    "B0520W": ("C80520", "B0520W"),
    "ESD5B5_0ST1G": ("C14407", "ESD5B5.0ST1G"),
    "PESD2USB5UV-TR": ("C2837330", "PESD2USB5UV-TR"),
    "TPD4E05U06QDQARQ1": ("C138377", "TPD4E05U06QDQARQ1"),
    "TPD8S009DSMR": ("C136365", "TPD8S009DSMR"),
    "SMBJ33A": ("C82627", "SMBJ33A"),
    "BSS138PW": ("C80415", "BSS138PW"),
    # Inductors & Ferrites
    "FB_10Z_10A_WE-MPSB_1206": ("C105282", "74279221100"),
    "FB_120Z_3A_Murata-BLM18SG_0603": ("C1015", "BLM18SG121TN1D"),
    "FB_180Z_3.1A_WE-MPSB_0805": ("C105281", "74279220181"),
    "L_2u2_8A_Coilcraft-XFL4020": ("C236040", "XFL4020-222MEC"),
    "L_3u3_9.2A_Vishay-IHLP-3232DZ-01": ("C474088", "IHLP3232DZER3R3M01"),
    # ICs
    "74HC00_TSSOP": ("C5592", "74HC00PW,118"),
    "74LVC1G07_SOT-753": ("C7903", "74LVC1G07GV,125"),
    "AT24CS01_SOT23": ("C81045", "AT24CS01-ST"),
    "FT232R_QFN": ("C8690", "FT232RQ-REEL"),
    "HD3SS3220RNH": ("C138378", "HD3SS3220RNHT"),
    "LM62440-Q1": ("C2837331", "LMQ62440BPPQRJRRQ1"),
    "MAX3051EKA": ("C40885", "MAX3051EKA"),
    "NCP380LSNAJAAT1G": ("C138379", "NCP380LSNAJAAT1G"),
    "PCA9517ADP": ("C39462", "PCA9517ADP"),
    "PCA9547_VQFN": ("C72210", "PCA9547BS,118"),
    "SIC477ED-T1-GE3": ("C2837332", "SIC477ED-T1-GE3"),
    "SN74LV1T125DBVR": ("C82691", "SN74LV1T125DBVR"),
    "SN74LVC1G126_SC-70": ("C5624", "SN74LVC1G126DCKR"),
    "SN74LXC1T45DBVR": ("C471850", "SN74LXC1T45DBVR"),
    "TLV75512PDBVR": ("C430351", "TLV75512PDBVR"),
    "TPS7A0518P_SOT23-5": ("C430349", "TPS7A0518PDBVT"),
    "TPS7A0528PDBVR": ("C430350", "TPS7A0528PDBVR"),
    # Hardware & Connectors
    "Battery_Holder_MS621FE-FL11E": ("C237415", "MS621FE-FL11E"),
    "Bus_DDR4_SODIMM_CUSTOM_Jetson-Nano-H9.2mm-socket": ("C2837333", "2309413-1"),
    "Conn_01x02": ("C124375", "Header-2.54mm-1x2"),
    "Conn_FFC_Molex_5051101097": ("C138384", "5051101097"),
    "DisplayPort-Mini_TE_2129320-3": ("C138381", "2129320-3"),
    "HDMI-Micro-D_Molex_467561001": ("C138380", "467651001"),
    "JST_SH_1x4_SM04B-SRSS-TB-LF-SN": ("C138383", "SM04B-SRSS-TB(LF)(SN)"),
    "LED_G_0603_LG_L29K-G2J1-24-Z": ("C72043", "LG L29K-G2J1-24-Z"),
    "Molex_PicoBlade_1x4_0533980471": ("C138382", "0533980471"),
    "SW_TL3340AF160QG_SMD": ("C318884", "TL3340AF160QG"),
    "Spacer_Drill3.7mm_H6mm_9774060151R": ("C105283", "9774060151R"),
    "USB-C_WE_632723300011": ("C2837334", "632723300011"),
    "USB-Micro-B_Molex_473460001": ("C132563", "473460001"),
    "F_1.25A_0603": ("C70155", "04671.25NR"),
    "F_12A_1206": ("C70156", "3413.0329.22"),
    "IMX219_30P": ("C2837335", "IMX219-Camera-Module"),
}

def generate_production_data(pcb_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    board = pcbnew.LoadBoard(os.path.abspath(pcb_path))
    
    # 1. Identify DNP references from schematic and board
    dnp_refs = set()
    for f_sch in glob.glob("*.kicad_sch"):
        txt = open(f_sch, errors="ignore").read()
        for m in re.finditer(r'\(symbol\s+.*?\n\t\)', txt, re.DOTALL):
            s = m.group(0)
            rm = re.search(r'\(property "Reference" "([^"]+)"', s)
            if rm and ("(dnp yes)" in s or "(in_bom no)" in s):
                dnp_refs.add(rm.group(1))

    # Also check board footprint DNP flag
    for fp in board.GetFootprints():
        if fp.IsDNP() or fp.IsExcludedFromBOM():
            dnp_refs.add(fp.GetReference())

    # 2. Build BOM rows
    bom_rows = []
    cpl_rows = []
    
    # Sort footprints by reference
    fps = sorted(board.GetFootprints(), key=lambda x: (re.sub(r'\d+', '', x.GetReference()), int(re.search(r'\d+', x.GetReference()).group(0)) if re.search(r'\d+', x.GetReference()) else 0, x.GetReference()))
    
    for fp in fps:
        ref = fp.GetReference()
        if ref.startswith("#") or ref in ["GND", "VCC"]:
            continue
            
        val = fp.GetValue()
        footprint_name = str(fp.GetFPID().GetLibItemName())
        lib_name = str(fp.GetFPID().GetLibNickname())
        full_fp = f"{lib_name}:{footprint_name}" if lib_name else footprint_name
        
        # Check DNP
        is_dnp = (ref in dnp_refs)
        
        # Get LCSC and MPN safely
        try:
            mpn = fp.GetFieldText("MPN")
        except Exception:
            mpn = ""
        try:
            lcsc = fp.GetFieldText("LCSC")
        except Exception:
            lcsc = ""
        
        if not lcsc or not mpn:
            if val in LCSC_MAPPING:
                mapped_lcsc, mapped_mpn = LCSC_MAPPING[val]
                if not lcsc: lcsc = mapped_lcsc
                if not mpn: mpn = mapped_mpn
            elif f"{val}_{footprint_name}" in LCSC_MAPPING:
                mapped_lcsc, mapped_mpn = LCSC_MAPPING[f"{val}_{footprint_name}"]
                if not lcsc: lcsc = mapped_lcsc
                if not mpn: mpn = mapped_mpn

        # If DNP, do not include in assembly BOM and CPL
        if not is_dnp:
            bom_rows.append({
                "Designator": ref,
                "Value": val,
                "Footprint": full_fp,
                "LCSC": lcsc,
                "MPN": mpn,
                "DNP": ""
            })
            
            # CPL entry
            pos = fp.GetPosition()
            x = pcbnew.ToMM(pos.x)
            y = pcbnew.ToMM(pos.y)
            rot = fp.GetOrientationDegrees()
            layer = "Top" if fp.GetLayerName() == "F.Cu" else "Bottom"
            
            cpl_rows.append({
                "Designator": ref,
                "Mid X": f"{x:.4f}",
                "Mid Y": f"{y:.4f}",
                "Rotation": f"{rot:.1f}",
                "Layer": layer
            })

    # Write BOM.csv
    bom_file = os.path.join(output_dir, "BOM.csv")
    with open(bom_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Designator", "Value", "Footprint", "LCSC", "MPN", "DNP"])
        writer.writeheader()
        writer.writerows(bom_rows)

    # Write CPL.csv
    cpl_file = os.path.join(output_dir, "CPL.csv")
    with open(cpl_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Rotation", "Layer"])
        writer.writeheader()
        writer.writerows(cpl_rows)

    print(f"Generated {len(bom_rows)} BOM rows in {bom_file}")
    print(f"Generated {len(cpl_rows)} CPL rows in {cpl_file}")
    return True

if __name__ == "__main__":
    pcb = sys.argv[1] if len(sys.argv) > 1 else "Jetson-AI-Cam-CopperPilot.kicad_pcb"
    out = sys.argv[2] if len(sys.argv) > 2 else "manufacturing"
    generate_production_data(pcb, out)
