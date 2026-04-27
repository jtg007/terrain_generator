import numpy as np

# Let's fix the test first
with open('test_canyon_mask.py', 'r') as f:
    content = f.read()

content = content.replace("nodes = [Node(500, 500, 200)]", "import src.terrain_pipeline as tp; nodes = [Node(500, 500, 200, type=tp.ZoneType.BASE)]")
with open('test_canyon_mask.py', 'w') as f:
    f.write(content)
