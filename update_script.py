import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

content = content.replace(
    '                # node_radius = 0 since corridors define space\n                node = LayoutNode(wx, wy, 0, ZoneType.VEHICLE_OPEN)',
    '                node = LayoutNode(wx, wy, node_radius, ZoneType.VEHICLE_OPEN)'
)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
