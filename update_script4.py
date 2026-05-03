import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

content = content.replace(
    '        node_radius = min(spacing_x, spacing_y) * 0.25\n        # Ensure lane width has a safe minimum (192.0 is vehicle clearance) so connectivity check doesn\'t fail on tiny paths\n        lane_width = max(192.0, min(spacing_x, spacing_y) * 0.30 * getattr(spec, "lane_width_scale", 1.0))',
    '        lane_width_scale = getattr(spec, "lane_width_scale", 1.0)\n        # Cap width scaling slightly below 0.5 so we still have some canyon walls even at massive lane widths.\n        capped_scale = min(lane_width_scale, 1.45)\n        node_radius = min(spacing_x, spacing_y) * 0.25 * capped_scale\n        # Ensure lane width has a safe minimum (192.0 is vehicle clearance) so connectivity check doesn\'t fail on tiny paths\n        lane_width = max(192.0, min(spacing_x, spacing_y) * 0.30 * capped_scale)'
)

content = content.replace(
    '                # node_radius = 0 since corridors define space\n                node = LayoutNode(wx, wy, 0, ZoneType.VEHICLE_OPEN)',
    '                node = LayoutNode(wx, wy, node_radius, ZoneType.VEHICLE_OPEN)'
)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
