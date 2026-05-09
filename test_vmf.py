from src.vmf_gen import DisplacementVMF, PipelineSpec
import numpy as np

spec = PipelineSpec(map_name="test_map")
gen = DisplacementVMF(spec)
gen.heightmap = np.random.rand(1024, 1024)
gen.playability_mask = np.random.rand(1024, 1024) * 255.0
gen.generate_vmf("test.vmf")

print("done")
