import sys
import json
import random
from pathlib import Path

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "config"))

import os

if not getattr(sys, "frozen", False):
    os.chdir(PROJECT_ROOT)

from PySide6.QtWidgets import (
    QApplication,
    QRadioButton,
    QButtonGroup,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QComboBox,
    QGroupBox,
    QMessageBox,
    QFileDialog,
    QCheckBox,
    QLineEdit,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QImage
from tools.preview_widget import MapPreviewWidget

from PIL import Image
import numpy as np

from src.config_model import GUIConfigModel
from src.terrain_pipeline import run_pipeline
from src.vmf_gen import (
    PipelineSpec,
    DisplacementVMF,
    SAFE_EMPIRES_SKYBOXES,
    DEFAULT_SAFE_SKYBOX,
)
from src.steam_paths import validate_empires_path
from config import Config

# Ensure OUTPUT_DIR is outside of _internal when bundled
if getattr(sys, "frozen", False):
    OUTPUT_DIR = Path(sys.executable).parent / "output"
else:
    OUTPUT_DIR = PROJECT_ROOT / "output"

# Make sure it exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def heightgrid_to_heightmap(
    grid, target_rows: int = 0, target_cols: int = 0
) -> np.ndarray:
    min_h = grid.min_height()
    max_h = grid.max_height()
    h_range = max_h - min_h
    if h_range < 1e-6:
        return np.zeros((grid.rows, grid.cols), dtype=np.float32)

    normalized = np.array(
        [
            [(grid.heights[r][c] - min_h) / h_range for c in range(grid.cols)]
            for r in range(grid.rows)
        ],
        dtype=np.float32,
    )
    normalized = np.clip(normalized, 0.0, 1.0)

    if target_rows > grid.rows or target_cols > grid.cols:
        from scipy.ndimage import zoom

        scale_y = target_rows / grid.rows
        scale_x = target_cols / grid.cols
        normalized = zoom(normalized, (scale_y, scale_x), order=1)

    return normalized


COMPILE_SAFE_NODETAIL_MATERIAL = "common/terrain/blend_grass01a_dirt01a_nodetail"


def choose_compile_safe_material(
    requested_material: str, map_width: int, map_height: int
) -> str:
    """Choose a safe terrain material for large maps to avoid detail prop overflow."""
    if "nodetail" in requested_material.lower():
        return requested_material

    large_map_threshold = 8192 * 8192
    if map_width * map_height >= large_map_threshold:
        return COMPILE_SAFE_NODETAIL_MATERIAL

    return requested_material


class PreviewWorker(QThread):
    finished = Signal(object, object)  # grid, spec

    def __init__(self, config_model):
        super().__init__()
        self.config_model = config_model

    def run(self):
        try:
            # We must not modify the original model's spec, but we can make a custom spec
            spec = self.config_model.make_spec()
            spec.displacement_power = 2  # Force low power for speed
            spec.erosion_iterations = 0  # Disable erosion for instant preview
            spec.disable_commander = True
            spec.disable_buildings = True
            spec.disable_resource_nodes = True

            result = run_pipeline(spec)
            self.finished.emit(result["grid"], result["spec"])
        except Exception:
            self.finished.emit(None, None)


class GenerationWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, config_model, output_filename="gui_terrain"):
        super().__init__()
        self.config_model = config_model
        self.output_filename = output_filename

    def run(self):
        try:
            spec = self.config_model.make_spec()

            result = run_pipeline(spec)
            if result["errors"]:
                raise Exception(f"Pipeline errors: {result['errors']}")

            grid = result["grid"]

            tile_size = self.config_model.cell_size
            displacement_power = self.config_model.displacement_power

            grid_size = (2**displacement_power) + 1
            tiles_x = spec.size_x // tile_size
            tiles_y = spec.size_y // tile_size
            map_width = tiles_x * tile_size
            map_height = tiles_y * tile_size
            compile_safe_material = choose_compile_safe_material(
                self.config_model.terrain_material,
                map_width,
                map_height,
            )

            vertex_cols = tiles_x * (grid_size - 1) + 1
            vertex_rows = tiles_y * (grid_size - 1) + 1

            heightmap = heightgrid_to_heightmap(grid, vertex_rows, vertex_cols)

            hm_array = (heightmap * 255).astype(np.uint8)
            hm_img = Image.fromarray(hm_array, mode="L")
            hm_path = OUTPUT_DIR / f"{self.output_filename}_temp.png"
            hm_img.save(hm_path)

            calculated_max_height = self.config_model.height_scale

            vmf_spec = PipelineSpec(
                map_name=self.output_filename,
                heightmap_path=str(hm_path),
                terrain_max_height=calculated_max_height,
                terrain_actual_max=grid.max_height(),
                terrain_tile_size=tile_size,
                terrain_power=self.config_model.displacement_power,
                terrain_material=compile_safe_material,
                skybox=self.config_model.skybox,
                terrain_tiles_x=tiles_x,
                terrain_tiles_y=tiles_y,
                output_dir=str(OUTPUT_DIR),
                use_enhanced_spawning=True,
                disable_commander=self.config_model.disable_commander,
                disable_buildings=self.config_model.disable_buildings,
                disable_resource_nodes=self.config_model.disable_resource_nodes,
                minimal_map=self.config_model.minimal_map,
                terrain_only=self.config_model.terrain_only,
                custom_imp_base_x=self.config_model.custom_imp_base_x,
                custom_imp_base_y=self.config_model.custom_imp_base_y,
                custom_nf_base_x=self.config_model.custom_nf_base_x,
                custom_nf_base_y=self.config_model.custom_nf_base_y,
                custom_resources=self.config_model.custom_resources,
            )

            vmf_gen = DisplacementVMF(vmf_spec)
            vmf_gen.load_heightmap(str(hm_path), auto_resize=False)

            vmf_path = OUTPUT_DIR / f"{self.output_filename}.vmf"
            vmf_gen.generate_vmf(str(vmf_path))

            origin_x = -(map_width // 2)
            origin_y = -(map_height // 2)
            resource_content = f'''"{self.output_filename}"
{{
	"image"		"maps/{self.output_filename}"

	"min_image_x"	"0"
	"min_image_y"	"0"

	"max_image_x"	"1024"
	"max_image_y"	"1024"
	
	"min_bounds_x"	"{origin_x}"
	"min_bounds_y"	"{origin_y}"

	"max_bounds_x"	"{origin_x + map_width}"
	"max_bounds_y"	"{origin_y + map_height}"

	"sector_width"	"512"
	"sector_height"	"512"

	"min_zoom"	"1"
	"max_zoom"	"0.25"

	"nf_description" "GUI generated terrain."
	"nf_objective" "Build refineries to gain resources and destroy the enemy command vehicle."
	"imp_description" "GUI generated terrain."
	"imp_objective" "Build refineries to gain resources and destroy the enemy command vehicle."
}}
'''
            resource_file = OUTPUT_DIR / f"{self.output_filename}.txt"
            resource_file.write_text(resource_content)

            hm_path.unlink(missing_ok=True)

            message = f"VMF saved: {vmf_path}"
            if compile_safe_material != self.config_model.terrain_material:
                message += (
                    "\nLarge map safety: switched terrain material to "
                    f"{compile_safe_material}"
                )
            self.finished.emit(True, message)
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))


class TerrainGeneratorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modern Terrain Generator")
        self.resize(1150, 750)

        self.config_model = GUIConfigModel()
        self.config = Config()
        self.presets = self.load_presets()
        self.terrain_materials, self.skyboxes = self.load_textures()

        self.setup_ui()
        self.apply_dark_theme()

        # Load Empires path from config
        empires_path = self.config.get("empires_path", "")
        self.edit_empires_path.setText(empires_path)
        self.update_empires_status()

        # Load default preset
        self.apply_preset("mixed") if "mixed" in self.presets else self.apply_preset(
            "hills"
        )
        self.update_validation_status()

    def load_presets(self):
        presets_path = PROJECT_ROOT / "config" / "presets.json"
        if presets_path.exists():
            with open(presets_path, "r") as f:
                data = json.load(f)
                return data.get("presets", {})
        return {}

    def load_textures(self):
        textures_path = PROJECT_ROOT / "config" / "textures.json"
        if textures_path.exists():
            with open(textures_path, "r") as f:
                data = json.load(f)
                materials = data.get(
                    "terrain_materials", ["common/nature/blend_grass_mountainwall_000"]
                )
                skyboxes = data.get("skyboxes", SAFE_EMPIRES_SKYBOXES)
                if not skyboxes:
                    skyboxes = SAFE_EMPIRES_SKYBOXES
                return materials, skyboxes
        return (
            ["common/nature/blend_grass_mountainwall_000"],
            [DEFAULT_SAFE_SKYBOX],
        )

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar.setFixedWidth(250)

        title = QLabel("Terrain Gen")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(title)

        preset_group = QGroupBox("Presets")
        preset_layout = QVBoxLayout(preset_group)
        self.btn_flat = QPushButton("Flat")
        self.btn_hills = QPushButton("Hills")
        self.btn_rugged = QPushButton("Rugged")
        self.btn_comp = QPushButton("Competitive")

        self.btn_flat.clicked.connect(lambda: self.apply_preset("flat"))
        self.btn_hills.clicked.connect(lambda: self.apply_preset("hills"))
        self.btn_rugged.clicked.connect(lambda: self.apply_preset("rugged"))
        self.btn_comp.clicked.connect(lambda: self.apply_preset("competitive"))

        preset_layout.addWidget(self.btn_flat)
        preset_layout.addWidget(self.btn_hills)
        preset_layout.addWidget(self.btn_rugged)
        preset_layout.addWidget(self.btn_comp)
        sidebar_layout.addWidget(preset_group)

        # Empires Path Configuration
        empires_group = QGroupBox("Empires Path")
        empires_layout = QVBoxLayout(empires_group)

        empires_desc = QLabel("Required for compiling maps")
        empires_desc.setStyleSheet("color: #888; font-size: 10px;")
        empires_layout.addWidget(empires_desc)

        empires_path_layout = QHBoxLayout()
        self.edit_empires_path = QLineEdit()
        self.edit_empires_path.setPlaceholderText("Select Empires folder...")
        empires_path_layout.addWidget(self.edit_empires_path)

        self.btn_browse_empires = QPushButton("Browse")
        self.btn_browse_empires.setFixedWidth(70)
        self.btn_browse_empires.clicked.connect(self.browse_empires_path)
        empires_path_layout.addWidget(self.btn_browse_empires)
        empires_layout.addLayout(empires_path_layout)

        self.lbl_empires_status = QLabel()
        self.lbl_empires_status.setStyleSheet("color: #888; font-size: 10px;")
        empires_layout.addWidget(self.lbl_empires_status)

        sidebar_layout.addWidget(empires_group)

        # Connect text changes to save and validate
        self.edit_empires_path.textChanged.connect(self.on_empires_path_changed)

        sidebar_layout.addStretch()

        self.btn_reset = QPushButton("Reset to Safe Preset")
        self.btn_reset.clicked.connect(self.reset_to_safe)
        sidebar_layout.addWidget(self.btn_reset)

        self.btn_generate = QPushButton("Generate Safe Map")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold;"
        )
        self.btn_generate.clicked.connect(self.generate_map)
        sidebar_layout.addWidget(self.btn_generate)

        self.btn_compile = QPushButton("Compile (VBSP)")
        self.btn_compile.setFixedHeight(40)
        self.btn_compile.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;"
        )
        self.btn_compile.clicked.connect(self.compile_map)
        sidebar_layout.addWidget(self.btn_compile)

        # --- Main Area ---

        main_area = QWidget()
        main_area_layout = QVBoxLayout(main_area)
        main_area_layout.setContentsMargins(0, 0, 0, 0)

        # Settings Layout
        settings_group = QGroupBox("Configuration")
        grid = QGridLayout(settings_group)
        grid.setSpacing(10)
        grid.setColumnMinimumWidth(0, 100)
        grid.setColumnStretch(1, 2)
        grid.setColumnMinimumWidth(2, 100)
        grid.setColumnStretch(3, 2)

        row = 0
        col = 0

        def next_cell():
            nonlocal row, col
            col += 2
            if col > 2:
                col = 0
                row += 1

        def add_setting(label_text, widget):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold;")
            grid.addWidget(lbl, row, col)
            grid.addWidget(widget, row, col + 1)
            next_cell()

        # Map Name
        self.txt_map_name = QLineEdit()
        self.txt_map_name.setText("gui_terrain")
        self.txt_map_name.setPlaceholderText("Enter map name...")
        add_setting("Map Name:", self.txt_map_name)

        # Data Source (Custom Image)
        source_layout = QHBoxLayout()
        self.chk_custom_image = QCheckBox("Enable")
        self.btn_browse = QPushButton("Browse...")
        self.lbl_image_path = QLabel("None")
        self.btn_browse.setEnabled(False)
        self.lbl_image_path.setStyleSheet("color: #888; font-size: 10px;")
        source_layout.addWidget(self.chk_custom_image)
        source_layout.addWidget(self.btn_browse)
        source_layout.addWidget(self.lbl_image_path)
        source_widget = QWidget()
        source_widget.setLayout(source_layout)
        add_setting("Custom Image:", source_widget)

        self.chk_custom_image.toggled.connect(self.toggle_custom_image)
        self.btn_browse.clicked.connect(self.browse_image)

        # Seed
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 999999999)
        self.btn_random_seed = QPushButton("🎲")
        self.btn_random_seed.setFixedWidth(40)
        self.btn_random_seed.clicked.connect(
            lambda: self.spin_seed.setValue(random.randint(0, 999999999))
        )
        seed_layout = QHBoxLayout()
        seed_layout.addWidget(self.spin_seed)
        seed_layout.addWidget(self.btn_random_seed)
        seed_widget = QWidget()
        seed_widget.setLayout(seed_layout)
        add_setting("Seed:", seed_widget)
        self.spin_seed.valueChanged.connect(self.sync_to_model)

        # Map Size X in tiles
        tilesx_container = QVBoxLayout()
        tilesx_desc = QLabel("Width in 512-unit tiles")
        tilesx_desc.setStyleSheet("color: #888; font-size: 10px;")
        tilesx_container.addWidget(tilesx_desc)
        tilesx_sub = QHBoxLayout()
        tilesx_sub.addWidget(QLabel("1"))
        self.spin_tiles_x = QSpinBox()
        self.spin_tiles_x.setRange(1, 64)
        tilesx_sub.addWidget(self.spin_tiles_x)
        tilesx_sub.addWidget(QLabel("64"))
        tilesx_container.addLayout(tilesx_sub)
        tilesx_widget = QWidget()
        tilesx_widget.setLayout(tilesx_container)
        add_setting("Tiles X:", tilesx_widget)
        self.spin_tiles_x.valueChanged.connect(self.sync_to_model)

        # Map Size Y in tiles
        tilesy_container = QVBoxLayout()
        tilesy_desc = QLabel("Height in 512-unit tiles")
        tilesy_desc.setStyleSheet("color: #888; font-size: 10px;")
        tilesy_container.addWidget(tilesy_desc)
        tilesy_sub = QHBoxLayout()
        tilesy_sub.addWidget(QLabel("1"))
        self.spin_tiles_y = QSpinBox()
        self.spin_tiles_y.setRange(1, 64)
        tilesy_sub.addWidget(self.spin_tiles_y)
        tilesy_sub.addWidget(QLabel("64"))
        tilesy_container.addLayout(tilesy_sub)
        tilesy_widget = QWidget()
        tilesy_widget.setLayout(tilesy_container)
        add_setting("Tiles Y:", tilesy_widget)
        self.spin_tiles_y.valueChanged.connect(self.sync_to_model)

        # Height Scale
        height_container = QVBoxLayout()
        height_desc = QLabel("Max height in world units")
        height_desc.setStyleSheet("color: #888; font-size: 10px;")
        height_container.addWidget(height_desc)
        height_sub = QHBoxLayout()
        height_sub.addWidget(QLabel("128"))
        self.spin_height = QSpinBox()
        self.spin_height.setRange(128, 4096)
        height_sub.addWidget(self.spin_height)
        height_sub.addWidget(QLabel("4096"))
        height_container.addLayout(height_sub)
        height_widget = QWidget()
        height_widget.setLayout(height_container)
        add_setting("Height Scale:", height_widget)
        self.spin_height.valueChanged.connect(self.sync_to_model)

        # Displacement Power
        power_container = QVBoxLayout()
        power_desc = QLabel("Vertices per tile")
        power_desc.setStyleSheet("color: #888; font-size: 10px;")
        power_container.addWidget(power_desc)
        self.combo_power = QComboBox()
        self.combo_power.addItems(
            ["2 (5×5) - Fast", "3 (9×9) - Balanced", "4 (17×17) - Detailed"]
        )
        power_container.addWidget(self.combo_power)
        power_widget = QWidget()
        power_widget.setLayout(power_container)
        add_setting("Detail Level:", power_widget)
        self.combo_power.currentIndexChanged.connect(self.sync_to_model)

        # Roughness Slider
        rough_container = QVBoxLayout()
        rough_desc = QLabel("Low=Smooth, High=Mountainous")
        rough_desc.setStyleSheet("color: #888; font-size: 10px;")
        rough_container.addWidget(rough_desc)
        rough_sub = QHBoxLayout()
        rough_sub.addWidget(QLabel("Smooth"))
        self.slider_rough = QSlider(Qt.Horizontal)
        self.slider_rough.setRange(0, 100)
        rough_sub.addWidget(self.slider_rough)
        rough_sub.addWidget(QLabel("Rugged"))
        rough_container.addLayout(rough_sub)
        rough_widget = QWidget()
        rough_widget.setLayout(rough_container)
        add_setting("Roughness:", rough_widget)
        self.slider_rough.valueChanged.connect(self.sync_to_model)

        # Erosion Strength Slider
        eros_container = QVBoxLayout()
        eros_desc = QLabel("Low=Sharp, High=Smooth")
        eros_desc.setStyleSheet("color: #888; font-size: 10px;")
        eros_container.addWidget(eros_desc)
        eros_sub = QHBoxLayout()
        eros_sub.addWidget(QLabel("Sharp"))
        self.slider_erosion = QSlider(Qt.Horizontal)
        self.slider_erosion.setRange(0, 100)
        eros_sub.addWidget(self.slider_erosion)
        eros_sub.addWidget(QLabel("Smooth"))
        eros_container.addLayout(eros_sub)
        eros_widget = QWidget()
        eros_widget.setLayout(eros_container)
        add_setting("Erosion:", eros_widget)
        self.slider_erosion.valueChanged.connect(self.sync_to_model)

        # Base Clear Radius Slider
        radius_container = QVBoxLayout()
        radius_desc = QLabel("Size of flat area (0=disabled)")
        radius_desc.setStyleSheet("color: #888; font-size: 10px;")
        radius_container.addWidget(radius_desc)
        radius_sub = QHBoxLayout()
        radius_sub.addWidget(QLabel("0"))
        self.slider_base_radius = QSlider(Qt.Horizontal)
        self.slider_base_radius.setRange(0, 4096)
        radius_sub.addWidget(self.slider_base_radius)
        radius_sub.addWidget(QLabel("4096"))
        radius_container.addLayout(radius_sub)
        radius_widget = QWidget()
        radius_widget.setLayout(radius_container)
        add_setting("Base Radius:", radius_widget)
        self.slider_base_radius.valueChanged.connect(self.sync_to_model)

        # Base Flatness Slider
        flat_container = QVBoxLayout()
        flat_desc = QLabel("0=natural, 100=flat")
        flat_desc.setStyleSheet("color: #888; font-size: 10px;")
        flat_container.addWidget(flat_desc)
        flat_sub = QHBoxLayout()
        flat_sub.addWidget(QLabel("Natural"))
        self.slider_base_flatness = QSlider(Qt.Horizontal)
        self.slider_base_flatness.setRange(0, 100)
        flat_sub.addWidget(self.slider_base_flatness)
        flat_sub.addWidget(QLabel("Flat"))
        flat_container.addLayout(flat_sub)
        flat_widget = QWidget()
        flat_widget.setLayout(flat_container)
        add_setting("Base Flatness:", flat_widget)
        self.slider_base_flatness.valueChanged.connect(self.sync_to_model)

        # Center Flatten Amount Slider
        cf_container = QVBoxLayout()
        cf_desc = QLabel("0=disabled, 100=flat")
        cf_desc.setStyleSheet("color: #888; font-size: 10px;")
        cf_container.addWidget(cf_desc)
        cf_sub = QHBoxLayout()
        cf_sub.addWidget(QLabel("Off"))
        self.slider_center_flatten = QSlider(Qt.Horizontal)
        self.slider_center_flatten.setRange(0, 100)
        cf_sub.addWidget(self.slider_center_flatten)
        cf_sub.addWidget(QLabel("Max"))
        cf_container.addLayout(cf_sub)
        cf_widget = QWidget()
        cf_widget.setLayout(cf_container)
        add_setting("Center Flatten:", cf_widget)
        self.slider_center_flatten.valueChanged.connect(self.sync_to_model)

        # Center Flatten Radius Slider
        cfr_container = QVBoxLayout()
        cfr_desc = QLabel("10-50% of map size")
        cfr_desc.setStyleSheet("color: #888; font-size: 10px;")
        cfr_container.addWidget(cfr_desc)
        cfr_sub = QHBoxLayout()
        cfr_sub.addWidget(QLabel("10%"))
        self.slider_center_radius = QSlider(Qt.Horizontal)
        self.slider_center_radius.setRange(10, 50)
        cfr_sub.addWidget(self.slider_center_radius)
        cfr_sub.addWidget(QLabel("50%"))
        cfr_container.addLayout(cfr_sub)
        cfr_widget = QWidget()
        cfr_widget.setLayout(cfr_container)
        add_setting("Center Radius:", cfr_widget)
        self.slider_center_radius.valueChanged.connect(self.sync_to_model)

        # Terrain Material
        mat_container = QVBoxLayout()
        mat_desc = QLabel("Ground surface blend")
        mat_desc.setStyleSheet("color: #888; font-size: 10px;")
        mat_container.addWidget(mat_desc)
        self.combo_material = QComboBox()
        self.combo_material.addItems(self.terrain_materials)
        self.combo_material.setCurrentText("common/nature/blend_grass_mountainwall_000")
        mat_container.addWidget(self.combo_material)
        mat_widget = QWidget()
        mat_widget.setLayout(mat_container)
        add_setting("Terrain Texture:", mat_widget)
        self.combo_material.currentIndexChanged.connect(self.sync_to_model)

        # Skybox
        sky_container = QVBoxLayout()
        sky_desc = QLabel("Sky background")
        sky_desc.setStyleSheet("color: #888; font-size: 10px;")
        sky_container.addWidget(sky_desc)
        self.combo_skybox = QComboBox()
        self.combo_skybox.addItems(self.skyboxes)
        self.combo_skybox.setCurrentText("empsky_overcast3yellow")
        sky_container.addWidget(self.combo_skybox)
        sky_widget = QWidget()
        sky_widget.setLayout(sky_container)
        add_setting("Skybox:", sky_widget)
        self.combo_skybox.currentIndexChanged.connect(self.sync_to_model)

        # Advance row for full width group
        if col != 0:
            row += 1
            col = 0

        # Spawn Settings
        lbl_spawn = QLabel("Spawn Settings:")
        lbl_spawn.setStyleSheet("font-weight: bold;")
        grid.addWidget(lbl_spawn, row, 0)

        spawn_container = QVBoxLayout()
        spawn_desc = QLabel("Control what entities are generated on the map")
        spawn_desc.setStyleSheet("color: #888; font-size: 10px;")
        spawn_container.addWidget(spawn_desc)

        spawn_grid = QGridLayout()

        self.chk_disable_commander = QCheckBox("Disable Commander")
        self.chk_disable_buildings = QCheckBox("Disable Base Buildings")
        self.chk_disable_resources = QCheckBox("Disable Resource Nodes")
        self.chk_minimal_map = QCheckBox("Minimal Map (Playable, No Props)")
        self.chk_terrain_only = QCheckBox("Terrain Only (No Spawns)")

        self.chk_disable_commander.toggled.connect(self.sync_to_model)
        self.chk_disable_buildings.toggled.connect(self.sync_to_model)
        self.chk_disable_resources.toggled.connect(self.sync_to_model)
        self.chk_minimal_map.toggled.connect(self.sync_to_model)
        self.chk_terrain_only.toggled.connect(self.sync_to_model)

        def update_spawn_checks():
            minimal = self.chk_minimal_map.isChecked()
            terrain_only = self.chk_terrain_only.isChecked()

            if terrain_only:
                self.chk_minimal_map.setChecked(False)
                minimal = False

            disable_individual = minimal or terrain_only

            self.chk_disable_commander.setEnabled(not disable_individual)
            self.chk_disable_buildings.setEnabled(not disable_individual)
            self.chk_disable_resources.setEnabled(not disable_individual)

            if disable_individual:
                self.chk_disable_commander.setChecked(False)
                self.chk_disable_buildings.setChecked(False)
                self.chk_disable_resources.setChecked(False)

        self.chk_minimal_map.toggled.connect(update_spawn_checks)
        self.chk_terrain_only.toggled.connect(update_spawn_checks)

        spawn_grid.addWidget(self.chk_disable_commander, 0, 0)
        spawn_grid.addWidget(self.chk_disable_buildings, 0, 1)
        spawn_grid.addWidget(self.chk_disable_resources, 1, 0)
        spawn_grid.addWidget(self.chk_minimal_map, 1, 1)
        spawn_grid.addWidget(self.chk_terrain_only, 2, 0)

        spawn_container.addLayout(spawn_grid)

        spawn_widget = QWidget()
        spawn_widget.setLayout(spawn_container)
        grid.addWidget(spawn_widget, row, 1, 1, 3)  # Span 3 columns
        row += 1

        # Use a scroll area for settings to ensure it fits in small windows
        from PySide6.QtWidgets import QScrollArea

        # Validation Feedback Panel
        self.val_group = QGroupBox("Validation Status")
        val_layout = QVBoxLayout(self.val_group)
        self.lbl_validation = QLabel("Checks passed.")
        self.lbl_validation.setWordWrap(True)
        val_layout.addWidget(self.lbl_validation)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(settings_group)
        scroll_layout.addWidget(self.val_group)
        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setFrameShape(QScrollArea.NoFrame)

        # Ensure scroll area doesn't force a horizontal scrollbar unnecessarily
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Split main area into settings and preview
        split_layout = QHBoxLayout()
        split_layout.addWidget(scroll, 1)

        # Preview Area
        preview_group = QGroupBox("Map Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_widget = MapPreviewWidget()
        preview_layout.addWidget(self.preview_widget)

        # Layout Validation Errors
        self.lbl_layout_validation = QLabel("")
        self.lbl_layout_validation.setStyleSheet("color: #F44336; font-weight: bold;")
        self.lbl_layout_validation.setWordWrap(True)
        preview_layout.addWidget(self.lbl_layout_validation)

        # Tools layout
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10)
        self.tool_group = QButtonGroup(self)

        self.rbtn_none = QRadioButton("Move/Drag")
        self.rbtn_none.setChecked(True)
        self.tool_group.addButton(self.rbtn_none, 0)
        tools_layout.addWidget(self.rbtn_none)

        self.rbtn_imp = QRadioButton("Set Imp Base (Blue)")
        self.rbtn_imp.setStyleSheet("color: #3498db; font-weight: bold;")
        self.tool_group.addButton(self.rbtn_imp, 1)
        tools_layout.addWidget(self.rbtn_imp)

        self.rbtn_nf = QRadioButton("Set NF Base (Red)")
        self.rbtn_nf.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.tool_group.addButton(self.rbtn_nf, 2)
        tools_layout.addWidget(self.rbtn_nf)

        self.rbtn_res = QRadioButton("Add Resource (Green)")
        self.rbtn_res.setStyleSheet("color: #2ecc71; font-weight: bold;")
        self.tool_group.addButton(self.rbtn_res, 3)
        tools_layout.addWidget(self.rbtn_res)

        self.btn_clear_res = QPushButton("Clear Resources")
        self.btn_clear_res.clicked.connect(self.clear_resources)
        tools_layout.addWidget(self.btn_clear_res)

        tools_layout.addStretch()
        preview_layout.addLayout(tools_layout)

        split_layout.addWidget(preview_group, 1)

        main_area_layout.addLayout(split_layout)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.run_preview)

        # Connect preview widget signals
        self.preview_widget.base_moved.connect(self.on_base_moved)
        self.preview_widget.resource_moved.connect(self.on_resource_moved)
        self.preview_widget.resource_added.connect(self.on_resource_added)
        self.tool_group.idClicked.connect(self.on_tool_changed)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(main_area)

    def validate_current_layout(self):
        spec = self.config_model.to_terrain_spec()
        layout_result = spec.validate_layout()

        if not layout_result.valid:
            self.lbl_layout_validation.setText("\n".join(layout_result.errors))
            self.lbl_layout_validation.show()
            self.btn_generate.setEnabled(False)
        else:
            self.lbl_layout_validation.setText("")
            self.lbl_layout_validation.hide()
            self.btn_generate.setEnabled(True)

        return layout_result.invalid_entities

    def clear_resources(self):
        self.config_model.custom_resources = []
        invalid_entities = self.validate_current_layout()
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            [],
            invalid_entities=invalid_entities
        )
        self.preview_timer.start(500)

    def on_tool_changed(self, id):
        tools = {0: "none", 1: "imp_base", 2: "nf_base", 3: "add_res"}
        self.preview_widget.current_tool = tools.get(id, "none")

    def on_base_moved(self, faction, x, y):
        if faction == "imp":
            self.config_model.custom_imp_base_x = x
            self.config_model.custom_imp_base_y = y
        else:
            self.config_model.custom_nf_base_x = x
            self.config_model.custom_nf_base_y = y
        invalid_entities = self.validate_current_layout()
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            self.config_model.custom_resources,
            invalid_entities=invalid_entities
        )
        self.preview_timer.start(500)

    def on_resource_moved(self, index, x, y):
        if self.config_model.custom_resources and 0 <= index < len(
            self.config_model.custom_resources
        ):
            self.config_model.custom_resources[index] = (x, y)
        invalid_entities = self.validate_current_layout()
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            self.config_model.custom_resources,
            invalid_entities=invalid_entities
        )
        # Resource positions do not affect the terrain heightmap itself,
        # so we don't necessarily need to re-run the pipeline on move,
        # but we can do it if desired.
        self.preview_timer.start(500)

    def on_resource_added(self, x, y):
        if self.config_model.custom_resources is None:
            self.config_model.custom_resources = []
        self.config_model.custom_resources.append((x, y))
        invalid_entities = self.validate_current_layout()
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            self.config_model.custom_resources,
            invalid_entities=invalid_entities
        )
        self.preview_timer.start(500)

    def run_preview(self):
        if not hasattr(self, "preview_worker") or not self.preview_worker.isRunning():
            self.preview_worker = PreviewWorker(self.config_model)
            self.preview_worker.finished.connect(self.on_preview_finished)
            self.preview_worker.start()

    def on_preview_finished(self, grid, spec):
        if grid and spec:
            import numpy as np

            heights = np.array(grid.heights)
            min_h = heights.min()
            max_h = heights.max()
            if max_h > min_h:
                normalized = (heights - min_h) / (max_h - min_h)
            else:
                normalized = np.zeros_like(heights)

            img_data = (normalized * 255).astype(np.uint8)
            h, w = img_data.shape

            # Create QImage from numpy array
            bytes_per_line = w
            # Must keep a reference to img_data so it isn't garbage collected
            self._current_preview_data = img_data
            qimg = QImage(
                self._current_preview_data.data,
                w,
                h,
                bytes_per_line,
                QImage.Format_Grayscale8,
            )

            self.preview_widget.set_map_image(
                qimg, spec.origin_x, spec.origin_y, spec.size_x, spec.size_y
            )

            # Setup initial bases if not set
            if self.config_model.custom_imp_base_x is None:
                imp_x = spec.origin_x + spec.size_x * 0.25
                imp_y = spec.origin_y + spec.size_y * 0.25
            else:
                imp_x = self.config_model.custom_imp_base_x
                imp_y = self.config_model.custom_imp_base_y

            if self.config_model.custom_nf_base_x is None:
                nf_x = spec.origin_x + spec.size_x * 0.75
                nf_y = spec.origin_y + spec.size_y * 0.75
            else:
                nf_x = self.config_model.custom_nf_base_x
                nf_y = self.config_model.custom_nf_base_y

            res = (
                self.config_model.custom_resources
                if self.config_model.custom_resources
                else []
            )
            invalid_entities = self.validate_current_layout()
            self.preview_widget.set_entities((imp_x, imp_y), (nf_x, nf_y), res, invalid_entities=invalid_entities)

    def apply_dark_theme(self):
        style = """
        QMainWindow, QWidget {
            background-color: #1a1a1c;
            color: #e0e0e0;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
            font-size: 13px;
        }
        QScrollArea {
            border: none;
            background-color: transparent;
        }
        QGroupBox {
            border: 1px solid #333338;
            border-radius: 8px;
            margin-top: 16px;
            font-weight: bold;
            color: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 4px;
            color: #a0a0a5;
        }
        QPushButton {
            background-color: #2c2c30;
            border: 1px solid #3e3e42;
            border-radius: 6px;
            padding: 8px 12px;
            color: #ffffff;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #38383e;
            border: 1px solid #505055;
        }
        QPushButton:pressed {
            background-color: #1e1e20;
            border: 1px solid #2c2c30;
        }
        QPushButton:disabled {
            background-color: #222224;
            color: #66666a;
            border: 1px solid #2a2a2c;
        }
        QSpinBox, QComboBox, QLineEdit {
            background-color: #252529;
            border: 1px solid #38383e;
            border-radius: 6px;
            padding: 6px 10px;
            color: #ffffff;
            selection-background-color: #0d6efd;
        }
        QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
            border: 1px solid #0d6efd;
            background-color: #2a2a2f;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #a0a0a5;
            margin-right: 8px;
        }
        QSlider::groove:horizontal {
            border: none;
            height: 6px;
            background: #38383e;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #0d6efd;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #ffffff;
            border: 2px solid #0d6efd;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 9px;
        }
        QSlider::handle:horizontal:hover {
            background: #e0e0e0;
            border: 2px solid #0b5ed7;
        }
        QCheckBox {
            spacing: 8px;
        }
        QScrollBar:vertical {
            border: none;
            background: #1a1a1c;
            width: 12px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #38383e;
            min-height: 20px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #1a1a1c;
            height: 12px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:horizontal {
            background: #38383e;
            min-width: 20px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
                """
        self.setStyleSheet(style)

    def apply_preset(self, preset_name):
        if preset_name not in self.presets:
            preset_name = (
                "hills"
                if "hills" in self.presets
                else list(self.presets.keys())[0]
                if self.presets
                else None
            )
            if not preset_name:
                return

        preset = self.presets[preset_name]

        # Block signals briefly to prevent firing multiple sync events
        self.spin_seed.blockSignals(True)
        self.spin_tiles_x.blockSignals(True)
        self.spin_tiles_y.blockSignals(True)
        self.spin_height.blockSignals(True)
        self.slider_rough.blockSignals(True)
        self.slider_erosion.blockSignals(True)
        self.slider_base_radius.blockSignals(True)
        self.slider_base_flatness.blockSignals(True)
        self.slider_center_flatten.blockSignals(True)
        self.slider_center_radius.blockSignals(True)
        self.combo_power.blockSignals(True)
        self.combo_material.blockSignals(True)
        self.combo_skybox.blockSignals(True)
        self.chk_disable_commander.blockSignals(True)
        self.chk_disable_buildings.blockSignals(True)
        self.chk_disable_resources.blockSignals(True)
        self.chk_minimal_map.blockSignals(True)
        self.chk_terrain_only.blockSignals(True)

        self.spin_seed.setValue(preset.get("seed", random.randint(0, 999999999)))
        if "tiles_x" in preset:
            self.spin_tiles_x.setValue(preset["tiles_x"])
        if "tiles_y" in preset:
            self.spin_tiles_y.setValue(preset["tiles_y"])
        self.spin_height.setValue(preset.get("height_scale", 1024))
        self.slider_rough.setValue(int(preset.get("roughness", 0.5) * 100))
        self.slider_erosion.setValue(int(preset.get("erosion_strength", 0.5) * 100))
        self.slider_base_radius.setValue(preset.get("base_clear_radius", 0))
        self.slider_base_flatness.setValue(int(preset.get("base_flatness", 0.0) * 100))
        self.slider_center_flatten.setValue(
            int(preset.get("center_flatten", 0.0) * 100)
        )
        self.slider_center_radius.setValue(
            int(preset.get("center_flatten_radius", 0.5) * 100)
        )

        p = preset.get("displacement_power", 3)
        if p == 2:
            self.combo_power.setCurrentIndex(0)
        elif p == 3:
            self.combo_power.setCurrentIndex(1)

        self.spin_seed.blockSignals(False)
        self.spin_tiles_x.blockSignals(False)
        self.spin_tiles_y.blockSignals(False)
        self.spin_height.blockSignals(False)
        self.slider_rough.blockSignals(False)
        self.slider_erosion.blockSignals(False)
        self.slider_base_radius.blockSignals(False)
        self.slider_base_flatness.blockSignals(False)
        self.slider_center_flatten.blockSignals(False)
        self.slider_center_radius.blockSignals(False)
        self.combo_power.blockSignals(False)
        self.combo_material.blockSignals(False)
        self.combo_skybox.blockSignals(False)
        self.chk_disable_commander.blockSignals(False)
        self.chk_disable_buildings.blockSignals(False)
        self.chk_disable_resources.blockSignals(False)
        self.chk_minimal_map.blockSignals(False)
        self.chk_terrain_only.blockSignals(False)

        # Apply preset texture/skybox if specified
        if "terrain_material" in preset:
            self.combo_material.setCurrentText(preset["terrain_material"])
        if "skybox" in preset:
            self.combo_skybox.setCurrentText(preset["skybox"])

        self.sync_to_model()

    def reset_to_safe(self):
        self.config_model.auto_clamp()
        self.sync_to_ui()

    def toggle_custom_image(self, checked):
        self.btn_browse.setEnabled(checked)
        self.slider_rough.setEnabled(not checked)
        self.spin_seed.setEnabled(not checked)
        self.btn_random_seed.setEnabled(not checked)
        if not checked:
            self.lbl_image_path.setText("None")
            self.config_model.custom_image_path = None
        self.sync_to_model()

    def browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Heightmap", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.lbl_image_path.setText(Path(file_path).name)
            self.config_model.custom_image_path = file_path
            self.sync_to_model()

    def browse_empires_path(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Empires Installation Folder"
        )
        if folder:
            # Validate the selected path
            is_valid, msg = validate_empires_path(folder)
            if is_valid:
                self.edit_empires_path.setText(folder)
                self.config.set("empires_path", folder)
                self.update_empires_status()
            else:
                QMessageBox.warning(
                    self,
                    "Invalid Folder",
                    f"The selected folder does not appear to be a valid Empires installation:\n{msg}",
                )

    def update_empires_status(self):
        """Update the status label for Empires path."""
        path = self.edit_empires_path.text()
        if not path:
            self.lbl_empires_status.setText("Not configured")
            self.lbl_empires_status.setStyleSheet("color: #888; font-size: 10px;")
        else:
            is_valid, msg = validate_empires_path(path)
            if is_valid:
                self.lbl_empires_status.setText("Valid")
                self.lbl_empires_status.setStyleSheet(
                    "color: #4CAF50; font-size: 10px;"
                )
            else:
                self.lbl_empires_status.setText(f"Invalid: {msg}")
                self.lbl_empires_status.setStyleSheet(
                    "color: #f44336; font-size: 10px;"
                )

    def on_empires_path_changed(self, text):
        """Handle changes to the Empires path field."""
        self.config.set("empires_path", text)
        self.update_empires_status()

    def sync_to_ui(self):
        """Updates UI components to match the config model."""
        self.spin_seed.blockSignals(True)
        self.spin_tiles_x.blockSignals(True)
        self.spin_tiles_y.blockSignals(True)
        self.spin_height.blockSignals(True)
        self.slider_rough.blockSignals(True)
        self.slider_erosion.blockSignals(True)
        self.slider_base_radius.blockSignals(True)
        self.slider_base_flatness.blockSignals(True)
        self.slider_center_flatten.blockSignals(True)
        self.slider_center_radius.blockSignals(True)
        self.combo_power.blockSignals(True)
        self.combo_material.blockSignals(True)
        self.combo_skybox.blockSignals(True)
        self.chk_disable_commander.blockSignals(True)
        self.chk_disable_buildings.blockSignals(True)
        self.chk_disable_resources.blockSignals(True)
        self.chk_minimal_map.blockSignals(True)
        self.chk_terrain_only.blockSignals(True)

        self.spin_seed.setValue(self.config_model.seed)
        self.spin_tiles_x.setValue(self.config_model.tiles_x)
        self.spin_tiles_y.setValue(self.config_model.tiles_y)
        self.spin_height.setValue(self.config_model.height_scale)
        self.slider_rough.setValue(int(self.config_model.roughness * 100))
        self.slider_erosion.setValue(int(self.config_model.erosion_strength * 100))
        self.slider_base_radius.setValue(self.config_model.base_clear_radius)
        self.slider_base_flatness.setValue(int(self.config_model.base_flatness * 100))
        self.slider_center_flatten.setValue(int(self.config_model.center_flatten * 100))
        self.slider_center_radius.setValue(
            int(self.config_model.center_flatten_radius * 100)
        )

        p = self.config_model.displacement_power
        if p == 2:
            self.combo_power.setCurrentIndex(0)
        elif p == 3:
            self.combo_power.setCurrentIndex(1)

        self.combo_material.setCurrentText(self.config_model.terrain_material)
        self.combo_skybox.setCurrentText(self.config_model.skybox)

        self.chk_disable_commander.setChecked(self.config_model.disable_commander)
        self.chk_disable_buildings.setChecked(self.config_model.disable_buildings)
        self.chk_disable_resources.setChecked(self.config_model.disable_resource_nodes)
        self.chk_minimal_map.setChecked(self.config_model.minimal_map)
        self.chk_terrain_only.setChecked(self.config_model.terrain_only)

        self.spin_seed.blockSignals(False)
        self.spin_tiles_x.blockSignals(False)
        self.spin_tiles_y.blockSignals(False)
        self.spin_height.blockSignals(False)
        self.slider_rough.blockSignals(False)
        self.slider_erosion.blockSignals(False)
        self.slider_base_radius.blockSignals(False)
        self.slider_base_flatness.blockSignals(False)
        self.slider_center_flatten.blockSignals(False)
        self.slider_center_radius.blockSignals(False)
        self.combo_power.blockSignals(False)
        self.combo_material.blockSignals(False)
        self.combo_skybox.blockSignals(False)
        self.chk_disable_commander.blockSignals(False)
        self.chk_disable_buildings.blockSignals(False)
        self.chk_disable_resources.blockSignals(False)
        self.chk_minimal_map.blockSignals(False)
        self.chk_terrain_only.blockSignals(False)

        if self.config_model.custom_image_path:
            self.chk_custom_image.setChecked(True)
            self.lbl_image_path.setText(Path(self.config_model.custom_image_path).name)
        else:
            self.chk_custom_image.setChecked(False)
            self.lbl_image_path.setText("None")

        self.update_validation_status()

    def sync_to_model(self):
        """Updates config model from UI components and validates."""
        self.config_model.seed = self.spin_seed.value()
        self.config_model.tiles_x = self.spin_tiles_x.value()
        self.config_model.tiles_y = self.spin_tiles_y.value()
        self.config_model.height_scale = self.spin_height.value()
        self.config_model.roughness = self.slider_rough.value() / 100.0
        self.config_model.erosion_strength = self.slider_erosion.value() / 100.0
        self.config_model.base_clear_radius = self.slider_base_radius.value()
        self.config_model.base_flatness = self.slider_base_flatness.value() / 100.0
        self.config_model.center_flatten = self.slider_center_flatten.value() / 100.0
        self.config_model.center_flatten_radius = (
            self.slider_center_radius.value() / 100.0
        )

        idx = self.combo_power.currentIndex()
        if idx == 0:
            self.config_model.displacement_power = 2
        elif idx == 1:
            self.config_model.displacement_power = 3

        self.config_model.terrain_material = self.combo_material.currentText()
        self.config_model.skybox = self.combo_skybox.currentText()

        self.config_model.disable_commander = self.chk_disable_commander.isChecked()
        self.config_model.disable_buildings = self.chk_disable_buildings.isChecked()
        self.config_model.disable_resource_nodes = (
            self.chk_disable_resources.isChecked()
        )
        self.config_model.minimal_map = self.chk_minimal_map.isChecked()
        self.config_model.terrain_only = self.chk_terrain_only.isChecked()

        self.update_validation_status()
        if hasattr(self, "preview_timer"):
            self.preview_timer.start(500)

    def update_validation_status(self):
        is_valid, msg = self.config_model.validate()
        self.lbl_validation.setText(msg)

        if is_valid:
            self.val_group.setStyleSheet("QGroupBox { border: 1px solid #4CAF50; }")
            self.lbl_validation.setStyleSheet("color: #4CAF50;")
            self.btn_generate.setEnabled(True)
        else:
            self.val_group.setStyleSheet("QGroupBox { border: 1px solid #F44336; }")
            self.lbl_validation.setStyleSheet("color: #F44336;")
            self.btn_generate.setEnabled(False)

    def generate_map(self):
        is_valid, msg = self.config_model.validate()
        if not is_valid:
            return

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating...")

        # Run generation in background
        map_name = self.txt_map_name.text().strip() or "gui_terrain"
        self.worker = GenerationWorker(self.config_model, map_name)
        self.worker.finished.connect(self.on_generation_finished)
        self.worker.start()

    def on_generation_finished(self, success, msg):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Generate Safe Map")

        if success:
            map_name = self.txt_map_name.text().strip() or "gui_terrain"
            self._last_vmf_path = str(OUTPUT_DIR / f"{map_name}.vmf")
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Generation Failed", msg)

    def compile_map(self):
        vmf_path = getattr(self, "_last_vmf_path", None)
        if not vmf_path or not Path(vmf_path).exists():
            QMessageBox.warning(
                self, "No VMF", "Generate a map first before compiling."
            )
            return

        self.btn_compile.setEnabled(False)
        self.btn_compile.setText("Compiling...")

        empires_path = self.config.get("empires_path", "")

        self.compile_worker = CompileWorker(vmf_path, empires_path)
        self.compile_worker.finished.connect(self.on_compile_finished)
        self.compile_worker.start()

    def on_compile_finished(self, success, msg):
        self.btn_compile.setEnabled(True)
        self.btn_compile.setText("Compile (VBSP)")

        if success:
            QMessageBox.information(self, "Compile Success", msg)
        else:
            QMessageBox.critical(self, "Compile Failed", msg)


class CompileWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, vmf_path, empires_path=""):
        super().__init__()
        self.vmf_path = vmf_path
        self.empires_path = empires_path

    def run(self):
        try:
            if getattr(sys, "frozen", False):
                import io
                import contextlib
                from tools.compile_vmf import compile_vmf

                f = io.StringIO()
                with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                    success = compile_vmf(
                        vmf_path=str(self.vmf_path),
                        sdk_path="",
                        empires_path=self.empires_path,
                        nodetail=True,
                    )

                if not success:
                    raise RuntimeError(f.getvalue().strip() or "Compile failed")
            else:
                import subprocess

                compile_script = PROJECT_ROOT / "tools" / "compile_vmf.py"
                cmd = [
                    sys.executable,
                    str(compile_script),
                    str(self.vmf_path),
                    "--nodetail",
                ]
                if self.empires_path:
                    cmd.extend(["--empires-path", self.empires_path])

                result = subprocess.run(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    err = (
                        result.stderr.strip()
                        if result.stderr
                        else result.stdout.strip()
                    )
                    raise RuntimeError(err or "Compile failed")

            self.finished.emit(
                True,
                (
                    "BSP compiled and deployed to Empires.\n"
                    "Overview TXT + minimap VMT were also deployed for stability."
                ),
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TerrainGeneratorGUI()
    window.show()
    sys.exit(app.exec())
