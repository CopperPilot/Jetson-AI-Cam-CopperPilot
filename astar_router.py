import pcbnew
import math
import heapq
import time

class AStarRouter:
    def __init__(self, board_path, net_name, bbox, grid_step=0.25, clearance=0.14, track_width=0.15, via_size=0.45, via_drill=0.20):
        self.board = pcbnew.LoadBoard(board_path)
        self.net_name = net_name
        self.net = self.board.FindNet(net_name)
        if not self.net:
            raise ValueError(f"Net {net_name} not found")
        self.netcode = self.net.GetNetCode()
        
        self.min_x, self.min_y, self.max_x, self.max_y = bbox
        self.step = grid_step
        self.clearance = clearance
        self.track_w = track_width
        self.via_size = via_size
        self.via_drill = via_drill
        self.uvia_size = 0.25
        
        self.cols = int(math.ceil((self.max_x - self.min_x) / self.step)) + 1
        self.rows = int(math.ceil((self.max_y - self.min_y) / self.step)) + 1

        self.microvia_spans = {
            ('F.Cu', 'In2_SINGAL.Cu'): ['F.Cu', 'In1_5V0_SYS_VIN.Cu', 'In2_SINGAL.Cu'],
            ('In2_SINGAL.Cu', 'F.Cu'): ['F.Cu', 'In1_5V0_SYS_VIN.Cu', 'In2_SINGAL.Cu'],
            ('F.Cu', 'In3_SIGNAL.Cu'): ['F.Cu', 'In1_5V0_SYS_VIN.Cu', 'In2_SINGAL.Cu', 'In3_SIGNAL.Cu'],
            ('In3_SIGNAL.Cu', 'F.Cu'): ['F.Cu', 'In1_5V0_SYS_VIN.Cu', 'In2_SINGAL.Cu', 'In3_SIGNAL.Cu'],
            ('B.Cu', 'In5_3V3_SYS_SIGNAL.Cu'): ['B.Cu', 'In6_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu'],
            ('In5_3V3_SYS_SIGNAL.Cu', 'B.Cu'): ['B.Cu', 'In6_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu'],
            ('B.Cu', 'In3_SIGNAL.Cu'): ['B.Cu', 'In6_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu', 'In4_GND.Cu', 'In3_SIGNAL.Cu'],
            ('In3_SIGNAL.Cu', 'B.Cu'): ['B.Cu', 'In6_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu', 'In4_GND.Cu', 'In3_SIGNAL.Cu'],
            ('In2_SINGAL.Cu', 'B.Cu'): ['In2_SINGAL.Cu', 'In3_SIGNAL.Cu', 'In4_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu', 'In6_GND.Cu', 'B.Cu'],
            ('B.Cu', 'In2_SINGAL.Cu'): ['In2_SINGAL.Cu', 'In3_SIGNAL.Cu', 'In4_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu', 'In6_GND.Cu', 'B.Cu'],
        }

    def to_grid(self, x, y):
        c = int(round((x - self.min_x) / self.step))
        r = int(round((y - self.min_y) / self.step))
        return max(0, min(self.cols - 1, c)), max(0, min(self.rows - 1, r))

    def to_world(self, c, r):
        return round(self.min_x + c * self.step, 4), round(self.min_y + r * self.step, 4)

    def build_obstacle_grid(self, search_layers):
        all_cu_layers = ['F.Cu', 'In1_5V0_SYS_VIN.Cu', 'In2_SINGAL.Cu', 'In3_SIGNAL.Cu', 'In4_GND.Cu', 'In5_3V3_SYS_SIGNAL.Cu', 'In6_GND.Cu', 'B.Cu']
        blocked = {l: set() for l in all_cu_layers}
        blocked_through_via = set()
        blocked_uvia = {l: set() for l in all_cu_layers}

        req_dist = (self.track_w / 2.0) + self.clearance
        via_req_dist = (self.via_size / 2.0) + self.clearance
        uvia_req_dist = (self.uvia_size / 2.0) + self.clearance
        
        for tr in self.board.GetTracks():
            if tr.GetNetCode() == self.netcode:
                continue
            is_via = (tr.GetClass() == 'PCB_VIA')
            if is_via:
                vx = pcbnew.ToMM(tr.GetPosition().x)
                vy = pcbnew.ToMM(tr.GetPosition().y)
                vr = (pcbnew.ToMM(tr.GetWidth(tr.TopLayer())) / 2.0) if hasattr(tr, 'GetWidth') else 0.2
                tot_r_track = vr + req_dist
                tot_r_via = vr + via_req_dist
                tot_r_uvia = vr + uvia_req_dist
                
                max_r = max(tot_r_track, tot_r_via, tot_r_uvia)
                if not (self.min_x - max_r <= vx <= self.max_x + max_r and self.min_y - max_r <= vy <= self.max_y + max_r):
                    continue
                
                c_min_v = max(0, int(math.floor((vx - tot_r_via - self.min_x) / self.step)))
                c_max_v = min(self.cols - 1, int(math.ceil((vx + tot_r_via - self.min_x) / self.step)))
                r_min_v = max(0, int(math.floor((vy - tot_r_via - self.min_y) / self.step)))
                r_max_v = min(self.rows - 1, int(math.ceil((vy + tot_r_via - self.min_y) / self.step)))
                for c in range(c_min_v, c_max_v + 1):
                    for r in range(r_min_v, r_max_v + 1):
                        wx, wy = self.to_world(c, r)
                        if (wx - vx)**2 + (wy - vy)**2 <= tot_r_via**2:
                            blocked_through_via.add((c, r))
                
                for l in all_cu_layers:
                    lid = self.board.GetLayerID(l)
                    if tr.IsOnLayer(lid):
                        c_min = max(0, int(math.floor((vx - tot_r_track - self.min_x) / self.step)))
                        c_max = min(self.cols - 1, int(math.ceil((vx + tot_r_track - self.min_x) / self.step)))
                        r_min = max(0, int(math.floor((vy - tot_r_track - self.min_y) / self.step)))
                        r_max = min(self.rows - 1, int(math.ceil((vy + tot_r_track - self.min_y) / self.step)))
                        for c in range(c_min, c_max + 1):
                            for r in range(r_min, r_max + 1):
                                wx, wy = self.to_world(c, r)
                                if (wx - vx)**2 + (wy - vy)**2 <= tot_r_track**2:
                                    blocked[l].add((c, r))
                                if (wx - vx)**2 + (wy - vy)**2 <= tot_r_uvia**2:
                                    blocked_uvia[l].add((c, r))
            else:
                sp = tr.GetStart()
                ep = tr.GetEnd()
                sx, sy = pcbnew.ToMM(sp.x), pcbnew.ToMM(sp.y)
                ex, ey = pcbnew.ToMM(ep.x), pcbnew.ToMM(ep.y)
                tw = pcbnew.ToMM(tr.GetWidth())
                tot_r_track = (tw / 2.0) + req_dist
                tot_r_via = (tw / 2.0) + via_req_dist
                tot_r_uvia = (tw / 2.0) + uvia_req_dist
                
                max_r = max(tot_r_track, tot_r_via, tot_r_uvia)
                minx = min(sx, ex) - max_r
                maxx = max(sx, ex) + max_r
                miny = min(sy, ey) - max_r
                maxy = max(sy, ey) + max_r
                if not (minx <= self.max_x and maxx >= self.min_x and miny <= self.max_y and maxy >= self.min_y):
                    continue
                
                dx = ex - sx
                dy = ey - sy
                l_sq = dx*dx + dy*dy
                
                c_min_v = max(0, int(math.floor((min(sx, ex) - tot_r_via - self.min_x) / self.step)))
                c_max_v = min(self.cols - 1, int(math.ceil((max(sx, ex) + tot_r_via - self.min_x) / self.step)))
                r_min_v = max(0, int(math.floor((min(sy, ey) - tot_r_via - self.min_y) / self.step)))
                r_max_v = min(self.rows - 1, int(math.ceil((max(sy, ey) + tot_r_via - self.min_y) / self.step)))
                for c in range(c_min_v, c_max_v + 1):
                    for r in range(r_min_v, r_max_v + 1):
                        wx, wy = self.to_world(c, r)
                        if l_sq == 0:
                            dist_sq = (wx - sx)**2 + (wy - sy)**2
                        else:
                            u = max(0.0, min(1.0, ((wx - sx)*dx + (wy - sy)*dy) / l_sq))
                            dist_sq = (wx - (sx + u*dx))**2 + (wy - (sy + u*dy))**2
                        if dist_sq <= tot_r_via**2:
                            blocked_through_via.add((c, r))
                
                l_name = tr.GetLayerName()
                if l_name in all_cu_layers:
                    c_min = max(0, int(math.floor((min(sx, ex) - max(tot_r_track, tot_r_uvia) - self.min_x) / self.step)))
                    c_max = min(self.cols - 1, int(math.ceil((max(sx, ex) + max(tot_r_track, tot_r_uvia) - self.min_x) / self.step)))
                    r_min = max(0, int(math.floor((min(sy, ey) - max(tot_r_track, tot_r_uvia) - self.min_y) / self.step)))
                    r_max = min(self.rows - 1, int(math.ceil((max(sy, ey) + max(tot_r_track, tot_r_uvia) - self.min_y) / self.step)))
                    for c in range(c_min, c_max + 1):
                        for r in range(r_min, r_max + 1):
                            wx, wy = self.to_world(c, r)
                            if l_sq == 0:
                                dist_sq = (wx - sx)**2 + (wy - sy)**2
                            else:
                                u = max(0.0, min(1.0, ((wx - sx)*dx + (wy - sy)*dy) / l_sq))
                                dist_sq = (wx - (sx + u*dx))**2 + (wy - (sy + u*dy))**2
                            if dist_sq <= tot_r_track**2:
                                blocked[l_name].add((c, r))
                            if dist_sq <= tot_r_uvia**2:
                                blocked_uvia[l_name].add((c, r))
                            
        for p in self.board.GetPads():
            if p.GetNetCode() == self.netcode:
                continue
            bb = p.GetBoundingBox()
            px = pcbnew.ToMM(bb.GetCenter().x)
            py = pcbnew.ToMM(bb.GetCenter().y)
            hw_track = (pcbnew.ToMM(bb.GetWidth()) / 2.0) + req_dist
            hh_track = (pcbnew.ToMM(bb.GetHeight()) / 2.0) + req_dist
            hw_via = (pcbnew.ToMM(bb.GetWidth()) / 2.0) + via_req_dist
            hh_via = (pcbnew.ToMM(bb.GetHeight()) / 2.0) + via_req_dist
            hw_uvia = (pcbnew.ToMM(bb.GetWidth()) / 2.0) + uvia_req_dist
            hh_uvia = (pcbnew.ToMM(bb.GetHeight()) / 2.0) + uvia_req_dist
            
            c_min_v = max(0, int(math.floor((px - hw_via - self.min_x) / self.step)))
            c_max_v = min(self.cols - 1, int(math.ceil((px + hw_via - self.min_x) / self.step)))
            r_min_v = max(0, int(math.floor((py - hh_via - self.min_y) / self.step)))
            r_max_v = min(self.rows - 1, int(math.ceil((py + hh_via - self.min_y) / self.step)))
            for c in range(c_min_v, c_max_v + 1):
                for r in range(r_min_v, r_max_v + 1):
                    blocked_through_via.add((c, r))
                    
            pad_layers = [self.board.GetLayerName(lid) for lid in p.GetLayerSet().Seq()]
            c_min = max(0, int(math.floor((px - max(hw_track, hw_uvia) - self.min_x) / self.step)))
            c_max = min(self.cols - 1, int(math.ceil((px + max(hw_track, hw_uvia) - self.min_x) / self.step)))
            r_min = max(0, int(math.floor((py - max(hh_track, hh_uvia) - self.min_y) / self.step)))
            r_max = min(self.rows - 1, int(math.ceil((py + max(hh_track, hh_uvia) - self.min_y) / self.step)))
            for l in all_cu_layers:
                if l in pad_layers:
                    for c in range(c_min, c_max + 1):
                        for r in range(r_min, r_max + 1):
                            blocked[l].add((c, r))
                            blocked_uvia[l].add((c, r))
                                
        edge_clr = 0.5
        for c in range(self.cols):
            for r in range(self.rows):
                wx, wy = self.to_world(c, r)
                if wy <= 74.91 + edge_clr or wy >= 129.91 - edge_clr or wx <= 89.66 + edge_clr or wx >= 167.66 - edge_clr:
                    blocked_through_via.add((c, r))
                    for l in all_cu_layers:
                        blocked[l].add((c, r))
                        blocked_uvia[l].add((c, r))

        return blocked, blocked_through_via, blocked_uvia

    def find_path(self, start_pos, end_pos, search_layers, allowed_via_pairs=None, unblock_radius=0.0):
        if allowed_via_pairs is None:
            allowed_via_pairs = []
            for i in range(len(search_layers)):
                for j in range(i+1, len(search_layers)):
                    allowed_via_pairs.append((search_layers[i], search_layers[j]))
                    allowed_via_pairs.append((search_layers[j], search_layers[i]))
                    
        print(f"Building obstacle grid for {len(search_layers)} layers, bbox: {self.cols}x{self.rows}...")
        t0 = time.time()
        blocked, blocked_through_via, blocked_uvia = self.build_obstacle_grid(search_layers)
        print(f"Obstacle grid built in {time.time()-t0:.2f}s.")
        
        sc, sr = self.to_grid(start_pos[0], start_pos[1])
        ec, er = self.to_grid(end_pos[0], end_pos[1])
        start_node = (sc, sr, start_pos[2])
        end_node = (ec, er, end_pos[2])

        if unblock_radius > 0:
            ub_steps = int(math.ceil(unblock_radius / self.step))
            for dc in range(-ub_steps, ub_steps + 1):
                for dr in range(-ub_steps, ub_steps + 1):
                    if (dc*self.step)**2 + (dr*self.step)**2 <= unblock_radius**2:
                        blocked[start_pos[2]].discard((sc + dc, sr + dr))
                        blocked[end_pos[2]].discard((ec + dc, er + dr))
        
        pq = []
        heapq.heappush(pq, (0.0, 0.0, start_node))
        came_from = {}
        cost_so_far = {start_node: 0.0}
        
        def h(c, r, l):
            d_xy = math.hypot(c - ec, r - er) * self.step
            d_l = 0.0 if l == end_pos[2] else 4.0
            return d_xy + d_l
            
        dirs = [
            (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
            (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)
        ]
        
        found = False
        while pq:
            _, current_cost, current = heapq.heappop(pq)
            
            if current == end_node:
                found = True
                break
                
            cc, cr, cl = current
            
            for dc, dr, weight in dirs:
                nc, nr = cc + dc, cr + dr
                if 0 <= nc < self.cols and 0 <= nr < self.rows:
                    if (nc, nr) not in blocked[cl] or (nc, nr, cl) == end_node:
                        neighbor = (nc, nr, cl)
                        new_cost = current_cost + weight * self.step
                        if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                            cost_so_far[neighbor] = new_cost
                            priority = new_cost + h(nc, nr, cl)
                            heapq.heappush(pq, (priority, new_cost, neighbor))
                            came_from[neighbor] = current
                            
            for l1, l2 in allowed_via_pairs:
                if cl == l1:
                    pair = (l1, l2)
                    is_uvia = pair in self.microvia_spans
                    via_clear = True
                    if is_uvia:
                        for span_l in self.microvia_spans[pair]:
                            if (cc, cr) in blocked_uvia[span_l]:
                                via_clear = False
                                break
                    else:
                        if (cc, cr) in blocked_through_via:
                            via_clear = False
                            
                    if via_clear:
                        neighbor = (cc, cr, l2)
                        via_cost = 4.0 if is_uvia else 7.0
                        new_cost = current_cost + via_cost
                        if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                            cost_so_far[neighbor] = new_cost
                            priority = new_cost + h(cc, cr, l2)
                            heapq.heappush(pq, (priority, new_cost, neighbor))
                            came_from[neighbor] = current
                            
        if not found:
            print("No path found!")
            return []
            
        path = []
        curr = end_node
        while curr != start_node:
            path.append(curr)
            curr = came_from[curr]
        path.append(start_node)
        path.reverse()
        
        items = []
        cur_track_start = None
        cur_layer = path[0][2]
        cur_dir = None
        
        for i in range(len(path) - 1):
            c1, r1, l1 = path[i]
            c2, r2, l2 = path[i+1]
            
            if l1 != l2:
                if cur_track_start:
                    items.append({
                        'type': 'track',
                        'net': self.net_name,
                        'layer': cur_layer,
                        'start': self.to_world(cur_track_start[0], cur_track_start[1]),
                        'end': self.to_world(c1, r1),
                        'width': self.track_w
                    })
                    cur_track_start = None
                    cur_dir = None
                vx, vy = self.to_world(c1, r1)
                pair = (l1, l2)
                is_uvia = pair in self.microvia_spans
                if is_uvia:
                    items.append({
                        'type': 'via',
                        'net': self.net_name,
                        'pos': (vx, vy),
                        'via_type': 'microvia',
                        'size': self.uvia_size,
                        'drill': 0.1,
                        'top_layer': min(l1, l2),
                        'bottom_layer': max(l1, l2)
                    })
                else:
                    items.append({
                        'type': 'via',
                        'net': self.net_name,
                        'pos': (vx, vy),
                        'via_type': 'through',
                        'size': self.via_size,
                        'drill': getattr(self, 'via_drill', 0.20),
                        'top_layer': 'F.Cu',
                        'bottom_layer': 'B.Cu'
                    })
                cur_layer = l2
            else:
                step_dir = (c2 - c1, r2 - r1)
                if cur_track_start is None:
                    cur_track_start = (c1, r1)
                    cur_dir = step_dir
                elif step_dir != cur_dir:
                    items.append({
                        'type': 'track',
                        'net': self.net_name,
                        'layer': cur_layer,
                        'start': self.to_world(cur_track_start[0], cur_track_start[1]),
                        'end': self.to_world(c1, r1),
                        'width': self.track_w
                    })
                    cur_track_start = (c1, r1)
                    cur_dir = step_dir
                    
        if cur_track_start:
            items.append({
                'type': 'track',
                'net': self.net_name,
                'layer': cur_layer,
                'start': self.to_world(cur_track_start[0], cur_track_start[1]),
                'end': self.to_world(path[-1][0], path[-1][1]),
                'width': self.track_w
            })
            
        return items
