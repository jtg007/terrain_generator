import re

with open('tools/terrain_generator.py', 'r') as f:
    content = f.read()

# Fix sync_to_ui: add block signals and set values
search_block_signals = """            self.slider_plateau_noise,
            self.slider_erosion,
            self.slider_feature_scale,
            self.slider_lane_node_radius,
            self.slider_base_radius,"""

replace_block_signals = """            self.slider_plateau_noise,
            self.slider_erosion,
            self.slider_feature_scale,
            self.slider_lane_node_radius,
            self.slider_maze_size,
            self.slider_lane_numbers,
            self.slider_base_radius,"""

content = content.replace(search_block_signals, replace_block_signals)

search_sync_ui_values = """            self.slider_feature_scale.setValue(
                int(self.config_model.feature_scale * 100)
            )

            self.slider_base_radius.setValue(self.config_model.base_clear_radius)"""

replace_sync_ui_values = """            self.slider_feature_scale.setValue(
                int(self.config_model.feature_scale * 100)
            )

            self.slider_maze_size.setValue(self.config_model.maze_size)
            self.lbl_maze_size_val.setText(f"{self.config_model.maze_size}%")
            self.slider_lane_numbers.setValue(self.config_model.lane_numbers)
            self.lbl_lane_numbers_val.setText(str(self.config_model.lane_numbers))

            self.slider_base_radius.setValue(self.config_model.base_clear_radius)"""

content = content.replace(search_sync_ui_values, replace_sync_ui_values)

# Fix sync_to_model: get values
search_sync_model_values = """        self.config_model.feature_scale = self.slider_feature_scale.value() / 100.0

        self.config_model.base_clear_radius = self.slider_base_radius.value()"""

replace_sync_model_values = """        self.config_model.feature_scale = self.slider_feature_scale.value() / 100.0
        self.config_model.maze_size = self.slider_maze_size.value()
        self.config_model.lane_numbers = self.slider_lane_numbers.value()

        self.config_model.base_clear_radius = self.slider_base_radius.value()"""

content = content.replace(search_sync_model_values, replace_sync_model_values)

with open('tools/terrain_generator.py', 'w') as f:
    f.write(content)
