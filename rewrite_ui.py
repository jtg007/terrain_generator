import re

with open('tools/terrain_generator.py', 'r') as f:
    content = f.read()

# Replace config layout creation
search_config = """        # ── Config scroll content ──
        config_layout = QVBoxLayout()
        config_layout.setSpacing(6)
        config_layout.setContentsMargins(14, 10, 14, 10)

        # ─── GENERAL ───
        sec_general = CollapsibleBox("GENERAL")
        config_layout.addWidget(sec_general)"""

replace_config = """        # ── Config scroll content ──
        config_layout = QVBoxLayout()
        config_layout.setSpacing(6)
        config_layout.setContentsMargins(14, 10, 14, 10)

        self.tab_widget = QTabWidget()
        config_layout.addWidget(self.tab_widget)

        self.tab_main = QScrollArea()
        self.tab_main.setWidgetResizable(True)
        self.tab_main.setFrameShape(QScrollArea.NoFrame)
        self.tab_main_content = QWidget()
        self.tab_main_layout = QVBoxLayout(self.tab_main_content)
        self.tab_main_layout.setAlignment(Qt.AlignTop)
        self.tab_main.setWidget(self.tab_main_content)

        self.tab_shape = QScrollArea()
        self.tab_shape.setWidgetResizable(True)
        self.tab_shape.setFrameShape(QScrollArea.NoFrame)
        self.tab_shape_content = QWidget()
        self.tab_shape_layout = QVBoxLayout(self.tab_shape_content)
        self.tab_shape_layout.setAlignment(Qt.AlignTop)
        self.tab_shape.setWidget(self.tab_shape_content)

        self.tab_gameplay = QScrollArea()
        self.tab_gameplay.setWidgetResizable(True)
        self.tab_gameplay.setFrameShape(QScrollArea.NoFrame)
        self.tab_gameplay_content = QWidget()
        self.tab_gameplay_layout = QVBoxLayout(self.tab_gameplay_content)
        self.tab_gameplay_layout.setAlignment(Qt.AlignTop)
        self.tab_gameplay.setWidget(self.tab_gameplay_content)

        self.tab_widget.addTab(self.tab_main, "Main")
        self.tab_widget.addTab(self.tab_shape, "Shape")
        self.tab_widget.addTab(self.tab_gameplay, "Gameplay")

        # ─── GENERAL ───
        lbl_sec_general = QLabel("GENERAL")
        lbl_sec_general.setObjectName("ConfigSection")
        self.tab_main_layout.addWidget(lbl_sec_general)

        sec_general = QWidget()
        sec_general.content_layout = QVBoxLayout(sec_general)
        sec_general.content_layout.setContentsMargins(0,0,0,0)
        self.tab_main_layout.addWidget(sec_general)"""

content = content.replace(search_config, replace_config)

# Replace DIMENSIONS
search_dim = """        # ─── MAP DIMENSIONS ───
        sec_dimensions = CollapsibleBox("MAP DIMENSIONS")
        config_layout.addWidget(sec_dimensions)"""

replace_dim = """        # ─── MAP DIMENSIONS ───
        lbl_sec_dimensions = QLabel("MAP DIMENSIONS")
        lbl_sec_dimensions.setObjectName("ConfigSection")
        self.tab_main_layout.addWidget(lbl_sec_dimensions)

        sec_dimensions = QWidget()
        sec_dimensions.content_layout = QVBoxLayout(sec_dimensions)
        sec_dimensions.content_layout.setContentsMargins(0,0,0,0)
        self.tab_main_layout.addWidget(sec_dimensions)"""

content = content.replace(search_dim, replace_dim)

# Replace SHAPE
search_shape = """        # ─── TERRAIN SHAPE ───
        sec_terrain_shape = CollapsibleBox("TERRAIN SHAPE")
        config_layout.addWidget(sec_terrain_shape)"""

replace_shape = """        # ─── TERRAIN SHAPE ───
        lbl_sec_terrain_shape = QLabel("TERRAIN SHAPE")
        lbl_sec_terrain_shape.setObjectName("ConfigSection")
        self.tab_shape_layout.addWidget(lbl_sec_terrain_shape)

        sec_terrain_shape = QWidget()
        sec_terrain_shape.content_layout = QVBoxLayout(sec_terrain_shape)
        sec_terrain_shape.content_layout.setContentsMargins(0,0,0,0)
        self.tab_shape_layout.addWidget(sec_terrain_shape)"""

content = content.replace(search_shape, replace_shape)

