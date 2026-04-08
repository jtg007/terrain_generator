#!/usr/bin/env python3
"""
Minimal ValveVMF compatibility layer.

Provides VMF, Solid, Side, DispInfo classes that generate
correct Source Engine VMF format output.

Key fixes from original:
- Added versioninfo, visgroups, viewsettings root blocks
- Fixed ID handling: solids start at 2, sides start at 3
- Reset ID counters for multiple VMF generations
"""

from typing import Dict, Optional, List, Tuple


class VersionInfo:
    """VMF version information block."""

    def __init__(self):
        self.editorversion: str = "400"
        self.editorbuild: str = "8849"
        self.mapversion: str = "1"
        self.formatversion: str = "100"
        self.prefab: str = "0"

    def __str__(self) -> str:
        lines = []
        lines.append("versioninfo")
        lines.append("{")
        lines.append(f'  "editorversion" "{self.editorversion}"')
        lines.append(f'  "editorbuild" "{self.editorbuild}"')
        lines.append(f'  "mapversion" "{self.mapversion}"')
        lines.append(f'  "formatversion" "{self.formatversion}"')
        lines.append(f'  "prefab" "{self.prefab}"')
        lines.append("}")
        return "\n".join(lines)


class VisGroups:
    """VMF visgroups block (empty but required)."""

    def __str__(self) -> str:
        return "visgroups\n{\n}"


class ViewSettings:
    """VMF viewsettings block (empty but required)."""

    def __str__(self) -> str:
        return "viewsettings\n{\n}"


class DispInfo:
    """Displacement information for a Side."""

    def __init__(self):
        self.power: int = 3
        self.startposition: str = "[0 0 0]"
        self.elevation: int = 0
        self.subdiv: int = 0
        self.normals: Dict[str, str] = {}
        self.distances: Dict[str, str] = {}
        self.offsets: Dict[str, str] = {}
        self.offset_normals: Dict[str, str] = {}
        self.triangle_tags: Dict[str, str] = {}
        self.alphas: Dict[str, str] = {}
        self.allowed_verts: Dict[str, str] = {}

    def __str__(self) -> str:
        lines = []
        lines.append("\t\t\tdispinfo")
        lines.append("\t\t\t{")
        lines.append(f'\t\t\t\t"power" "{self.power}"')
        lines.append(f'\t\t\t\t"startposition" "{self.startposition}"')
        lines.append('\t\t\t\t"flags" "0"')
        lines.append(f'\t\t\t\t"elevation" "{self.elevation}"')
        lines.append(f'\t\t\t\t"subdiv" "{self.subdiv}"')

        lines.append("\t\t\t\tnormals")
        lines.append("\t\t\t\t{")
        for key in sorted(self.normals.keys()):
            lines.append(
                f'\t\t\t\t\t"row{key.replace("row", "")}" "{self.normals[key]}"'
            )
        lines.append("\t\t\t\t}")

        lines.append("\t\t\t\tdistances")
        lines.append("\t\t\t\t{")
        for key in sorted(self.distances.keys()):
            lines.append(
                f'\t\t\t\t\t"row{key.replace("row", "")}" "{self.distances[key]}"'
            )
        lines.append("\t\t\t\t}")

        if self.offsets:
            lines.append("\t\t\t\toffsets")
            lines.append("\t\t\t\t{")
            for key in sorted(self.offsets.keys()):
                lines.append(
                    f'\t\t\t\t\t"row{key.replace("row", "")}" "{self.offsets[key]}"'
                )
            lines.append("\t\t\t\t}")

        if self.offset_normals:
            lines.append("\t\t\t\toffset_normals")
            lines.append("\t\t\t\t{")
            for key in sorted(self.offset_normals.keys()):
                lines.append(
                    f'\t\t\t\t\t"row{key.replace("row", "")}" "{self.offset_normals[key]}"'
                )
            lines.append("\t\t\t\t}")

        if self.alphas:
            lines.append("\t\t\t\talpha")
            lines.append("\t\t\t\t{")
            for key in sorted(self.alphas.keys()):
                lines.append(
                    f'\t\t\t\t\t"row{key.replace("row", "")}" "{self.alphas[key]}"'
                )
            lines.append("\t\t\t\t}")

        if self.triangle_tags:
            lines.append("\t\t\t\ttriangle_tags")
            lines.append("\t\t\t\t{")
            for key in sorted(self.triangle_tags.keys()):
                lines.append(
                    f'\t\t\t\t\t"row{key.replace("row", "")}" "{self.triangle_tags[key]}"'
                )
            lines.append("\t\t\t\t}")

        if self.allowed_verts:
            lines.append("\t\t\t\tallowed_verts")
            lines.append("\t\t\t\t{")
            for key in sorted(self.allowed_verts.keys()):
                lines.append(f'\t\t\t\t\t"{key}" "{self.allowed_verts[key]}"')
            lines.append("\t\t\t\t}")

        lines.append("\t\t\t}")
        return "\n".join(lines)


