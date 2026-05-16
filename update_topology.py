import re

file_path = "tools/terrain_generator.py"

with open(file_path, "r") as f:
    content = f.read()

# Update UI addItems
content = re.sub(
    r'self\.combo_topology\.addItems\(\s*\[\s*"Canyon Maze",\s*\]\s*\)',
    'self.combo_topology.addItems([\n                "Canyon Maze",\n                "Urban",\n            ])',
    content
)

# Update sync_to_ui
content = re.sub(
    r'# We currently only have Canyon Maze \(index 0 -> "canyon"\)\s+self\.combo_topology\.setCurrentIndex\(0\)',
    'if self.config_model.topology.lower() == "urban":\n                self.combo_topology.setCurrentIndex(1)\n            else:\n                self.combo_topology.setCurrentIndex(0)',
    content
)

# Update sync_to_model
content = re.sub(
    r'# We currently only have Canyon Maze \(index 0 -> "canyon"\)\s+self\.config_model\.topology = "canyon"\s+self\.config_model\.canyon_natural = False',
    'if self.combo_topology.currentText() == "Urban":\n            self.config_model.topology = "urban"\n        else:\n            self.config_model.topology = "canyon"\n        self.config_model.canyon_natural = False',
    content
)

with open(file_path, "w") as f:
    f.write(content)
