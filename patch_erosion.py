import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# We need to insert:
# playability_mask = getattr(grid, 'playability_mask', None)
# inside simulate_hydraulic_erosion before the loop

target_start = """    rng = random.Random(spec.seed + 1000)

    for _ in range(iterations):
        start_r = rng.randint(1, rows - 2)
        start_c = rng.randint(1, cols - 2)"""

replacement_start = """    rng = random.Random(spec.seed + 1000)

    # Fetch mask safely
    playability_mask = getattr(grid, 'playability_mask', None)

    for _ in range(iterations):
        start_r = rng.randint(1, rows - 2)
        start_c = rng.randint(1, cols - 2)

        # Protect playable lanes: DO NOT spawn droplets on paths or bases
        if playability_mask is not None and playability_mask[start_r, start_c] > 0.5:
            continue"""

content = content.replace(target_start, replacement_start)

# We also need to insert:
# if playability_mask is not None and playability_mask[ir, ic] > 0.5: break
# inside the loop for step in range(lifetime):

target_step = """        for step in range(lifetime):
            ir = int(pos_r)
            ic = int(pos_c)

            if ir <= 0 or ir >= rows - 1 or ic <= 0 or ic >= cols - 1:
                break"""

replacement_step = """        for step in range(lifetime):
            ir = int(pos_r)
            ic = int(pos_c)

            if ir <= 0 or ir >= rows - 1 or ic <= 0 or ic >= cols - 1:
                break

            # Protect playable lanes: droplets instantly evaporate when hitting a lane
            if playability_mask is not None and playability_mask[ir, ic] > 0.5:
                break"""

content = content.replace(target_step, replacement_step)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
