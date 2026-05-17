import pytest
import math
import numpy as np

from src.urban_spec import UrbanSpec, UrbanBlock, BlockType, RampPlacement, DistrictType
from src.urban_generator import (
    generate_urban_street_network, place_blocks, generate_urban_heightmap,
    validate_vehicle_paths, _create_wedge_brush
)
from src.terrain_spec import LayoutNode, LayoutConnection

def test_block_footprints_within_cells():
    spec = UrbanSpec(size_x=8192, size_y=8192, origin_x=0, origin_y=0, street_width=512)
    nodes, connections = generate_urban_street_network(spec, [])

    class DummyDistrict:
        district_type = DistrictType.RESIDENTIAL
        demolition_strength = 0.5
        bounds = (0, 0, 8192, 8192)

    blocks = place_blocks(spec, [DummyDistrict()], connections)

    # Check that each block's footprint stays within its allocated space
    for b in blocks:
        if b.block_type == BlockType.OPEN_LOT:
            continue

        # The block should not cross the node boundaries
        # And it should not be wider than actual_spacing - street_width
        avg_block_size = (spec.block_size_min + spec.block_size_max) / 2.0
        spacing = avg_block_size + spec.street_width

        actual_spacing_x = spec.size_x / max(2, int(spec.size_x / spacing))
        actual_spacing_y = spec.size_y / max(2, int(spec.size_y / spacing))

        assert b.footprint_w <= actual_spacing_x - spec.street_width
        assert b.footprint_d <= actual_spacing_y - spec.street_width

def test_heightmap_footprint_masks():
    spec = UrbanSpec(size_x=2048, size_y=2048, origin_x=0, origin_y=0, street_width=512)

    class DummyGrid:
        def __init__(self):
            self.rows = 64
            self.cols = 64
            self.heights = np.zeros((64, 64), dtype=np.float32)
            self.global_selection_mask = np.ones((64, 64), dtype=bool)

    grid = DummyGrid()
    blocks = [
        UrbanBlock(
            grid_x=0, grid_y=0, world_x=1024, world_y=1024,
            footprint_w=500, footprint_d=800, elevation_h=512,
            block_type=BlockType.INTACT, ramp_side=None, district=DistrictType.RESIDENTIAL,
            has_roof_resource=False, on_main_lane=False, adjacent_streets=[]
        )
    ]

    generate_urban_heightmap(spec, grid, blocks)

    # The heightmap raises elements exactly in the [world_x - w/2, world_x + w/2] range
    # Width=500 -> [-250, 250], Depth=800 -> [-400, 400]
    center_col = 32 # 1024 / (2048/64)
    center_row = 32

    # We just ensure it's not square
    raised_mask = grid.heights > spec.terrain_max_height * spec.lane_elevation
    raised_y, raised_x = np.nonzero(raised_mask)

    if len(raised_x) > 0:
        width_pixels = max(raised_x) - min(raised_x)
        depth_pixels = max(raised_y) - min(raised_y)

        # Ratio of width to depth should roughly match 500/800
        assert depth_pixels > width_pixels

def test_ramp_generation_valid():
    directions = [RampPlacement.NORTH, RampPlacement.SOUTH, RampPlacement.EAST, RampPlacement.WEST]
    for d in directions:
        brush = _create_wedge_brush(0, 0, 0, 192, 512, 256, d, "test_mat")
        assert len(brush.children) == 5, f"Ramp for {d} should have exactly 5 faces"

        # Verify normals or just that faces exist without error
        for side in brush.children:
            assert side.material == "test_mat"

def test_street_widths_not_mutated():
    spec = UrbanSpec(size_x=2048, size_y=2048, origin_x=0, origin_y=0, street_width=512)
    node1 = LayoutNode(0, 0, 100, 'vehicle_open_zone')
    node2 = LayoutNode(1024, 0, 100, 'vehicle_open_zone')

    from src.terrain_spec import ZoneType
    conn = LayoutConnection(node1, node2, 300, ZoneType.SIDE_ROUTE, [(0,0), (1024,0)])

    block = UrbanBlock(
            grid_x=0, grid_y=0, world_x=512, world_y=512,
            footprint_w=200, footprint_d=200, elevation_h=200,
            block_type=BlockType.INTACT, ramp_side=None, district=DistrictType.RESIDENTIAL,
            has_roof_resource=False, on_main_lane=False, adjacent_streets=[]
    )

    # Validate
    result = validate_vehicle_paths(spec, [node1, node2], [conn], [block])

    # Widths and geometry shouldn't change
    assert conn.width == 300
    assert node1.radius == 100
    assert block.footprint_w == 200
    assert block.world_x == 512
    assert block.world_y == 512
