import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

helper_function = """
def create_connection_path(
    start_node: LayoutNode,
    end_node: LayoutNode,
    width: float,
    conn_type: str,
    spec: TerrainSpec
) -> LayoutConnection:
    import math
    from src.noise import NoiseGenerator

    noise = NoiseGenerator(spec.seed)

    dx = end_node.x - start_node.x
    dy = end_node.y - start_node.y
    length = math.sqrt(dx*dx + dy*dy)

    if length == 0:
        return LayoutConnection(start_node, end_node, width, conn_type, [(start_node.x, start_node.y)])

    nx = -dy / length
    ny = dx / length

    # Subdivide line: roughly one point every 150 units
    num_segments = max(1, int(length / 150.0))
    path_points = []

    # Max offset is 20% of the total connection length
    max_offset = length * 0.20
    freq = 3.0  # Frequency of the winding

    for i in range(num_segments + 1):
        t = i / num_segments
        base_x = start_node.x + t * dx
        base_y = start_node.y + t * dy

        if i == 0 or i == num_segments:
            # Anchor perfectly to the start and end nodes
            path_points.append((base_x, base_y))
            continue

        # Sine envelope forces noise to 0 at the start and end
        envelope = math.sin(t * math.pi)

        # 1D noise sampled along t
        noise_val = noise.fbm(t * freq, spec.seed * 0.1, octaves=2)
        offset = noise_val * envelope * max_offset

        px = base_x + nx * offset
        py = base_y + ny * offset
        path_points.append((px, py))

    return LayoutConnection(start_node, end_node, width, conn_type, path_points)

def generate_strategic_layout(
"""

# The issue in the first script was that the regex didn't match the exact signature or there were multiple matches.
# Let's replace the EXACT string:
target = "def generate_strategic_layout(\n    spec: TerrainSpec,\n) -> Tuple[List[LayoutNode], List[LayoutConnection]]:"
replacement = helper_function + "    spec: TerrainSpec,\n) -> Tuple[List[LayoutNode], List[LayoutConnection]]:"

content = content.replace(target, replacement)

# Now, we do the same replace logic inside the newly modified `generate_strategic_layout` block
start_idx = content.find("def generate_strategic_layout(")
end_idx = content.find("def generate_heights(")

if start_idx != -1 and end_idx != -1:
    gen_layout = content[start_idx:end_idx]

    def replacer(match):
        inner = match.group(1)
        return f"create_connection_path({inner}, spec)"

    gen_layout_new = re.sub(r'LayoutConnection\(([^)]+)\)', replacer, gen_layout)

    content = content[:start_idx] + gen_layout_new + content[end_idx:]

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
