from dataclasses import dataclass
from typing import List, Tuple, Any

@dataclass
class CompileBudget:
    max_brushes: int = 4096
    max_static_props: int = 512
    max_detail_props: int = 1024
    max_roofs: int = 64
    max_ruined_blocks: int = 32
    max_total_entity_count: int = 1024
    max_vis_complexity: int = 256

@dataclass
class BudgetReport:
    brush_count: int
    static_prop_count: int
    detail_prop_count: int
    roof_count: int
    ruined_block_count: int
    entity_count: int
    estimated_vis_complexity: int
    reductions_applied: List[str]
    within_budget: bool

def audit_budget(spec, blocks, vmf_doc) -> BudgetReport:
    from src.urban_spec import BlockType
    brush_count = 0
    static_prop_count = 0
    detail_prop_count = 0
    entity_count = 0

    # Count VMF elements
    if vmf_doc and hasattr(vmf_doc, "world"):
        # Count world brushes
        brush_count += len(vmf_doc.world.children) # Roughly, each block is a brush or entity. Actually block brushes are solid.
        # It's better to count actual solids
        solids = [c for c in vmf_doc.world.children if getattr(c, "__class__", None).__name__ == "Solid"]
        brush_count = len(solids)

        # In vmflib, entities are attached to valve_map.children (which is vmf_doc.children usually, or vmf_doc.world... wait, vmf_doc has world and children)
        # Static props are in world.children or vmf_doc.children
        all_ents = []
        if hasattr(vmf_doc, "children"):
            all_ents.extend([c for c in vmf_doc.children if getattr(c, "__class__", None).__name__ == "Entity"])
        if hasattr(vmf_doc.world, "children"):
            all_ents.extend([c for c in vmf_doc.world.children if getattr(c, "__class__", None).__name__ == "Entity"])

        entity_count = len(all_ents)
        static_props = [e for e in all_ents if getattr(e, "classname", "") == "prop_static"]
        static_prop_count = len(static_props)

        # Detail props are hard to count since they are emitted by VBSP, but we can estimate based on grass materials or use 0 for now.
        # Phase 8 prompt doesn't specify how to count detail props in VMF accurately besides "Count all... detail props currently in the VMF".
        # Source detail props aren't in the VMF, they are in the detail.vbsp. We will set to 0.
        detail_prop_count = 0

    roof_count = sum(1 for b in blocks if b.block_type == BlockType.INTACT) # Assuming all INTACT have roofs in Phase 4
    ruined_block_count = sum(1 for b in blocks if b.block_type == BlockType.RUINED)

    num_intersections = len(spec.custom_layout_nodes) if getattr(spec, "custom_layout_nodes", None) else 0
    estimated_vis_complexity = (sum(1 for b in blocks if b.block_type == BlockType.INTACT) * 4) + \
                               (ruined_block_count * 2) + \
                               num_intersections

    # Validate against budget
    budget = spec.compile_budget
    within = (brush_count <= budget.max_brushes and
              static_prop_count <= budget.max_static_props and
              detail_prop_count <= budget.max_detail_props and
              roof_count <= budget.max_roofs and
              ruined_block_count <= budget.max_ruined_blocks and
              entity_count <= budget.max_total_entity_count and
              estimated_vis_complexity <= budget.max_vis_complexity)

    return BudgetReport(
        brush_count=brush_count,
        static_prop_count=static_prop_count,
        detail_prop_count=detail_prop_count,
        roof_count=roof_count,
        ruined_block_count=ruined_block_count,
        entity_count=entity_count,
        estimated_vis_complexity=estimated_vis_complexity,
        reductions_applied=[],
        within_budget=within
    )

