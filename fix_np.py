with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# I need to change `Tuple[np.ndarray, np.ndarray]` to `Tuple['np.ndarray', 'np.ndarray']` or `Tuple[Any, Any]`
# since `np` is imported inside the function, not at the module level.
import re
content = content.replace("Tuple[np.ndarray, np.ndarray]", "Tuple['np.ndarray', 'np.ndarray']")

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