class Side:
    """A single face of a Solid brush."""

    _id_counter = 3  # Start at 3 (world=1, first solid=2, first side=3)

    @classmethod
    def reset_ids(cls):
        """Reset ID counter for new VMF generation."""
        cls._id_counter = 3

    def __init__(self):
        self.id: int = Side._id_counter
        Side._id_counter += 1
        self.plane: str = ""
        self.material: str = "TOOLS/TOOLSSKIP"
        self.uaxis: str = "[1 0 0 0] 0.25"
        self.vaxis: str = "[0 0 -1 0] 0.25"
        self.rotation: int = 0
        self.lightmapscale: int = 16
        self.smoothing_groups: int = 0
        self.dispinfo: Optional[DispInfo] = None

    def set_plane(self, v0: Tuple, v1: Tuple, v2: Tuple):
        """Set plane from 3 vertices."""
        self.plane = f"({v0[0]} {v0[1]} {v0[2]}) ({v1[0]} {v1[1]} {v1[2]}) ({v2[0]} {v2[1]} {v2[2]})"

    def __str__(self) -> str:
        lines = []
        lines.append("\t\tside")
        lines.append("\t\t{")
        lines.append(f'\t\t\t"id" "{self.id}"')
        lines.append(f'\t\t\t"plane" "{self.plane}"')
        lines.append(f'\t\t\t"smoothing_groups" "{self.smoothing_groups}"')
        lines.append(f'\t\t\t"material" "{self.material}"')
        lines.append(f'\t\t\t"uaxis" "{self.uaxis}"')
        lines.append(f'\t\t\t"vaxis" "{self.vaxis}"')
        lines.append(f'\t\t\t"rotation" "{self.rotation}"')
        lines.append(f'\t\t\t"lightmapscale" "{self.lightmapscale}"')

        if self.dispinfo:
            lines.append(str(self.dispinfo))

        lines.append("\t\t}")
        return "\n".join(lines)


class Solid:
    """A brush consisting of 6+ Sides."""

    _id_counter = 2  # Start at 2 (world is 1)

    @classmethod
    def reset_ids(cls):
        """Reset ID counter for new VMF generation."""
        cls._id_counter = 2

    def __init__(self):
        self.id: int = Solid._id_counter
        Solid._id_counter += 1
        self.sides: List[Side] = []

    def add_side(self, side: Side):
        """Add a Side to this Solid."""
        self.sides.append(side)

    def __str__(self) -> str:
        lines = []
        lines.append("\tsolid")
        lines.append("\t{")
        lines.append(f'\t\t"id" "{self.id}"')
        for side in self.sides:
            lines.append(str(side))
        lines.append("\t}")
        return "\n".join(lines)


class World:
    """The worldspawn entity."""

    def __init__(self):
        self.id: int = 1
        self.skyname: str = "sky_day01_01"
        self.mapversion: int = 220
        self.classname: str = "worldspawn"
        self.solids: List[Solid] = []

    def add_solid(self, solid: Solid):
        """Add a Solid to the world."""
        self.solids.append(solid)

    def __str__(self) -> str:
        lines = []
        lines.append("world")
        lines.append("{")
        lines.append(f'\t"id" "{self.id}"')
        lines.append(f'\t"skyname" "{self.skyname}"')
        lines.append(f'\t"mapversion" "{self.mapversion}"')
        lines.append(f'\t"classname" "{self.classname}"')
        for solid in self.solids:
            lines.append(str(solid))
        lines.append("}")
        return "\n".join(lines)


class VMF:
    """Top-level VMF document."""

    def __init__(self):
        self.versioninfo = VersionInfo()
        self.visgroups = VisGroups()
        self.viewsettings = ViewSettings()
        self.world = World()

    @classmethod
    def reset_ids(cls):
        """Reset all ID counters for new VMF generation."""
        Solid._id_counter = 2
        Side._id_counter = 3

    def __str__(self) -> str:
        return "\n".join(
            [
                str(self.versioninfo),
                str(self.visgroups),
                str(self.viewsettings),
                str(self.world),
            ]
        )
