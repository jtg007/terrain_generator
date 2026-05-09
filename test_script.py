import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").absolute()))

from src.vmf_gen import DisplacementVMF, PipelineSpec
import json

def test():
    print("Testing PipelineSpec and Material defaults")
    spec = PipelineSpec(map_name="test_map")

    # Just checking if the file parses correctly after my edits
    print("Code parsed successfully")

if __name__ == "__main__":
    test()
