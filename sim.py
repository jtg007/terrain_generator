import sys
sys.path.insert(0, "src")
from terrain_spec import TerrainSpec
from terrain_pipeline import run_pipeline

spec = TerrainSpec()
spec.topology = "Canyon Maze"
spec.lane_width_scale = 0.29
spec.maze_size = 50
spec.lane_numbers = 5

run_pipeline(spec)
