import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").absolute()))

from src.vmf_gen import DisplacementVMF, PipelineSpec
import numpy as np

for theme in ["Temperate", "Desert", "Snow"]:
    spec = PipelineSpec(map_name=f"test_map_{theme}_cliff")
    spec.current_theme = theme
    vmf = DisplacementVMF(spec)

    # Need to load a dummy heightmap to make it run
    # Let's create a very steep gradient so it registers as a cliff
    vmf.heightmap = np.zeros((65, 65), dtype=np.float32)
    for i in range(65):
        for j in range(65):
            vmf.heightmap[i, j] = i * 0.1
    vmf.heightmap_width = 65
    vmf.heightmap_height = 65

    output_path = f"output/test_{theme}_cliff.vmf"
    Path("output").mkdir(exist_ok=True)
    vmf.generate_vmf(output_path)

    print(f"Generated {output_path}")
