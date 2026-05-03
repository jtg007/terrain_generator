#!/usr/bin/env python3
"""
VMF Writer powered by pySourceSDK / ValveVMF

This writer uses the object-oriented API of ValveVMF.
Geometry errors ("Inside-Out", "17 solids not loaded") are now
a thing of the past, as the library handles the exact formatting.
"""

from typing import List
from pathlib import Path
import sys

from ValveVMF import VMF, Solid, Side, DispInfo

from src.terrain_spec import TerrainSpec, HeightGrid, TerrainCell, UnderlayBrush
from src.terrain_pipeline import (
    get_cell_heightmap,
    get_cell_normals,
    get_cell_alphas,
)


class ValveVMFWriter:
    """Writes VMF files using the ValveVMF library."""

    def __init__(self):
        VMF.reset_ids()  # Reset IDs before new generation
        self.vmf = VMF()

    def write_vmf(
        self,
        cells: List[TerrainCell],
        underlay: UnderlayBrush,
        grid: HeightGrid,
        spec: TerrainSpec,
        path: str,
    ):
        """Generiert die Solids und speichert die Datei."""
        self.vmf.world.skyname = "sky_day01_01"

        for cell in cells:
            self._create_displacement_brush(cell, grid, spec)

        self._create_underlay_brush(underlay)

        with open(path, "w") as f:
            f.write(str(self.vmf))

        print(f"VMF erfolgreich über ValveVMF geschrieben: {path}")

    def _create_displacement_brush(
        self,
        cell: TerrainCell,
        grid: HeightGrid,
        spec: TerrainSpec,
    ):
        """Erzeugt einen perfekten Basis-Brush und legt die Höhenkarte als DispInfo auf die Top-Fläche."""
        power = spec.displacement_power
        cell_size = spec.cell_size
        vertices_per_tile = 2**power

        heights = get_cell_heightmap(cell, grid, power)
        normals = get_cell_normals(heights, power)
        alphas = get_cell_alphas(cell, grid, power)

        # Flip the cell block vertically to match North-West startposition!
        heights.reverse()
        normals.reverse()
        alphas.reverse()

        tile_col = cell.grid_col // vertices_per_tile
        tile_row = cell.grid_row // vertices_per_tile

        X1 = int(spec.origin_x + tile_col * cell_size)
        X2 = int(X1 + cell_size)
        Y1 = int(spec.origin_y + tile_row * cell_size)
        Y2 = int(Y1 + cell_size)
        Z2 = 0
        Z1 = -32

        solid = Solid()

        top_side = Side()
        top_side.set_plane((X1, Y1, Z2), (X2, Y1, Z2), (X2, Y2, Z2))
        top_side.material = spec.material
        top_side.uaxis = "[1 0 0 0] 0.25"
        top_side.vaxis = "[0 -1 0 0] 0.25"

        disp = DispInfo()
        disp.power = power
        # NW corner is [min_x max_y max_z]
        disp.startposition = f"[{int(X1)} {int(Y2)} {int(Z2)}]"
        disp.elevation = 0
        disp.subdiv = 0

        # Use Hammer default V axis [0 -1 0]
        top_side.vaxis = "[0 -1 0 0] 0.25"

        disp.distances = {}
        disp.normals = {}
        disp.alphas = {}
        disp.allowed_verts = {}
        grid_size = len(heights)
        for row_idx in range(grid_size):
            h_str = " ".join(str(int(round(h))) for h in heights[row_idx])
            disp.distances[f"row{row_idx}"] = h_str
            n_str = " ".join(f"{nx} {ny} {nz}" for nx, ny, nz in normals[row_idx])
            disp.normals[f"row{row_idx}"] = n_str
            a_str = " ".join(str(int(alpha)) for alpha in alphas[row_idx])
            disp.alphas[f"row{row_idx}"] = a_str

        # Empires expects exactly the key "10" for all displacement allowed_verts
        disp.allowed_verts["10"] = "-1 -1 -1 -1 -1 -1 -1 -1 -1 -1"

        top_side.dispinfo = disp
        solid.add_side(top_side)

        # 2. Bottom Face
        bottom_side = Side()
        bottom_side.set_plane((X1, Y2, Z1), (X2, Y2, Z1), (X2, Y1, Z1))
        bottom_side.material = "TOOLS/TOOLSNODRAW"
        bottom_side.uaxis = "[1 0 0 0] 0.25"
        bottom_side.vaxis = "[0 -1 0 0] 0.25"
        solid.add_side(bottom_side)

        # 3. Min-Y Wall (South)
        south_side = Side()
        south_side.set_plane((X1, Y1, Z2), (X1, Y1, Z1), (X2, Y1, Z1))
        south_side.material = "TOOLS/TOOLSNODRAW"
        south_side.uaxis = "[1 0 0 0] 0.25"
        south_side.vaxis = "[0 0 -1 0] 0.25"
        solid.add_side(south_side)

        # 4. Max-Y Wall (North)
        north_side = Side()
        north_side.set_plane((X2, Y2, Z2), (X2, Y2, Z1), (X1, Y2, Z1))
        north_side.material = "TOOLS/TOOLSNODRAW"
        north_side.uaxis = "[1 0 0 0] 0.25"
        north_side.vaxis = "[0 0 -1 0] 0.25"
        solid.add_side(north_side)

        # 5. Min-X Wall (West)
        west_side = Side()
        west_side.set_plane((X1, Y2, Z2), (X1, Y2, Z1), (X1, Y1, Z1))
        west_side.material = "TOOLS/TOOLSNODRAW"
        west_side.uaxis = "[0 1 0 0] 0.25"
        west_side.vaxis = "[0 0 -1 0] 0.25"
        solid.add_side(west_side)

        # 6. Max-X Wall (East)
        east_side = Side()
        east_side.set_plane((X2, Y1, Z2), (X2, Y1, Z1), (X2, Y2, Z1))
        east_side.material = "TOOLS/TOOLSNODRAW"
        east_side.uaxis = "[0 1 0 0] 0.25"
        east_side.vaxis = "[0 0 -1 0] 0.25"
        solid.add_side(east_side)

        self.vmf.world.add_solid(solid)

    def _create_underlay_brush(self, underlay: UnderlayBrush):
        """Erzeugt die große Underlay-Box."""
        X1 = underlay.origin_x
        Y1 = underlay.origin_y
        X2 = X1 + underlay.size_x
        Y2 = Y1 + underlay.size_y
        Z1 = underlay.bottom_z
        Z2 = underlay.top_z
        mat = "TOOLS/TOOLSNODRAW"

        solid = Solid()

        s_top = Side()
        s_top.set_plane((X1, Y1, Z2), (X2, Y1, Z2), (X2, Y2, Z2))
        s_top.material = mat
        solid.add_side(s_top)

        s_bot = Side()
        s_bot.set_plane((X1, Y2, Z1), (X2, Y2, Z1), (X2, Y1, Z1))
        s_bot.material = mat
        solid.add_side(s_bot)

        s_miny = Side()
        s_miny.set_plane((X1, Y1, Z2), (X1, Y1, Z1), (X2, Y1, Z1))
        s_miny.material = mat
        solid.add_side(s_miny)

        s_maxy = Side()
        s_maxy.set_plane((X2, Y2, Z2), (X2, Y2, Z1), (X1, Y2, Z1))
        s_maxy.material = mat
        solid.add_side(s_maxy)

        s_minx = Side()
        s_minx.set_plane((X1, Y2, Z2), (X1, Y2, Z1), (X1, Y1, Z1))
        s_minx.material = mat
        solid.add_side(s_minx)

        s_maxx = Side()
        s_maxx.set_plane((X2, Y1, Z2), (X2, Y1, Z1), (X2, Y2, Z1))
        s_maxx.material = mat
        solid.add_side(s_maxx)

        self.vmf.world.add_solid(solid)


def export_vmf(
    cells: List[TerrainCell],
    underlay: UnderlayBrush,
    grid: HeightGrid,
    spec: TerrainSpec,
    path: str,
):
    writer = ValveVMFWriter()
    writer.write_vmf(cells, underlay, grid, spec, path)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent))

    from terrain_spec import create_default_spec
    from terrain_pipeline import run_pipeline

    print("Starte VMF Generierung mit ValveVMF...")
    result = run_pipeline(create_default_spec())

    if result["errors"]:
        print("ERRORS during pipeline:")
        for e in result["errors"]:
            print(f"  {e}")
    else:
        output_path = "output/terrain_valvevmf.vmf"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        export_vmf(
            result["cells"],
            result["underlay"],
            result["grid"],
            result["spec"],
            output_path,
        )
