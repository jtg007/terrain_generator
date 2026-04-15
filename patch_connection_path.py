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

content = content.replace("def generate_strategic_layout(\n", helper_function)

# Replace LayoutConnection instantiation with create_connection_path in generate_strategic_layout
# This might be tricky because of spacing and newlines, let's use a regex carefully.
# We replace: LayoutConnection(A, B, C, D) with create_connection_path(A, B, C, D, spec)
# Inside generate_strategic_layout, we need to match it properly.

# Let's extract generate_strategic_layout to replace locally
start_idx = content.find("def generate_strategic_layout(")
end_idx = content.find("def generate_heights(")

if start_idx != -1 and end_idx != -1:
    gen_layout = content[start_idx:end_idx]

    # Replace LayoutConnection with create_connection_path
    # Pattern: LayoutConnection(a, b, c, d)
    # Be careful, python allows newlines inside ().
    # Let's write a simple replacer for this block.
    # We will just replace "LayoutConnection(" with "create_connection_path(" and insert ", spec" before the closing parenthesis.
    import ast

    class RewriteConnections(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == 'LayoutConnection':
                node.func.id = 'create_connection_path'
                node.args.append(ast.Name(id='spec', ctx=ast.Load()))
            return node

    # To be safer, I will just use regex on the text, since AST unparsing drops formatting.
    # The formatting in `generate_strategic_layout` is pretty standard.
    # Connections are appended like: LayoutConnection(imp_base, center_node, lane_width, ZoneType.MAIN_LANE)

    # Actually, all LayoutConnection usages in `generate_strategic_layout` follow exactly 4 arguments.
    # Let's use a regex that matches `LayoutConnection(arg1, arg2, arg3, arg4)`
    # Considering newlines, we can match it.

    def replacer(match):
        inner = match.group(1)
        return f"create_connection_path({inner}, spec)"

    gen_layout_new = re.sub(r'LayoutConnection\(([^)]+)\)', replacer, gen_layout)

    content = content[:start_idx] + gen_layout_new + content[end_idx:]

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
