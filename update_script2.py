import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# I want to cap lane_width to half the map size or less than the spacing so we don't totally wipe out walls
content = content.replace(
    '        lane_width = max(192.0, min(spacing_x, spacing_y) * 0.30 * lane_width_scale)',
    '        # Ensure lane width has a safe minimum (192.0 is vehicle clearance) so connectivity check doesn\'t fail on tiny paths\n        # Cap it so we still have some canyon walls even at massive lane widths.\n        lane_width = max(192.0, min(min(spacing_x, spacing_y) * 0.30 * lane_width_scale, min(spacing_x, spacing_y) * 0.45))'
)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
