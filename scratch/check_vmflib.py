import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools" / "vmflib"))
try:
    from vmflib.brush import DispInfo
    from vmflib.types import Vertex
    
    power = 3
    # Dummy data
    normals = [[Vertex(0,0,1) for _ in range(9)] for _ in range(9)]
    heights = [[0 for _ in range(9)] for _ in range(9)]
    
    disp = DispInfo(power, normals, heights)
    print(f"Alphas type: {type(disp.alphas)}")
    print(f"Alphas dir: {dir(disp.alphas)}")
    if hasattr(disp.alphas, 'properties'):
        print("Alphas has properties")
except Exception as e:
    print(f"Error: {e}")
