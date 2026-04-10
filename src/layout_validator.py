from dataclasses import dataclass
from typing import List, Set, Tuple
import math

from src.terrain_spec import TerrainSpec


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    invalid_entities: Set[str]


class LayoutValidator:
    def validate(
        self,
        spec: TerrainSpec,
        imp_base: Tuple[float, float],
        nf_base: Tuple[float, float],
        resources: List[Tuple[float, float]],
    ) -> ValidationResult:
        errors = []
        invalid_entities = set()

        min_dim = min(spec.size_x, spec.size_y)

        # Distances and thresholds
        base_margin = 512
        res_margin = 256
        base_to_base_min_dist = 0.40 * min_dim
        res_to_base_min_dist = 0.15 * min_dim + spec.base_clear_radius
        res_to_res_min_dist = 0.10 * min_dim

        # Check Bases within bounds
        def check_bounds(
            entity_pos: Tuple[float, float], margin: float, entity_name: str
        ):
            x, y = entity_pos
            if (
                x < spec.origin_x + margin
                or x > spec.origin_x + spec.size_x - margin
                or y < spec.origin_y + margin
                or y > spec.origin_y + spec.size_y - margin
            ):
                return False
            return True

        if not check_bounds(imp_base, base_margin, "Imp Base"):
            errors.append(f"Imp Base is out of bounds (margin={base_margin}).")
            invalid_entities.add("imp")

        if not check_bounds(nf_base, base_margin, "NF Base"):
            errors.append(f"NF Base is out of bounds (margin={base_margin}).")
            invalid_entities.add("nf")

        # Check Resources within bounds
        for i, res in enumerate(resources):
            if not check_bounds(res, res_margin, f"Resource {i}"):
                errors.append(f"Resource {i} is out of bounds (margin={res_margin}).")
                invalid_entities.add(str(i))

        def get_dist(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
            return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

        # Base to Base
        dist_bases = get_dist(imp_base, nf_base)
        if dist_bases < base_to_base_min_dist:
            errors.append(
                f"Bases are too close to each other. Distance: {dist_bases:.1f}, Minimum: {base_to_base_min_dist:.1f}"
            )
            invalid_entities.add("imp")
            invalid_entities.add("nf")

        # Resource to Base
        for i, res in enumerate(resources):
            dist_imp = get_dist(res, imp_base)
            dist_nf = get_dist(res, nf_base)

            if dist_imp < res_to_base_min_dist:
                errors.append(
                    f"Resource {i} is too close to Imp Base. Distance: {dist_imp:.1f}, Minimum: {res_to_base_min_dist:.1f}"
                )
                invalid_entities.add("imp")
                invalid_entities.add(str(i))

            if dist_nf < res_to_base_min_dist:
                errors.append(
                    f"Resource {i} is too close to NF Base. Distance: {dist_nf:.1f}, Minimum: {res_to_base_min_dist:.1f}"
                )
                invalid_entities.add("nf")
                invalid_entities.add(str(i))

        # Resource to Resource
        for i in range(len(resources)):
            for j in range(i + 1, len(resources)):
                dist_res = get_dist(resources[i], resources[j])
                if dist_res < res_to_res_min_dist:
                    errors.append(
                        f"Resource {i} and Resource {j} are too close to each other. Distance: {dist_res:.1f}, Minimum: {res_to_res_min_dist:.1f}"
                    )
                    invalid_entities.add(str(i))
                    invalid_entities.add(str(j))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            invalid_entities=invalid_entities,
        )
