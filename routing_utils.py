import pcbnew, math, json, os, subprocess, shutil, uuid

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PRIMARY_PCB = "Jetson-AI-Cam-CopperPilot.kicad_pcb"
STEM = "Jetson-AI-Cam-CopperPilot"

def get_drc(pcb_path=PRIMARY_PCB, rpt_path=None):
    if rpt_path is None:
        rpt_path = ".copperpilot/tmp/drc_report.json"
    os.makedirs(os.path.dirname(rpt_path), exist_ok=True)
    cmd = [KICAD_CLI, "pcb", "drc", "--format", "json", "-o", rpt_path, pcb_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(rpt_path) as f:
        d = json.load(f)
    violations = d.get("violations", [])
    errors = [v for v in violations if v.get("severity") == "error"]
    unconn = d.get("unconnected_items", [])
    return errors, violations, unconn

def is_via_clear(board, vx_mm, vy_mm, target_net, via_size=0.4, clearance=0.16):
    vx_nm = int(vx_mm * 1e6)
    vy_nm = int(vy_mm * 1e6)
    via_r_nm = int(via_size * 0.5 * 1e6)
    clear_nm = int(clearance * 1e6)
    req_nm = via_r_nm + clear_nm
    
    for t in board.GetTracks():
        if t.GetNetname() == target_net:
            continue
        p1 = t.GetStart()
        p2 = t.GetEnd()
        is_via = isinstance(t, pcbnew.PCB_VIA)
        w = t.GetWidth(pcbnew.F_Cu) if is_via else t.GetWidth()
        minx = min(p1.x, p2.x) - w//2 - req_nm
        maxx = max(p1.x, p2.x) + w//2 + req_nm
        miny = min(p1.y, p2.y) - w//2 - req_nm
        maxy = max(p1.y, p2.y) + w//2 + req_nm
        if not (minx <= vx_nm <= maxx and miny <= vy_nm <= maxy):
            continue
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        l_sq = dx*dx + dy*dy
        if l_sq == 0:
            dist = math.hypot(vx_nm - p1.x, vy_nm - p1.y)
        else:
            u = max(0.0, min(1.0, ((vx_nm - p1.x)*dx + (vy_nm - p1.y)*dy) / l_sq))
            dist = math.hypot(vx_nm - (p1.x + u*dx), vy_nm - (p1.y + u*dy))
        if dist < (req_nm + w//2):
            return False
            
    for p in board.GetPads():
        if p.GetNetname() == target_net:
            continue
        bb = p.GetBoundingBox()
        if not (bb.GetX() - req_nm <= vx_nm <= bb.GetRight() + req_nm and
                bb.GetY() - req_nm <= vy_nm <= bb.GetBottom() + req_nm):
            continue
        pos = p.GetPosition()
        sz = p.GetSize()
        hx = sz.x // 2
        hy = sz.y // 2
        dx = max(0, abs(vx_nm - pos.x) - hx)
        dy = max(0, abs(vy_nm - pos.y) - hy)
        dist = math.hypot(dx, dy)
        if dist < req_nm:
            return False
            
    return True

def find_clear_vias(board, target_net, cx, cy, radius=3.0, step=0.05, via_size=0.4, clearance=0.16):
    req_nm = int((via_size * 0.5 + clearance) * 1e6)
    roi_min_x = int((cx - radius) * 1e6) - req_nm - int(0.5*1e6)
    roi_max_x = int((cx + radius) * 1e6) + req_nm + int(0.5*1e6)
    roi_min_y = int((cy - radius) * 1e6) - req_nm - int(0.5*1e6)
    roi_max_y = int((cy + radius) * 1e6) + req_nm + int(0.5*1e6)

    filtered_tracks = []
    for t in board.GetTracks():
        if t.GetNetname() == target_net:
            continue
        p1 = t.GetStart()
        p2 = t.GetEnd()
        is_via = isinstance(t, pcbnew.PCB_VIA)
        w = t.GetWidth(pcbnew.F_Cu) if is_via else t.GetWidth()
        if max(p1.x, p2.x) + w//2 < roi_min_x or min(p1.x, p2.x) - w//2 > roi_max_x:
            continue
        if max(p1.y, p2.y) + w//2 < roi_min_y or min(p1.y, p2.y) - w//2 > roi_max_y:
            continue
        filtered_tracks.append((p1, p2, w))

    filtered_pads = []
    for p in board.GetPads():
        if p.GetNetname() == target_net:
            continue
        bb = p.GetBoundingBox()
        if bb.GetRight() < roi_min_x or bb.GetX() > roi_max_x:
            continue
        if bb.GetBottom() < roi_min_y or bb.GetY() > roi_max_y:
            continue
        pos = p.GetPosition()
        sz = p.GetSize()
        filtered_pads.append((pos.x, pos.y, sz.x // 2, sz.y // 2))

    results = []
    r_steps = int(radius / step)
    for ix in range(-r_steps, r_steps + 1):
        for iy in range(-r_steps, r_steps + 1):
            x = cx + ix * step
            y = cy + iy * step
            d = math.hypot(x - cx, y - cy)
            if d > radius:
                continue
            
            vx_nm = int(x * 1e6)
            vy_nm = int(y * 1e6)
            clear = True
            for p1, p2, w in filtered_tracks:
                minx = min(p1.x, p2.x) - w//2 - req_nm
                maxx = max(p1.x, p2.x) + w//2 + req_nm
                miny = min(p1.y, p2.y) - w//2 - req_nm
                maxy = max(p1.y, p2.y) + w//2 + req_nm
                if not (minx <= vx_nm <= maxx and miny <= vy_nm <= maxy):
                    continue
                dx = p2.x - p1.x
                dy = p2.y - p1.y
                l_sq = dx*dx + dy*dy
                if l_sq == 0:
                    dist = math.hypot(vx_nm - p1.x, vy_nm - p1.y)
                else:
                    u = max(0.0, min(1.0, ((vx_nm - p1.x)*dx + (vy_nm - p1.y)*dy) / l_sq))
                    dist = math.hypot(vx_nm - (p1.x + u*dx), vy_nm - (p1.y + u*dy))
                if dist < (req_nm + w//2):
                    clear = False
                    break
            if not clear:
                continue
            for px, py, hx, hy in filtered_pads:
                dx = max(0, abs(vx_nm - px) - hx)
                dy = max(0, abs(vy_nm - py) - hy)
                dist = math.hypot(dx, dy)
                if dist < req_nm:
                    clear = False
                    break
            if clear:
                results.append((round(x, 4), round(y, 4), round(d, 4)))

    results.sort(key=lambda item: item[2])
    return results

def is_seg_clear(board, x1_mm, y1_mm, x2_mm, y2_mm, layer_name, target_net, width=0.15, clearance=0.15):
    # Check clearance of a segment on a specific layer
    x1_nm = int(x1_mm * 1e6)
    y1_nm = int(y1_mm * 1e6)
    x2_nm = int(x2_mm * 1e6)
    y2_nm = int(y2_mm * 1e6)
    w_nm = int(width * 1e6)
    clear_nm = int(clearance * 1e6)
    req_nm = w_nm//2 + clear_nm
    
    layer_id = board.GetLayerID(layer_name)
    
    # Check against tracks on this layer
    for t in board.GetTracks():
        if t.GetNetname() == target_net:
            continue
        if t.IsOnLayer(layer_id):
            p1 = t.GetStart()
            p2 = t.GetEnd()
            is_via = isinstance(t, pcbnew.PCB_VIA)
            tw = t.GetWidth(pcbnew.F_Cu) if is_via else t.GetWidth()
            # test segment-to-segment distance
            # approximate with sample points along new segment
            seg_len = math.hypot(x2_nm - x1_nm, y2_nm - y1_nm)
            steps = max(2, int(seg_len / (w_nm//2)))
            for step in range(steps + 1):
                sx = x1_nm + (x2_nm - x1_nm) * step / steps
                sy = y1_nm + (y2_nm - y1_nm) * step / steps
                # dist to track
                dx = p2.x - p1.x
                dy = p2.y - p1.y
                l_sq = dx*dx + dy*dy
                if l_sq == 0:
                    dist = math.hypot(sx - p1.x, sy - p1.y)
                else:
                    u = max(0.0, min(1.0, ((sx - p1.x)*dx + (sy - p1.y)*dy) / l_sq))
                    dist = math.hypot(sx - (p1.x + u*dx), sy - (p1.y + u*dy))
                if dist < (req_nm + tw//2):
                    return False
                    
    # Check against pads on this layer
    for p in board.GetPads():
        if p.GetNetname() == target_net:
            continue
        if p.IsOnLayer(layer_id):
            pos = p.GetPosition()
            sz = p.GetSize()
            hx = sz.x // 2
            hy = sz.y // 2
            # distance from sample points on segment to rectangle
            steps = max(2, int(seg_len / (w_nm//2)))
            for step in range(steps + 1):
                sx = x1_nm + (x2_nm - x1_nm) * step / steps
                sy = y1_nm + (y2_nm - y1_nm) * step / steps
                dx = max(0, abs(sx - pos.x) - hx)
                dy = max(0, abs(sy - pos.y) - hy)
                dist = math.hypot(dx, dy)
                if dist < req_nm:
                    return False
                
    return True

