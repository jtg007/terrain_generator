import os
from pathlib import Path

# Smart detail system constraints
REFERENCE_AREA = 8192.0 * 8192.0  # 67,108,864 sq units
BASE_DENSITY = 400.0
MAX_DENSITY = 600.0
MIN_DENSITY = 30.0

def calculate_smart_density(map_size_x: int, map_size_y: int) -> float:
    """
    Calculates a safe detail density from map size using an inverse proportional formula.
    Ensures that total detail props never exceed the engine ceiling.
    """
    current_map_area = float(map_size_x * map_size_y)
    if current_map_area <= 0:
        return BASE_DENSITY

    raw_density = BASE_DENSITY * (REFERENCE_AREA / current_map_area)
    final_density = max(MIN_DENSITY, min(MAX_DENSITY, raw_density))

    print(f"[Smart Detail] Map size: {map_size_x}x{map_size_y} (Area: {current_map_area})")
    print(f"[Smart Detail] Calculated density: {final_density:.2f} (Raw: {raw_density:.2f})")

    return final_density

def generate_auto_detail_vbsp(project_root: Path, density: float) -> str:
    """
    Generates auto_detail.vbsp with the calculated density.
    Returns the relative path to the generated file.
    """
    vmf_assets_dir = project_root / "materials" / "vmf_generator_assets"
    vmf_assets_dir.mkdir(parents=True, exist_ok=True)

    file_path = vmf_assets_dir / "auto_detail.vbsp"

    # Standard grass sprite template
    content = f"""detail
{{
	auto_grass_profile
	{{
		density {density:.2f}
		Group1
		{{
			alpha 1.0
			Model1
			{{
				sprite "0 0 128 128 512"
				spritesize "0.5 0.0 24 24"
				spriterandomscale 0.2
				amount 1.0
				detailOrientation 2
				upright 1
			}}
		}}
	}}
}}
"""
    file_path.write_text(content)
    print(f"[Smart Detail] Generated detail script at: {file_path}")
    return "materials/vmf_generator_assets/auto_detail.vbsp"

def generate_smart_vmt_patch(project_root: Path, original_material: str) -> str:
    """
    Generates a _smartdetail VMT patch for the original material.
    Returns the new material name (without materials/ or .vmt).
    """
    vmf_assets_dir = project_root / "materials" / "vmf_generator_assets"
    vmf_assets_dir.mkdir(parents=True, exist_ok=True)

    # Strip materials/ and .vmt if present to get standard path
    if original_material.startswith("materials/"):
        original_material = original_material[len("materials/"):]
    if original_material.endswith(".vmt"):
        original_material = original_material[:-4]

    material_name = Path(original_material).stem
    new_material_name = f"{material_name}_smartdetail"

    new_vmt_path = vmf_assets_dir / f"{new_material_name}.vmt"

    content = f"""Patch
{{
    include "materials/{original_material}.vmt"
    insert
    {{
        "%detailtype" "auto_grass_profile"
    }}
}}
"""
    new_vmt_path.write_text(content)
    print(f"[Smart Detail] Generated smart VMT patch at: {new_vmt_path}")

    return f"vmf_generator_assets/{new_material_name}"
