#!/usr/bin/env python3
"""
Automated silkscreen optimization:
1. Fixes edge clearance violations by pulling back connector silkscreen and boundary text.
2. Resolves silkscreen overlaps between reference text and graphical lines.
"""

import sys, os, pcbnew

def fix_silkscreen(pcb_path):
    abs_pcb = os.path.abspath(pcb_path)
    board = pcbnew.LoadBoard(abs_pcb)
    if not board:
        print(f"Error loading {abs_pcb}")
        return False

    # 1. Edge text fields: J4 and C84
    j4 = board.FindFootprintByReference("J4")
    if j4:
        ref_f = j4.Reference()
        ref_f.SetPosition(pcbnew.VECTOR2I(int(164.5 * 1e6), ref_f.GetPosition().y))

    c84 = board.FindFootprintByReference("C84")
    if c84:
        ref_f = c84.Reference()
        ref_f.SetPosition(pcbnew.VECTOR2I(ref_f.GetPosition().x, int(78.5 * 1e6)))

    # 2. J15 connector outer mechanical edge outlines -> move to F.Fab
    j15 = board.FindFootprintByReference("J15")
    if j15:
        for g in j15.GraphicalItems():
            if g.GetLayerName() == "F.Silkscreen":
                sp, ep = g.GetStart(), g.GetEnd()
                sx, sy = pcbnew.ToMM(sp.x), pcbnew.ToMM(sp.y)
                ex, ey = pcbnew.ToMM(ep.x), pcbnew.ToMM(ep.y)
                if sx < 90.0 or ex < 90.0 or sx > 167.3 or ex > 167.3:
                    g.SetLayer(board.GetLayerID("F.Fab"))

    # 3. Text A and B over circles
    for item in board.GetDrawings():
        if item.GetClass() == "PCB_TEXT" and item.GetLayerName() == "F.Silkscreen":
            txt = item.GetText()
            if txt in ["A", "B"]:
                pos = item.GetPosition()
                item.SetPosition(pcbnew.VECTOR2I(pos.x, int(pos.y - 1.8 * 1e6)))

    # 4. Reference designator text collisions with component outline segments
    # Offset reference designator for identified collision footprints
    collide_refs = {
        "IC1": (0.0, 1.2),
        "D15": (0.0, 1.0),
        "R68": (0.0, -0.8),
        "T8": (0.0, 0.8),
        "R55": (0.0, 0.8),
        "L9": (0.0, -1.0),
        "L1": (0.0, 1.2),
        "R108": (0.0, 0.8),
        "R122": (0.0, -0.8),
        "IC3": (0.0, -1.2),
        "T5": (0.0, 0.8),
        "C39": (0.0, 0.8),
        "R15": (0.0, -0.8),
        "IC15": (0.0, 1.2),
        "D1": (0.0, 0.8),
        "D3": (0.0, 0.8),
        "D5": (0.0, 0.8),
        "D7": (0.0, 0.8),
        "D9": (0.0, 0.8),
        "D11": (0.0, 0.8),
        "D13": (0.0, 0.8),
    }

    for ref, (dx, dy) in collide_refs.items():
        fp = board.FindFootprintByReference(ref)
        if fp:
            rf = fp.Reference()
            pos = rf.GetPosition()
            rf.SetPosition(pcbnew.VECTOR2I(int(pos.x + dx * 1e6), int(pos.y + dy * 1e6)))

    board.Save(abs_pcb)
    print("Silkscreen optimization complete.")
    return True

if __name__ == "__main__":
    pcb = sys.argv[1] if len(sys.argv) > 1 else "Jetson-AI-Cam-CopperPilot.kicad_pcb"
    fix_silkscreen(pcb)
