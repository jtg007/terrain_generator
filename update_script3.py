import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# Replace lane_width logic to correctly handle the scale
content = content.replace(
    '        lane_width_scale = getattr(spec, "lane_width_scale", 1.0)\n        node_radius = min(spacing_x, spacing_y) * 0.25 * lane_width_scale\n        # Ensure lane width has a safe minimum (192.0 is vehicle clearance) so connectivity check doesn\'t fail on tiny paths\n        # Cap it so we still have some canyon walls even at massive lane widths.\n        lane_width = max(192.0, min(min(spacing_x, spacing_y) * 0.30 * lane_width_scale, min(spacing_x, spacing_y) * 0.45))',
    '        lane_width_scale = getattr(spec, "lane_width_scale", 1.0)\n        # Cap it so we still have some canyon walls even at massive lane widths.\n        node_radius = min(spacing_x, spacing_y) * 0.25 * min(lane_width_scale, 1.5)\n        # Ensure lane width has a safe minimum (192.0 is vehicle clearance) so connectivity check doesn\'t fail on tiny paths\n        lane_width = max(192.0, min(spacing_x, spacing_y) * 0.30 * min(lane_width_scale, 1.5))'
)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
