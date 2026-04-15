import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# 1. Update LayoutConnection
content = re.sub(
    r'class LayoutConnection:\n    start_node: LayoutNode\n    end_node: LayoutNode\n    width: float\n    type: str  # \'main_lane\', \'side_lane\', \'chokepoint_lane\'',
    r"class LayoutConnection:\n    start_node: LayoutNode\n    end_node: LayoutNode\n    width: float\n    type: str  # 'main_lane', 'side_lane', 'chokepoint_lane'\n    path_points: List[Tuple[float, float]] = None",
    content
)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