def enforce_budget(spec, blocks, vmf_doc, budget: CompileBudget) -> Tuple[List[Any], BudgetReport]:
    import math
    from src.urban_spec import BlockType
    from src.urban_generator import generate_vertical_layers
    from src.entity_placer import spawn_urban_props

    report = audit_budget(spec, blocks, vmf_doc)
    all_reductions = []

    if report.within_budget:
        return blocks, report

    if hasattr(spec, "size_x"):
        map_w = spec.size_x
        map_h = spec.size_y
        origin_x = spec.origin_x
        origin_y = spec.origin_y
    else:
        map_w = spec.terrain_tiles_x * spec.terrain_tile_size
        map_h = spec.terrain_tiles_y * spec.terrain_tile_size
        origin_x = -(map_w // 2)
        origin_y = -(map_h // 2)

    center_x = origin_x + map_w / 2.0
    center_y = origin_y + map_h / 2.0

    def dist_to_center(b):
        return math.sqrt((b.world_x - center_x)**2 + (b.world_y - center_y)**2)

    # Helper to regenerate VMF parts
    def regenerate_and_audit():
        # Strip urban elements from VMF
        if vmf_doc and hasattr(vmf_doc, "world"):
            # We can't easily distinguish urban solids from terrain solids without tracking them.
            # But we can assume all solids after the initial terrain generation are urban.
            # However, regenerating the whole thing is safer.
            pass

        # For the sake of this test, we won't fully clear VMF since it's complex to isolate urban vs terrain brushes.
        # Instead, we'll apply state changes to blocks and let the caller regenerate if needed, or we just estimate.
        # Actually, Phase 4 and 6 functions add to `vmf_doc.world.children`.
        # We can record the length of `vmf_doc.world.children` before Phase 4, and just truncate back to it!

        # Let's assume the caller will clear and regenerate.
        pass

    # Note: Because exact VMF counts require calling generate_vertical_layers/spawn_urban_props,
    # it's best to modify the state, then re-audit. Since we can't easily undo VMF additions cleanly
    # without a marker, we'll implement the logic in vmf_gen to call enforce_budget inside a generation loop
    # or we handle the loop here by truncating `vmf_doc.world.children`.

    # To properly implement "re-auditing after each step", we need a reliable way to recreate the VMF urban parts.
    # We will accept an initial world_children length and children length from vmf_doc to truncate before regenerating.
    initial_world_len = getattr(vmf_doc, "_urban_initial_world_len", len(vmf_doc.world.children) if vmf_doc else 0)
    initial_children_len = getattr(vmf_doc, "_urban_initial_children_len", len(vmf_doc.children) if vmf_doc else 0)

    def apply_reductions_and_audit(step_fn, description_fn) -> bool:
        """Applies reduction function, regenerates VMF, audits, returns True if within budget."""
        # Find blocks furthest from center
        sorted_blocks = sorted(blocks, key=dist_to_center, reverse=True)

        for b in sorted_blocks:
            if step_fn(b):
                all_reductions.append(description_fn(b))

                # Regenerate VMF
                if vmf_doc:
                    vmf_doc.world.children = vmf_doc.world.children[:initial_world_len]
                    vmf_doc.children = vmf_doc.children[:initial_children_len]

                    generate_vertical_layers(spec, blocks, vmf_doc)
                    spawn_urban_props(vmf_doc, spec, blocks)

                new_report = audit_budget(spec, blocks, vmf_doc)
                if new_report.within_budget:
                    new_report.reductions_applied = all_reductions
                    return new_report
        return False

    # 1. Remove irregular wall variations from RUINED blocks
    def step1(b):
        if b.block_type == BlockType.RUINED and not b.downgraded_flat_walls:
            b.downgraded_flat_walls = True
            return True
        return False
    if report := apply_reductions_and_audit(step1, lambda b: f"Downgraded RUINED block at {b.grid_x},{b.grid_y} to flat walls"):
        return blocks, report

    # 2. Reduce prop density on RUBBLE blocks by 50%
    # We apply this globally as per Phase 6, but just once.
    if not getattr(spec, "_urban_reduced_density", False):
        spec._urban_reduced_density = True
        all_reductions.append("Reduced global prop density by 50%")
        if vmf_doc:
            vmf_doc.world.children = vmf_doc.world.children[:initial_world_len]
            vmf_doc.children = vmf_doc.children[:initial_children_len]
            generate_vertical_layers(spec, blocks, vmf_doc)
            spawn_urban_props(vmf_doc, spec, blocks)
        new_report = audit_budget(spec, blocks, vmf_doc)
        if new_report.within_budget:
            new_report.reductions_applied = all_reductions
            return blocks, new_report

    # 3. Remove rooftop cover props from blocks furthest from center
    def step3(b):
        if getattr(b, "needs_rooftop_cover", False):
            b.needs_rooftop_cover = False
            return True
        return False
    if report := apply_reductions_and_audit(step3, lambda b: f"Removed rooftop cover from block at {b.grid_x},{b.grid_y}"):
        return blocks, report

    # 4. Downgrade RUINED blocks furthest from center to RUBBLE
    def step4(b):
        if b.block_type == BlockType.RUINED:
            b.block_type = BlockType.RUBBLE
            return True
        return False
    if report := apply_reductions_and_audit(step4, lambda b: f"Downgraded RUINED block at {b.grid_x},{b.grid_y} to RUBBLE"):
        return blocks, report

    # 5. Remove ramps from INTACT blocks furthest from center
    def step5(b):
        if b.block_type == BlockType.INTACT and getattr(b, "ramp_side", None) is not None:
            b.ramp_side = None
            return True
        return False
    if report := apply_reductions_and_audit(step5, lambda b: f"Removed ramp from INTACT block at {b.grid_x},{b.grid_y}"):
        return blocks, report

    # 6. Downgrade INTACT blocks furthest from center to RUINED
    def step6(b):
        if b.block_type == BlockType.INTACT:
            b.block_type = BlockType.RUINED
            return True
        return False
    if report := apply_reductions_and_audit(step6, lambda b: f"Downgraded INTACT block at {b.grid_x},{b.grid_y} to RUINED"):
        return blocks, report

    # If we got here, we failed to meet the budget
    final_report = audit_budget(spec, blocks, vmf_doc)
    final_report.reductions_applied = all_reductions

    # Identify violations
    violations = []
    if final_report.brush_count > budget.max_brushes:
        violations.append(f"Brushes: {final_report.brush_count} > {budget.max_brushes}")
    if final_report.static_prop_count > budget.max_static_props:
        violations.append(f"Static Props: {final_report.static_prop_count} > {budget.max_static_props}")
    if final_report.detail_prop_count > budget.max_detail_props:
        violations.append(f"Detail Props: {final_report.detail_prop_count} > {budget.max_detail_props}")
    if final_report.roof_count > budget.max_roofs:
        violations.append(f"Roofs: {final_report.roof_count} > {budget.max_roofs}")
    if final_report.ruined_block_count > budget.max_ruined_blocks:
        violations.append(f"Ruined Blocks: {final_report.ruined_block_count} > {budget.max_ruined_blocks}")
    if final_report.entity_count > budget.max_total_entity_count:
        violations.append(f"Total Entities: {final_report.entity_count} > {budget.max_total_entity_count}")
    if final_report.estimated_vis_complexity > budget.max_vis_complexity:
        violations.append(f"Vis Complexity: {final_report.estimated_vis_complexity} > {budget.max_vis_complexity}")

    raise ValueError("Compile budget limits exceeded after all reductions applied:\n" + "\n".join(violations))
