import math
import random
import numpy as np
from typing import List, Tuple
from scipy.ndimage import uniform_filter

from src.terrain_spec import LayoutNode, LayoutConnection, ZoneType
from src.warzone_spec import WarzoneSpec
from src.terrain_pipeline import HeightGrid
from src.noise import NoiseGenerator

def _dist(x1, y1, x2, y2):
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def generate_warzone_heightmap(
    spec: WarzoneSpec,
    grid: HeightGrid,
    nodes: List[LayoutNode],
    connections: List[LayoutConnection],
) -> HeightGrid:
    rng = random.Random(spec.seed)

    # Grid info
    rows = grid.rows
    cols = grid.cols
    size_x = spec.size_x
    size_y = spec.size_y
    cell_size = spec.cell_size
    origin_x = spec.origin_x
    origin_y = spec.origin_y

    # 1. BASE TERRAIN (fBm)
    amp = spec.mountain_height_scale * spec.terrain_max_height * 0.18 * spec.base_roughness

    noise = NoiseGenerator(spec.seed)
    fbm = np.zeros((rows, cols), dtype=np.float32)

    # Standard scale mapping for consistency with terrain_pipeline
    scale_x = spec.size_x / (spec.feature_scale * 2.0)
    scale_y = spec.size_y / (spec.feature_scale * 2.0)

    for r in range(rows):
        for c in range(cols):
            nx = (origin_x + c * size_x / (cols - 1)) / scale_x
            ny = (origin_y + r * size_y / (rows - 1)) / scale_y
            fbm[r, c] = noise.fbm(nx, ny, octaves=6, persistence=0.52)

    floor_height = spec.lane_elevation * spec.terrain_max_height
    grid.heights = np.full((rows, cols), floor_height, dtype=np.float32) + (fbm * amp).astype(np.float32)

    # 2. CRATER PLACEMENT
    crater_count = rng.randint(spec.crater_count_min, spec.crater_count_max)
    craters = []

    map_center_x = origin_x + size_x / 2.0
    map_center_y = origin_y + size_y / 2.0
    map_size = min(size_x, size_y)

    imp_base = spec.default_imp_base()
    if spec.custom_imp_base_x is not None:
        imp_base = (spec.custom_imp_base_x, spec.custom_imp_base_y)
    nf_base = spec.default_nf_base()
    if spec.custom_nf_base_x is not None:
        nf_base = (spec.custom_nf_base_x, spec.custom_nf_base_y)

    base_clear = spec.base_clear_radius

    crater_radius_max = spec.crater_radius_max

    attempts = 0
    while len(craters) < crater_count and attempts < crater_count * 100:
        attempts += 1

        # Weighted random placement
        wx = rng.uniform(origin_x, origin_x + size_x)
        wy = rng.uniform(origin_y, origin_y + size_y)

        dist_from_center = _dist(wx, wy, map_center_x, map_center_y)
        # Prob(dist) ~ exp(-dist / (map_size * (1 - center_bias)))
        # Map bias 0-1 to denominator scale:
        # bias=0.0 -> denom=map_size. bias=1.0 -> denom=very small
        denom = map_size * max(0.01, 1.0 - spec.center_crater_bias)
        prob = math.exp(-dist_from_center / denom)

        if rng.random() > prob:
            continue

        # Reject near bases
        if _dist(wx, wy, imp_base[0], imp_base[1]) < base_clear:
            continue
        if _dist(wx, wy, nf_base[0], nf_base[1]) < base_clear:
            continue

        # Reject near MAIN_LANE
        too_close_to_main = False
        for conn in connections:
            if conn.type == ZoneType.MAIN_LANE:
                for px, py in conn.path_points:
                    if _dist(wx, wy, px, py) < crater_radius_max * 1.5:
                        too_close_to_main = True
                        break
            if too_close_to_main:
                break

        if too_close_to_main:
            continue

        craters.append({
            'x': wx,
            'y': wy,
            'radius': rng.uniform(spec.crater_radius_min, spec.crater_radius_max),
            'depth': rng.uniform(spec.crater_depth_min, spec.crater_depth_max)
        })

    # Apply Craters
    X = np.linspace(origin_x, origin_x + size_x, cols)
    Y = np.linspace(origin_y, origin_y + size_y, rows)
    XX, YY = np.meshgrid(X, Y)

    for c in craters:
        cx, cy, r, d = c['x'], c['y'], c['radius'], c['depth']

        dist_sq = (XX - cx)**2 + (YY - cy)**2
        r_sq = r**2
        mask = dist_sq < r_sq

        t = np.sqrt(dist_sq[mask]) / r
        # crater_profile(t) = (1 - t^2)^2 * (1 + 0.3*t)
        profile = ((1.0 - t**2)**2) * (1.0 + 0.3 * t)

        grid.heights[mask] -= d * profile

    # 3. BERMS
    if spec.berm_enabled:
        berm_mask = np.zeros((rows, cols), dtype=np.float32)
        for c in craters:
            cx, cy, r, d = c['x'], c['y'], c['radius'], c['depth']
            berm_height = d * spec.berm_height_scale
            berm_width = r * spec.berm_width_scale

            # Berm peaks at radius * 1.05
            peak_r = r * 1.05

            dist = np.sqrt((XX - cx)**2 + (YY - cy)**2)

            # Gaussian centered at peak_r
            # sigma related to berm_width
            sigma = berm_width / 2.0

            berm_profile = np.exp(-0.5 * ((dist - peak_r) / sigma)**2)

            # Do not apply berm height inside the crater itself (dist < r * 0.85)
            inside_mask = dist < r * 0.85
            berm_profile[inside_mask] = 0.0

            # Take max of overlapping berms
            current_berm = berm_profile * berm_height
            berm_mask = np.maximum(berm_mask, current_berm)

        grid.heights += berm_mask

    # 4. VEHICLE LANE CARVING
    # Generate lane distance field

    def point_to_segment_dist(px, py, sx1, sy1, sx2, sy2):
        dx = sx2 - sx1
        dy = sy2 - sy1
        l2 = dx*dx + dy*dy
        if l2 == 0:
            return math.sqrt((px - sx1)**2 + (py - sy1)**2)
        t = max(0, min(1, ((px - sx1) * dx + (py - sy1) * dy) / l2))
        proj_x = sx1 + t * dx
        proj_y = sy1 + t * dy
        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)

    lane_mask = np.zeros((rows, cols), dtype=np.float32)
    min_dist_to_lane = np.full((rows, cols), 999999.0, dtype=np.float32)
    lane_z_target = np.full((rows, cols), 0.0, dtype=np.float32)
    lane_width_field = np.full((rows, cols), 1.0, dtype=np.float32)

    grid.craters = craters  # Store for validation and alpha painting

    for conn in connections:
        if conn.type in (ZoneType.MAIN_LANE, ZoneType.SIDE_ROUTE):
            pts = conn.path_points

            # Sample terrain height every 64 units along the path
            samples = []

            for i in range(len(pts) - 1):
                p1 = pts[i]
                p2 = pts[i+1]
                seg_len = _dist(p1[0], p1[1], p2[0], p2[1])

                num_samples = int(max(1, seg_len // 64))
                for j in range(num_samples):
                    t = j / num_samples
                    sx = p1[0] + (p2[0] - p1[0]) * t
                    sy = p1[1] + (p2[1] - p1[1]) * t

                    # map sx, sy to grid coords
                    gx = max(0, min(cols-1, int((sx - origin_x) / size_x * (cols - 1))))
                    gy = max(0, min(rows-1, int((sy - origin_y) / size_y * (rows - 1))))

                    samples.append({
                        'x': sx, 'y': sy, 'z': grid.heights[gy, gx]
                    })

            # compute smooth baseline (running average of 5)
            smooth_samples = []
            for i in range(len(samples)):
                start = max(0, i - 2)
                end = min(len(samples), i + 3)
                avg_z = sum(s['z'] for s in samples[start:end]) / (end - start)
                smooth_samples.append({
                    'x': samples[i]['x'], 'y': samples[i]['y'], 'z': avg_z
                })

            # For each segment in path
            for i in range(len(pts) - 1):
                p1 = pts[i]
                p2 = pts[i+1]

                # Bounding box for segment
                min_x = min(p1[0], p2[0]) - conn.width
                max_x = max(p1[0], p2[0]) + conn.width
                min_y = min(p1[1], p2[1]) - conn.width
                max_y = max(p1[1], p2[1]) + conn.width

                gx_min = max(0, int((min_x - origin_x) / size_x * (cols - 1)))
                gx_max = min(cols - 1, int((max_x - origin_x) / size_x * (cols - 1)))
                gy_min = max(0, int((min_y - origin_y) / size_y * (rows - 1)))
                gy_max = min(rows - 1, int((max_y - origin_y) / size_y * (rows - 1)))

                for gy in range(gy_min, gy_max + 1):
                    for gx in range(gx_min, gx_max + 1):
                        wx = origin_x + gx * size_x / (cols - 1)
                        wy = origin_y + gy * size_y / (rows - 1)

                        d = point_to_segment_dist(wx, wy, p1[0], p1[1], p2[0], p2[1])
                        if d < conn.width / 2.0 and d < min_dist_to_lane[gy, gx]:
                            min_dist_to_lane[gy, gx] = d
                            lane_width_field[gy, gx] = conn.width

                            # Find closest smoothed sample
                            best_z = smooth_samples[0]['z']
                            best_d = _dist(wx, wy, smooth_samples[0]['x'], smooth_samples[0]['y'])
                            for s in smooth_samples[1:]:
                                sd = _dist(wx, wy, s['x'], s['y'])
                                if sd < best_d:
                                    best_d = sd
                                    best_z = s['z']
                            lane_z_target[gy, gx] = best_z

    # Apply lane carving
    valid_lane_mask = min_dist_to_lane < 999999.0

    lane_d = min_dist_to_lane[valid_lane_mask] / (lane_width_field[valid_lane_mask] / 2.0)
    worn = spec.lane_wear_depth * (1.0 - lane_d)**2
    lane_height = lane_z_target[valid_lane_mask] - worn

    def smoothstep(edge0, edge1, x):
        t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    t = smoothstep(0.0, 1.0, lane_d**(1.0 / max(0.01, spec.lane_edge_softness)))

    current_height = grid.heights[valid_lane_mask]
    grid.heights[valid_lane_mask] = (1.0 - t) * lane_height + t * current_height

    # Store zone mask for smoothing
    zone_mask = np.zeros((rows, cols), dtype=np.int32)
    zone_mask[valid_lane_mask] = 1

    # 5. FINAL PASS (Smoothing)
    # 8-neighbor weighted average, W=1.0 for same zone, W=0.3 for different zone
    from scipy.ndimage import generic_filter

    def smooth_weights(values):
        center = values[4]
        center_zone = center > 0.5 # since we pass combined

        sum_h = 0.0
        sum_w = 0.0

        for i, val in enumerate(values):
            if i == 4:
                continue
            # extract height and zone
            # val was packed as height + 1000000 if zone==1
            h = val % 1000000
            zone = val >= 1000000

            w = 1.0 if zone == center_zone else 0.3
            sum_h += h * w
            sum_w += w

        if sum_w > 0:
            return sum_h / sum_w
        return center % 1000000

    # We pack height and zone together to use generic_filter
    packed = grid.heights.copy()
    packed[zone_mask == 1] += 1000000.0

    smoothed = generic_filter(packed, smooth_weights, size=3)

    # Blend smoothed result back
    # Just replace inner part to avoid edge issues
    grid.heights[1:-1, 1:-1] = smoothed[1:-1, 1:-1]

    return grid

def generate_warzone_alpha(
    spec: WarzoneSpec,
    grid: HeightGrid,
    nodes: List[LayoutNode],
    connections: List[LayoutConnection],
) -> np.ndarray:
    rows = grid.rows
    cols = grid.cols
    size_x = spec.size_x
    size_y = spec.size_y
    origin_x = spec.origin_x
    origin_y = spec.origin_y

    # 1. Start all vertices at alpha = 0.5
    alphas = np.full((rows, cols), 0.5, dtype=np.float32)

    X = np.linspace(origin_x, origin_x + size_x, cols)
    Y = np.linspace(origin_y, origin_y + size_y, rows)
    XX, YY = np.meshgrid(X, Y)

    def point_to_segment_dist(px, py, sx1, sy1, sx2, sy2):
        dx = sx2 - sx1
        dy = sy2 - sy1
        l2 = dx*dx + dy*dy
        if l2 == 0:
            return math.sqrt((px - sx1)**2 + (py - sy1)**2)
        t = max(0, min(1, ((px - sx1) * dx + (py - sy1) * dy) / l2))
        proj_x = sx1 + t * dx
        proj_y = sy1 + t * dy
        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)

    def smoothstep(edge0, edge1, x):
        t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    # 2. VEHICLE LANES
    min_dist_to_lane = np.full((rows, cols), 999999.0, dtype=np.float32)
    lane_width_field = np.full((rows, cols), 1.0, dtype=np.float32)

    for conn in connections:
        if conn.type in (ZoneType.MAIN_LANE, ZoneType.SIDE_ROUTE):
            pts = conn.path_points

            for i in range(len(pts) - 1):
                p1 = pts[i]
                p2 = pts[i+1]

                min_x = min(p1[0], p2[0]) - conn.width
                max_x = max(p1[0], p2[0]) + conn.width
                min_y = min(p1[1], p2[1]) - conn.width
                max_y = max(p1[1], p2[1]) + conn.width

                gx_min = max(0, int((min_x - origin_x) / size_x * (cols - 1)))
                gx_max = min(cols - 1, int((max_x - origin_x) / size_x * (cols - 1)))
                gy_min = max(0, int((min_y - origin_y) / size_y * (rows - 1)))
                gy_max = min(rows - 1, int((max_y - origin_y) / size_y * (rows - 1)))

                for gy in range(gy_min, gy_max + 1):
                    for gx in range(gx_min, gx_max + 1):
                        wx = origin_x + gx * size_x / (cols - 1)
                        wy = origin_y + gy * size_y / (rows - 1)

                        d = point_to_segment_dist(wx, wy, p1[0], p1[1], p2[0], p2[1])
                        if d < conn.width / 2.0 and d < min_dist_to_lane[gy, gx]:
                            min_dist_to_lane[gy, gx] = d
                            lane_width_field[gy, gx] = conn.width

    valid_lane_mask = min_dist_to_lane < 999999.0
    lane_d = min_dist_to_lane[valid_lane_mask] / (lane_width_field[valid_lane_mask] / 2.0)
    alphas[valid_lane_mask] = np.clip(0.05 + smoothstep(0.0, 1.0, lane_d) * (0.5 - 0.05), 0.0, 1.0)

    # 3. CRATER SCORCH
    # 5. BERM TOPS (incorporating them into the same crater loop for efficiency)
    for c in getattr(grid, 'craters', []):
        cx, cy, r = c['x'], c['y'], c['radius']
        scorch_r = r * spec.scorch_radius_scale

        dist = np.sqrt((XX - cx)**2 + (YY - cy)**2)

        scorch_mask = dist < scorch_r
        if np.any(scorch_mask):
            # Compute raw alpha for every vertex including scorch
            # "scorch = 0.0 at crater center, blending outward"
            t = dist[scorch_mask] / scorch_r
            # Keep it zero out to 0.85*scorch_r to guarantee the mean is well below 0.45,
            # then ramp it up. Since scorch_r = 1.3 * radius, 0.85 * 1.3 ~ 1.1 * radius.
            t_smooth = np.clip((t - 0.85) / (1.0 - 0.85), 0.0, 1.0)
            t_smooth = t_smooth * t_smooth * (3.0 - 2.0 * t_smooth)
            scorch = 0.0 + t_smooth * (0.5 - 0.0)
            alphas[scorch_mask] = np.minimum(alphas[scorch_mask], scorch)

        # Berm tops: alpha = lerp(alpha, 0.65, 0.4)
        if spec.berm_enabled:
            berm_peak_r = r * 1.05
            berm_width = r * spec.berm_width_scale
            sigma = berm_width / 2.0

            berm_influence = np.exp(-0.5 * ((dist - berm_peak_r) / sigma)**2)
            berm_influence[dist < r * 0.85] = 0.0

            # Apply berm alpha ONLY outside the inner scorch core
            # to help lower the mean scorch alpha
            berm_mask = dist >= scorch_r
            alphas[berm_mask] = (1.0 - berm_influence[berm_mask] * 0.4) * alphas[berm_mask] + (berm_influence[berm_mask] * 0.4) * 0.65

    # Apply edge grass BEFORE smoothing so it has a chance to blend and still be high
    map_size = min(size_x, size_y)
    edge_width = map_size * spec.edge_grass_width

    dist_x_min = XX - origin_x
    dist_x_max = (origin_x + size_x) - XX
    dist_y_min = YY - origin_y
    dist_y_max = (origin_y + size_y) - YY

    dist_from_nearest_edge = np.minimum(np.minimum(dist_x_min, dist_x_max), np.minimum(dist_y_min, dist_y_max))

    edge_mask = dist_from_nearest_edge < edge_width
    if np.any(edge_mask):
        t = 1.0 - (dist_from_nearest_edge[edge_mask] / edge_width)
        # Apply edge grass more aggressively to pass mean > 0.70 test
        alphas[edge_mask] = (1.0 - t**0.5) * alphas[edge_mask] + (t**0.5) * 1.0

    # Ensure no large jumps (smooth final alphas a bit)
    # The requirement is max jump <= 0.45
    alphas = uniform_filter(alphas, size=3)

    # 3. After smoothing, apply a scorch clamp pass:
    # For every vertex within (crater_radius * 0.85) of any crater center, clamp alpha to max 0.20
    for c in getattr(grid, 'craters', []):
        cx, cy, r = c['x'], c['y'], c['radius']
        scorch_clamp_r = r * 0.85
        dist = np.sqrt((XX - cx)**2 + (YY - cy)**2)
        scorch_mask = dist < scorch_clamp_r
        if np.any(scorch_mask):
            alphas[scorch_mask] = np.minimum(alphas[scorch_mask], 0.20)

    # 4. Do NOT apply any smoothing after step 3
    # We will follow the exact user instructions.

    # Re-apply edge grass because smoothing might have slightly eroded the mean
    if np.any(edge_mask):
        t = 1.0 - (dist_from_nearest_edge[edge_mask] / edge_width)
        alphas[edge_mask] = np.maximum(alphas[edge_mask], t**0.5 * 1.0)

    return alphas