# Replace MAZE
search_maze = """        # ─── MAZE SETTINGS ───
        self.sec_maze_settings = CollapsibleBox("MAZE SETTINGS")
        config_layout.addWidget(self.sec_maze_settings)"""

replace_maze = """        # ─── MAZE SETTINGS ───
        self.lbl_sec_maze_settings = QLabel("MAZE SETTINGS")
        self.lbl_sec_maze_settings.setObjectName("ConfigSection")
        self.tab_shape_layout.addWidget(self.lbl_sec_maze_settings)

        self.sec_maze_settings = QWidget()
        self.sec_maze_settings.content_layout = QVBoxLayout(self.sec_maze_settings)
        self.sec_maze_settings.content_layout.setContentsMargins(0,0,0,0)
        self.tab_shape_layout.addWidget(self.sec_maze_settings)"""

content = content.replace(search_maze, replace_maze)

# Replace BASE AREAS
search_base = """        # ─── BASE AREAS ───
        sec_base_areas = CollapsibleBox("BASE AREAS")
        config_layout.addWidget(sec_base_areas)"""

replace_base = """        # ─── BASE AREAS ───
        lbl_sec_base_areas = QLabel("BASE AREAS")
        lbl_sec_base_areas.setObjectName("ConfigSection")
        self.tab_gameplay_layout.addWidget(lbl_sec_base_areas)

        sec_base_areas = QWidget()
        sec_base_areas.content_layout = QVBoxLayout(sec_base_areas)
        sec_base_areas.content_layout.setContentsMargins(0,0,0,0)
        self.tab_gameplay_layout.addWidget(sec_base_areas)"""

content = content.replace(search_base, replace_base)

# Replace MATERIALS
search_mat = """        # ─── MATERIALS ───
        sec_materials = CollapsibleBox("MATERIALS")
        config_layout.addWidget(sec_materials)"""

replace_mat = """        # ─── MATERIALS ───
        lbl_sec_materials = QLabel("MATERIALS")
        lbl_sec_materials.setObjectName("ConfigSection")
        self.tab_shape_layout.addWidget(lbl_sec_materials)

        sec_materials = QWidget()
        sec_materials.content_layout = QVBoxLayout(sec_materials)
        sec_materials.content_layout.setContentsMargins(0,0,0,0)
        self.tab_shape_layout.addWidget(sec_materials)"""

content = content.replace(search_mat, replace_mat)

# Replace SETTINGS
search_set = """        # ─── SETTINGS ───
        sec_settings = CollapsibleBox("SETTINGS")
        config_layout.addWidget(sec_settings)"""

replace_set = """        # ─── SETTINGS ───
        lbl_sec_settings = QLabel("SETTINGS")
        lbl_sec_settings.setObjectName("ConfigSection")
        self.tab_gameplay_layout.addWidget(lbl_sec_settings)

        sec_settings = QWidget()
        sec_settings.content_layout = QVBoxLayout(sec_settings)
        sec_settings.content_layout.setContentsMargins(0,0,0,0)
        self.tab_gameplay_layout.addWidget(sec_settings)"""

content = content.replace(search_set, replace_set)

# We also need to fix _update_maze_visibility to hide both the label and the widget
search_vis = """    def _update_maze_visibility(self):
        \"\"\"Show or hide maze settings depending on current topology.\"\"\"
        if self.combo_topology.currentText() == "Canyon Maze":
            self.sec_maze_settings.setVisible(True)
        else:
            self.sec_maze_settings.setVisible(False)"""

replace_vis = """    def _update_maze_visibility(self):
        \"\"\"Show or hide maze settings depending on current topology.\"\"\"
        if self.combo_topology.currentText() == "Canyon Maze":
            self.sec_maze_settings.setVisible(True)
            if hasattr(self, "lbl_sec_maze_settings"):
                self.lbl_sec_maze_settings.setVisible(True)
        else:
            self.sec_maze_settings.setVisible(False)
            if hasattr(self, "lbl_sec_maze_settings"):
                self.lbl_sec_maze_settings.setVisible(False)"""

content = content.replace(search_vis, replace_vis)

# And fix scroll_content wrapper
search_scroll = """        # Wrap in scroll area
        scroll_content = QWidget()
        scroll_content.setLayout(config_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumWidth(240)"""

replace_scroll = """        # Wrap in scroll area
        scroll_content = QWidget()
        scroll_content.setLayout(config_layout)

        scroll = scroll_content # The tabs themselves have scroll areas inside now
        scroll.setMinimumWidth(240)"""

content = content.replace(search_scroll, replace_scroll)


with open('tools/terrain_generator.py', 'w') as f:
    f.write(content)
