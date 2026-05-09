1. **Fix 1: Cliff threshold**:
   In `src/vmf_gen.py`, change `is_cliff = slope > 0.2` to `is_cliff = slope > 2.5`.
2. **Fix 2 & 3 & 4**:
   Before the outer loop (`for row_idx in range(tiles_y):`), add:
   ```python
        map_z_min = float(working_heightmap.min()) * height_scale
        map_z_max = float(working_heightmap.max()) * height_scale
        band_list = []
   ```

   Replace the zone_score band logic:
   ```python
                if is_cliff:
                    band = "cliff"
                elif zone_score > 0.7:
                    band = "low" # ACTION ZONE
                elif zone_score > 0.3:
                    band = "transition" # TRANSITION BELT
                else:
                    band = "valley" # SCENERY ZONE
   ```
   with:
   ```python
                # Compute mean tile height in world units
                corners = []
                for dy in (0, grid_size - 1):
                    for dx in (0, grid_size - 1):
                        cpx = min(col_idx * (grid_size - 1) + dx, img_width - 1)
                        cpy = min(row_idx * (grid_size - 1) + dy, img_height - 1)
                        corners.append(working_heightmap[cpy, cpx] * height_scale)
                tile_z = sum(corners) / 4.0

                z_range = map_z_max - map_z_min
                ratio = (tile_z - map_z_min) / z_range if z_range > 200 else 0.5

                # Deterministic per-tile noise to prevent hard rings
                noise = ((col_idx * 2654435761 ^ row_idx * 2246822519) & 0xFFFFFF)
                noise = (noise / 0xFFFFFF - 0.5) * 0.12
                ratio = max(0.0, min(1.0, ratio + noise))

                if is_cliff:
                    band = "cliff"
                elif ratio > 0.78:
                    band = "peak"
                elif ratio > 0.55:
                    band = "high"
                elif ratio > 0.35:
                    band = "mid"
                elif ratio > 0.15:
                    band = "low"
                elif ratio > 0.05:
                    band = "transition"
                else:
                    band = "valley"

                band_list.append(band)

                if col_idx == 0 and row_idx == 0:
                    print(f"[Terrain] map_z range: {map_z_min:.0f} to {map_z_max:.0f}")
                    print(f"[Terrain] tile(0,0): z={tile_z:.0f} ratio={ratio:.2f} "
                          f"slope={slope:.3f} band={band}")
   ```
   And after the double loop completes, add:
   ```python
        from collections import Counter
        print(f"[Terrain] Band distribution: {dict(Counter(band_list))}")
   ```
3. Run `python3 test_vmf.py` to verify the outputs.
4. Call `pre_commit_instructions` and follow pre-commit checks.
5. Submit the changes.
