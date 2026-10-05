import pcbnew, math, heapq, time

class AStarRouter:
    def __init__(self, board_path, net_name, bbox, grid_step=0.1, clearance=0.15, track_width=0.15, via_size=0.25):
        self.board = pcbnew.LoadBoard(board_path)
        self.net_name = net_name
        self.net = self.board.FindNet(net_name)
        if not self.net:
            raise ValueError(f"Net {net_name} not found!")
        self.netcode = self.net.GetNetCode()
        
        self.min_x, self.min_y, self.max_x, self.max_y = bbox
        self.step = grid_step
        self.clearance = clearance
        self.track_w = track_width
        self.via_size = via_size
        
        self.cols = int(math.ceil((self.max_x - self.min_x) / self.step)) + 1
        self.rows = int(math.ceil((self.max_y - self.min_y) / self.step)) + 1
        
    def to_grid(self, x, y):
        col = int(round((x - self.min_x) / self.step))
        row = int(round((y - self.min_y) / self.step))
        return col, row
        
    def to_world(self, col, row):
        x = self.min_x + col * self.step
        y = self.min_y + row * self.step
        return round(x, 4), round(y, 4)
        
    def build_obstacle_grid(self, search_layers):
        blocked = {l: set() for l in search_layers}
        req_dist = (self.track_w / 2.0) + self.clearance
        via_req_dist = (self.via_size / 2.0) + self.clearance
        
        # Collect obstacles from board tracks and vias
        for tr in self.board.GetTracks():
            if tr.GetNetCode() == self.netcode:
                continue
            is_via = (tr.GetClass() == 'PCB_VIA')
            if is_via:
                vx = pcbnew.ToMM(tr.GetPosition().x)
                vy = pcbnew.ToMM(tr.GetPosition().y)
                vr = (pcbnew.ToMM(tr.GetWidth()) / 2.0) if hasattr(tr, 'GetWidth') else 0.2
                if hasattr(tr, 'GetDrill'):
                    vr = max(vr, 0.2)
                tot_r = vr + max(req_dist, via_req_dist)
                if not (self.min_x - tot_r <= vx <= self.max_x + tot_r and self.min_y - tot_r <= vy <= self.max_y + tot_r):
                    continue
                top_id = tr.TopLayer()
                bot_id = tr.BottomLayer()
                min_id, max_id = min(top_id, bot_id), max(top_id, bot_id)
                
                c_min = max(0, int(math.floor((vx - tot_r - self.min_x) / self.step)))
                c_max = min(self.cols - 1, int(math.ceil((vx + tot_r - self.min_x) / self.step)))
                r_min = max(0, int(math.floor((vy - tot_r - self.min_y) / self.step)))
                r_max = min(self.rows - 1, int(math.ceil((vy + tot_r - self.min_y) / self.step)))
                
                for l in search_layers:
                    lid = self.board.GetLayerID(l)
                    if min_id <= lid <= max_id:
                        for c in range(c_min, c_max + 1):
                            for r in range(r_min, r_max + 1):
                                wx, wy = self.to_world(c, r)
                                if (wx - vx)**2 + (wy - vy)**2 <= tot_r**2:
                                    blocked[l].add((c, r))
            else:
                l_name = tr.GetLayerName()
                if l_name not in search_layers:
                    continue
                sp = tr.GetStart()
                ep = tr.GetEnd()
                sx, sy = pcbnew.ToMM(sp.x), pcbnew.ToMM(sp.y)
                ex, ey = pcbnew.ToMM(ep.x), pcbnew.ToMM(ep.y)
                tw = pcbnew.ToMM(tr.GetWidth())
                tot_r = (tw / 2.0) + req_dist
                
                minx = min(sx, ex) - tot_r
                maxx = max(sx, ex) + tot_r
                miny = min(sy, ey) - tot_r
                maxy = max(sy, ey) + tot_r
                if not (minx <= self.max_x and maxx >= self.min_x and miny <= self.max_y and maxy >= self.min_y):
                    continue
                c_min = max(0, int(math.floor((minx - self.min_x) / self.step)))
                c_max = min(self.cols - 1, int(math.ceil((maxx - self.min_x) / self.step)))
                r_min = max(0, int(math.floor((miny - self.min_y) / self.step)))
                r_max = min(self.rows - 1, int(math.ceil((maxy - self.min_y) / self.step)))
                
                dx = ex - sx
                dy = ey - sy
                l_sq = dx*dx + dy*dy
                for c in range(c_min, c_max + 1):
                    for r in range(r_min, r_max + 1):
                        wx, wy = self.to_world(c, r)
                        if l_sq == 0:
                            dist_sq = (wx - sx)**2 + (wy - sy)**2
                        else:
                            u = max(0.0, min(1.0, ((wx - sx)*dx + (wy - sy)*dy) / l_sq))
                            dist_sq = (wx - (sx + u*dx))**2 + (wy - (sy + u*dy))**2
                        if dist_sq <= tot_r**2:
                            blocked[l_name].add((c, r))
                            
        # Check pads of other nets with full box expansion
        for p in self.board.GetPads():
            if p.GetNetCode() == self.netcode:
                continue
            pos = p.GetPosition()
            px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
            sz = p.GetSize()
            hw = (pcbnew.ToMM(sz.x) / 2.0) + max(req_dist, via_req_dist)
            hh = (pcbnew.ToMM(sz.y) / 2.0) + max(req_dist, via_req_dist)
            
            minx = px - hw
            maxx = px + hw
            miny = py - hh
            maxy = py + hh
            if not (minx <= self.max_x and maxx >= self.min_x and miny <= self.max_y and maxy >= self.min_y):
                continue
            pad_layers = [self.board.GetLayerName(lid) for lid in p.GetLayerSet().Seq()]
            c_min = max(0, int(math.floor((minx - self.min_x) / self.step)))
            c_max = min(self.cols - 1, int(math.ceil((maxx - self.min_x) / self.step)))
            r_min = max(0, int(math.floor((miny - self.min_y) / self.step)))
            r_max = min(self.rows - 1, int(math.ceil((maxy - self.min_y) / self.step)))
            for l in search_layers:
                if l in pad_layers:
                    for c in range(c_min, c_max + 1):
                        for r in range(r_min, r_max + 1):
                            blocked[l].add((c, r))
                                
        return blocked

    def find_path(self, start_pos, end_pos, search_layers, allowed_via_pairs=None):
        if allowed_via_pairs is None:
            allowed_via_pairs = []
            for i in range(len(search_layers)):
                for j in range(i+1, len(search_layers)):
                    allowed_via_pairs.append((search_layers[i], search_layers[j]))
                    allowed_via_pairs.append((search_layers[j], search_layers[i]))
                    
        print(f"Building obstacle grid for {len(search_layers)} layers, bbox: {self.cols}x{self.rows}...")
        t0 = time.time()
        blocked = self.build_obstacle_grid(search_layers)
        print(f"Obstacle grid built in {time.time()-t0:.2f}s.")
        
        sc, sr = self.to_grid(start_pos[0], start_pos[1])
        ec, er = self.to_grid(end_pos[0], end_pos[1])
        start_node = (sc, sr, start_pos[2])
        end_node = (ec, er, end_pos[2])
        
        pq = []
        heapq.heappush(pq, (0.0, 0.0, start_node))
        came_from = {}
        cost_so_far = {start_node: 0.0}
        
        def h(c, r, l):
            d_xy = math.hypot(c - ec, r - er) * self.step
            d_l = 0.0 if l == end_pos[2] else 2.0
            return d_xy + d_l
            
        dirs = [
            (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
            (1, 1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (-1, -1, 1.414)
        ]
        
        found = False
        while pq:
            _, current_cost, current = heapq.heappop(pq)
            if current == end_node:
                found = True
                break
                
            cc, cr, cl = current
            
            # In-plane movement
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
                            
            # Layer transition (via)
            for l1, l2 in allowed_via_pairs:
                if cl == l1:
                    # check if via fits here on both layers
                    if (cc, cr) not in blocked[l1] and ((cc, cr) not in blocked[l2] or (cc, cr, l2) == end_node):
                        neighbor = (cc, cr, l2)
                        via_cost = 5.0
                        new_cost = current_cost + via_cost
                        if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                            cost_so_far[neighbor] = new_cost
                            priority = new_cost + h(cc, cr, l2)
                            heapq.heappush(pq, (priority, new_cost, neighbor))
                            came_from[neighbor] = current
                            
        if not found:
            print("No path found!")
            return None
            
        # Reconstruct path
        path = []
        curr = end_node
        while curr != start_node:
            path.append(curr)
            curr = came_from[curr]
        path.append(start_node)
        path.reverse()
        
        items = []
        current_segment = []
        
        for i in range(len(path)):
            node = path[i]
            wx, wy = self.to_world(node[0], node[1])
            layer = node[2]
            
            if i > 0 and path[i][2] != path[i-1][2]:
                via_pos = self.to_world(path[i-1][0], path[i-1][1])
                l1 = path[i-1][2]
                l2 = path[i][2]
                items.append({
                    'type': 'via',
                    'net': self.net_name,
                    'pos': via_pos,
                    'via_type': 'microvia' if 'B.Cu' in [l1, l2] or 'F.Cu' in [l1, l2] else 'through',
                    'size': self.via_size,
                    'drill': 0.1 if self.via_size <= 0.3 else 0.15,
                    'top_layer': l1 if self.board.GetLayerID(l1) < self.board.GetLayerID(l2) else l2,
                    'bottom_layer': l2 if self.board.GetLayerID(l1) < self.board.GetLayerID(l2) else l1
                })
                current_segment = [(wx, wy, layer)]
            else:
                if not current_segment:
                    current_segment = [(wx, wy, layer)]
                else:
                    current_segment.append((wx, wy, layer))
                    
            if i == len(path) - 1 or (i < len(path)-1 and path[i+1][2] != path[i][2]):
                if len(current_segment) >= 2:
                    simplified = [current_segment[0]]
                    for k in range(1, len(current_segment) - 1):
                        p_prev = simplified[-1]
                        p_curr = current_segment[k]
                        p_next = current_segment[k+1]
                        d1x, d1y = p_curr[0] - p_prev[0], p_curr[1] - p_prev[1]
                        d2x, d2y = p_next[0] - p_curr[0], p_next[1] - p_curr[1]
                        if abs(d1x * d2y - d1y * d2x) > 1e-5:
                            simplified.append(p_curr)
                    simplified.append(current_segment[-1])
                    
                    for k in range(len(simplified) - 1):
                        items.append({
                            'type': 'track',
                            'net': self.net_name,
                            'layer': simplified[k][2],
                            'start': (simplified[k][0], simplified[k][1]),
                            'end': (simplified[k+1][0], simplified[k+1][1]),
                            'width': self.track_w
                        })
                current_segment = []
                
        return items
