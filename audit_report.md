# Security and Code Health Audit Report

## Security Findings

### Critical
*(None found)*

### High
*(None found)*

### Medium
*(None found)*

### Low
1. **File:** `tools/terrain_generator.py` (Line 541, 1589)
   - **Risk:** Standard pseudo-random generators (`random.randint`) are used. While likely used for procedural generation, they are not cryptographically secure if ever repurposed for sensitive seed generation.
   - **Fix:** If security is a concern, consider using `secrets` module, otherwise this is a false positive for procedural generation.
2. **File:** `tools/generate_vmf.py` (Line 164, 205) / `tools/terrain_generator.py` (Line 292, 312, 2014, 2026)
   - **Risk:** Use of `subprocess.run`. While `shell=True` is not used, any execution of untrusted input (e.g., passing unsanitized UI paths to compiler args) could lead to unintended command execution.
   - **Fix:** Ensure all variables passed into `subprocess.run` (like `cmd` arrays or `path` variables) are strictly validated and not directly user-controlled without sanitization.
3. **File:** `tools/terrain_generator.py` (Line 312)
   - **Risk:** Starting a process (`spectacle`) with a partial executable path instead of an absolute path.
   - **Fix:** Provide the absolute path to the executable to avoid PATH manipulation attacks.
4. **File:** `tools/test_shape.py` (Line 23, 29)
   - **Risk:** Use of `assert`. Assertions are stripped when Python runs with the `-O` flag, potentially bypassing critical validation.
   - **Fix:** Use standard `if` statements and raise specific exceptions (e.g., `ValueError`) for production code, or ignore if strictly within the `tests/` boundary.

## Code Health Findings

### Critical
*(None found)*

### High
1. **File:** `src/steam_paths.py` (Line 44, 59) / `tools/compile_vmf.py` (Line 173) / `tools/generate_organic_vmf.py` (Line 179) / `tools/terrain_generator.py` (Line 132, 253, 324, 2047)
   - **Risk:** Broad exception handling (`except Exception:`) silently swallows errors, making debugging difficult and potentially masking critical failures.
   - **Fix:** Catch specific exceptions (e.g., `subprocess.TimeoutExpired`, `FileNotFoundError`) or at minimum log the full exception traceback before continuing.

### Medium
1. **File:** `terrain.sh` (Line 305, 316, 340, 363, 366)
   - **Risk:** Quotes are used on the right-hand side of `=~` operator in Bash, causing it to match as a literal string rather than a regular expression.
   - **Fix:** Remove quotes from the right-hand side of the `=~` operator.

### Low
1. **File:** `terrain.sh` (Line 339, 386, 401, 419, 442, 494, 775, 820)
   - **Risk:** Variable declaration and assignment are combined (`local var=$(cmd)`), which masks the return value (exit code) of the command.
   - **Fix:** Declare variables (`local var`) and assign them on the next line (`var=$(cmd)`).
2. **File:** `terrain.sh` (Line 274)
   - **Risk:** Potential style improvement for string replacement (ShellCheck code 2001).
   - **Fix:** Use native string replacement like `${variable//search/replace}` instead of spawning a subshell with `sed` or `tr` if applicable.
3. **Dead Code (Vulture Analysis - High Confidence > 80%)**
   - **File:** `tools/blend_mapper.py` (Line 264) - Unused variable `num_tiles`.
   - **File:** `tools/run_blend.py` (Line 130) - Unused variable `face_coords`.
   - **File:** `tools/terrain_gen.py` (Line 70) - Unused import `worldengine`.
   - **File:** `tools/terrain_generator.py` (Line 482) - Unused variable `suffix`.
   - **Fix:** Remove unused variables and imports to clean up the codebase.

### Low-Confidence Dead Code Findings (Vulture < 80%)
*Note: These are likely false positives due to dynamic dispatch, Qt signal connections, or API endpoints intended for external use, but are included for completeness.*
- **File:** `src/noise.py` - `_seed` attribute, `generate_heightmap_from_spec` function.
- **File:** `src/steam_paths.py` - `files` variable, `validate_empires_bin` function.
- **File:** `src/terrain_pipeline.py` - `WILDERNESS` variable.
- **File:** `src/terrain_spec.py` - `to_dict`, `from_dict`, `set_height`, `world_position`, `neighbor_heights`, `average_height`, `vertex_indices`, `get_vertex_height`, `world_bounds`.
- **File:** `src/vmf_gen.py` - `origin` attributes across multiple lines.
- **File:** `tools/blend_mapper.py` - `generate_vmf_blend_data` method.
- **File:** `tools/preview_widget.py` - `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent` methods (Qt events).
- **File:** `tools/run_blend.py` - `MATERIAL_MAP` variable, `_generate_alpha_for_face` method, `run_dispgen_with_blend` function.
- **File:** `tools/terrain_gen.py` - `TerrainGenerator` class, `get_preset_names`, `get_parameter_range`, `gen_params`, `generate_preview`, `generate_and_save`, `get_texture_suggestions`, `get_hamming_instructions`.
- **File:** `tools/terrain_generator.py` - `rbtn_imp`, `rbtn_nf`, `rbtn_res` attributes, `reset_to_safe` method.