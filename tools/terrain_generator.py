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
from contextlib import contextmanager

if not getattr(sys, "frozen", False):
    os.chdir(PROJECT_ROOT)

from PySide6.QtWidgets import (
    QApplication,
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
    QMessageBox,
    QFileDialog,
    QCheckBox,
    QLineEdit,
    QSplitter,
    QScrollArea,
    QTabWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QImage, QColor, QPainter, QPixmap, QShortcut, QKeySequence
from tools.preview_widget import MapPreviewWidget



from src.config_model import GUIConfigModel
from src.terrain_pipeline import run_pipeline
from src.export_utils import export_vmf
from src.vmf_gen import (
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


class PreviewWorker(QThread):
    finished = Signal(object, object)  # grid, spec

    def __init__(self, config_model, custom_nodes=None, custom_connections=None, custom_resources=None):
        super().__init__()
        self.config_model = config_model
        self.custom_nodes = custom_nodes
        self.custom_connections = custom_connections
        self.custom_resources = custom_resources

    def run(self):
        try:
            # We must not modify the original model's spec, but we can make a custom spec
            # Pass validate=False so we still get a preview even if nodes are being dragged
            spec = self.config_model.make_spec(validate=False)
            spec.displacement_power = 3  # Power 3 is still fast but shows much more detail
            # Enable scaled-down erosion for preview (max 20000 iterations)
            # Use 50% scaling because the preview grid is faster than the full VMF one
            spec.erosion_iterations = min(int(spec.erosion_iterations * 0.5), 20000)
            spec.disable_commander = True
            spec.disable_buildings = True
            spec.disable_resource_nodes = True
            
            if self.custom_nodes and self.custom_connections:
                spec.custom_layout_nodes = self.custom_nodes
                spec.custom_layout_connections = self.custom_connections
            
            if self.custom_resources is not None:
                spec.custom_resources = self.custom_resources

            # Skip layout validation during preview to prevent crashes while dragging
            result = run_pipeline(spec, skip_layout_validation=True)
            self.finished.emit(result["grid"], result["spec"])
        except Exception:
            import traceback

            if getattr(sys, "frozen", False):
                log_path = Path(sys.executable).parent / "preview_error.log"
                with open(log_path, "w") as f:
                    traceback.print_exc(file=f)
            else:
                traceback.print_exc()
            self.finished.emit(None, None)


class GenerationWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, config_model, custom_nodes=None, custom_connections=None, custom_resources=None, output_filename="gui_terrain"):
        super().__init__()
        self.config_model = config_model
        self.custom_nodes = custom_nodes
        self.custom_connections = custom_connections
        self.custom_resources = custom_resources
        self.output_filename = output_filename

    def run(self):
        try:
            spec = self.config_model.make_spec()
            if self.custom_nodes and self.custom_connections:
                spec.custom_layout_nodes = self.custom_nodes
                spec.custom_layout_connections = self.custom_connections
                
            if self.custom_resources is not None:
                spec.custom_resources = self.custom_resources

            # Run pipeline
            result = run_pipeline(spec, map_name=self.output_filename, output_dir=str(OUTPUT_DIR))
            if result["errors"]:
                raise Exception(f"Pipeline errors: {result['errors']}")

            grid = result["grid"]

            message = export_vmf(
                grid,
                self.config_model,
                OUTPUT_DIR,
                self.output_filename,
            )

            self.finished.emit(True, message)
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))


class TerrainGeneratorGUI(QMainWindow):
    @contextmanager
    def _block_signals(self, *widgets):
        for w in widgets:
            w.blockSignals(True)
        try:
            yield
        finally:
            for w in widgets:
                w.blockSignals(False)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Terrain Generator — Source Engine VMF Builder")
        self.setWindowIcon(QIcon(str(PROJECT_ROOT / "icons" / "app_icon.svg")))
        self.resize(1200, 780)
        self.setMinimumSize(820, 560)

        self.config_model = GUIConfigModel()
        self.config = Config()
        self.terrain_materials, self.skyboxes = self.load_textures()

        self.setup_ui()
        self.apply_dark_theme()

        # Load Empires path from config
        empires_path = self.config.get("empires_path", "")
        self.edit_empires_path.setText(empires_path)
        self.update_empires_status()

        # Initial sync and validation
        self.sync_to_ui()
        self.sync_to_model()

        # F12 screenshot
        sc = QShortcut(QKeySequence("F12"), self)
        sc.activated.connect(self.take_screenshot)

    def take_screenshot(self):
        import datetime
        import subprocess
        import shutil

        out_dir = PROJECT_ROOT / "docs" / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(out_dir / f"gui_{ts}.png")
        canonical = str(out_dir / "gui_preview.png")

        # self.grab() captures this window — works on Wayland
        pixmap = self.grab()
        if not pixmap.isNull():
            ok = pixmap.save(path, "PNG")
            if ok:
                shutil.copy(path, canonical)
                QMessageBox.information(self, "Screenshot saved", f"Saved to:\n{path}")
                return

        # Fallback: spectacle (KDE)
        try:
            spectacle_path = shutil.which("spectacle")
            if not spectacle_path:
                raise RuntimeError("Could not find 'spectacle' executable")
            subprocess.run(
                [spectacle_path, "-b", "-a", "-n", "-o", path],
                timeout=8,
                capture_output=True,
            )
            if Path(path).exists() and Path(path).stat().st_size > 0:
                shutil.copy(path, canonical)
                QMessageBox.information(self, "Screenshot saved", f"Saved to:\n{path}")
            else:
                QMessageBox.warning(
                    self, "Screenshot failed", "Could not capture screen."
                )
        except Exception as e:
            QMessageBox.warning(self, "Screenshot failed", str(e))


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
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Root splitter: sidebar | main area
        self._root_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self._root_splitter)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 12)
        sidebar_layout.setSpacing(8)
        sidebar.setMinimumWidth(190)
        sidebar.setMaximumWidth(300)

        # Clean title
        title = QLabel("Terrain Generator")
        title.setAlignment(Qt.AlignLeft)
        title.setObjectName("BrandTitle")
        sidebar_layout.addWidget(title)

        # Divider
        div1 = QWidget()
        div1.setFixedHeight(1)
        div1.setObjectName("Divider")
        sidebar_layout.addWidget(div1)


        # Divider
        div2 = QWidget()
        div2.setFixedHeight(1)
        div2.setObjectName("Divider")
        sidebar_layout.addWidget(div2)

        # Empires path — compact
        path_label = QLabel("COMPILE PATH")
        path_label.setObjectName("SectionLabel")
        sidebar_layout.addWidget(path_label)

        self.chk_auto_copy = QCheckBox("Auto-copy to Empires folder")
        self.chk_auto_copy.setObjectName("FieldLabel")
        self.chk_auto_copy.setChecked(self.config.get("auto_copy_to_empires", True))
        self.chk_auto_copy.stateChanged.connect(self.on_auto_copy_changed)
        sidebar_layout.addWidget(self.chk_auto_copy)

        self.edit_empires_path = QLineEdit()
        self.edit_empires_path.setPlaceholderText("Empires install folder...")
        sidebar_layout.addWidget(self.edit_empires_path)

        empires_bottom = QHBoxLayout()
        empires_bottom.setSpacing(6)
        self.lbl_empires_status = QLabel()
        self.lbl_empires_status.setObjectName("HintLabel")
        empires_bottom.addWidget(self.lbl_empires_status, 1)
        self.btn_browse_empires = QPushButton("Browse")
        self.btn_browse_empires.setObjectName("SmallButton")
        self.btn_browse_empires.clicked.connect(self.browse_empires_path)
        empires_bottom.addWidget(self.btn_browse_empires)
        sidebar_layout.addLayout(empires_bottom)

        self.edit_empires_path.textChanged.connect(self.on_empires_path_changed)

        # Custom output folder
        self.custom_output_container = QWidget()
        custom_output_layout = QVBoxLayout(self.custom_output_container)
        custom_output_layout.setContentsMargins(0, 0, 0, 0)
        custom_output_layout.setSpacing(6)

        self.lbl_custom_output = QLabel("Custom Output Folder:")
        self.lbl_custom_output.setObjectName("FieldLabel")
        custom_output_layout.addWidget(self.lbl_custom_output)

        self.edit_custom_output = QLineEdit()
        self.edit_custom_output.setPlaceholderText("Select output folder...")
        self.edit_custom_output.setText(self.config.get("custom_output_folder", ""))
        self.edit_custom_output.textChanged.connect(self.on_custom_output_changed)
        custom_output_layout.addWidget(self.edit_custom_output)

        custom_output_bottom = QHBoxLayout()
        custom_output_bottom.setSpacing(6)
        self.lbl_custom_status = QLabel()
        self.lbl_custom_status.setObjectName("HintLabel")
        custom_output_bottom.addWidget(self.lbl_custom_status, 1)
        self.btn_browse_custom = QPushButton("Browse")
        self.btn_browse_custom.setObjectName("SmallButton")
        self.btn_browse_custom.clicked.connect(self.browse_custom_output)
        custom_output_bottom.addWidget(self.btn_browse_custom)
        custom_output_layout.addLayout(custom_output_bottom)

        sidebar_layout.addWidget(self.custom_output_container)

        self.on_auto_copy_changed() # Trigger initial state setup

        sidebar_layout.addStretch()

        self.btn_generate = QPushButton("Generate VMF")
        self.btn_generate.setObjectName("GenerateButton")
        self.btn_generate.setMinimumHeight(40)
        self.btn_generate.clicked.connect(self.generate_map)
        sidebar_layout.addWidget(self.btn_generate)

        self.btn_compile = QPushButton("Compile (VBSP)")
        self.btn_compile.setObjectName("CompileButton")
        self.btn_compile.setMinimumHeight(40)
        self.btn_compile.clicked.connect(self.compile_map)
        sidebar_layout.addWidget(self.btn_compile)

        # --- Main Area ---

        main_area = QWidget()
        main_area_layout = QVBoxLayout(main_area)
        main_area_layout.setContentsMargins(0, 0, 0, 0)

        # ── Helper: create a slider row with live value label ──
        def make_slider_row(slider, value_label, *args):
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(slider, 1)
            value_label.setFixedWidth(48)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setObjectName("SliderValue")
            row_layout.addWidget(value_label)
            w = QWidget()
            w.setLayout(row_layout)
            return w

        # ── Helper: section divider inside scroll area ──
        def make_section_label(text):
            lbl = QLabel(text)
            lbl.setObjectName("ConfigSection")
            return lbl

        # ── Helper: thin horizontal line ──
        def make_divider():
            d = QWidget()
            d.setFixedHeight(1)
            d.setObjectName("Divider")
            return d

        # ── Config scroll content ──
        config_layout = QVBoxLayout()
        config_layout.setSpacing(6)
        config_layout.setContentsMargins(14, 10, 14, 10)

        # ─── GENERAL ───
        config_layout.addWidget(make_section_label("GENERAL"))

        # Map Name
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel("Map Name")
        name_lbl.setObjectName("FieldLabel")
        name_row.addWidget(name_lbl)
        self.txt_map_name = QLineEdit()
        self.txt_map_name.setText("gui_terrain")
        self.txt_map_name.setPlaceholderText("Enter map name...")
        name_row.addWidget(self.txt_map_name, 1)
        config_layout.addLayout(name_row)

        # Seed
        seed_row = QHBoxLayout()
        seed_row.setSpacing(8)
        seed_lbl = QLabel("Seed")
        seed_lbl.setObjectName("FieldLabel")
        seed_row.addWidget(seed_lbl)
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 999999999)
        seed_row.addWidget(self.spin_seed, 1)
        self.btn_random_seed = QPushButton("🎲")
        self.btn_random_seed.setFixedSize(34, 30)
        self.btn_random_seed.setToolTip("Randomize seed")
        self.btn_random_seed.clicked.connect(
            lambda: self.spin_seed.setValue(random.randint(0, 999999999))
        )
        seed_row.addWidget(self.btn_random_seed)
        config_layout.addLayout(seed_row)
        self.spin_seed.valueChanged.connect(self.sync_to_model)

        # Custom Image
        img_row = QHBoxLayout()
        img_row.setSpacing(8)
        img_lbl = QLabel("Heightmap")
        img_lbl.setObjectName("FieldLabel")
        img_row.addWidget(img_lbl)
        self.chk_custom_image = QCheckBox("Custom")
        img_row.addWidget(self.chk_custom_image)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.setEnabled(False)
        img_row.addWidget(self.btn_browse)
        self.lbl_image_path = QLabel("None")
        self.lbl_image_path.setObjectName("HintLabel")
        img_row.addWidget(self.lbl_image_path, 1)
        config_layout.addLayout(img_row)
        self.chk_custom_image.toggled.connect(self.toggle_custom_image)
        self.btn_browse.clicked.connect(self.browse_image)

        config_layout.addWidget(make_divider())

        # ─── MAP DIMENSIONS ───
        config_layout.addWidget(make_section_label("MAP DIMENSIONS"))

        dim_grid = QGridLayout()
        dim_grid.setSpacing(6)
        dim_grid.setColumnStretch(1, 1)
        dim_grid.setColumnStretch(3, 1)

        lbl_tx = QLabel("Tiles X")
        lbl_tx.setObjectName("FieldLabel")
        lbl_tx.setToolTip(
            "Number of displacement tiles horizontally (each is 512 world units)"
        )
        dim_grid.addWidget(lbl_tx, 0, 0)
        self.spin_tiles_x = QSpinBox()
        self.spin_tiles_x.setRange(1, 64)
        dim_grid.addWidget(self.spin_tiles_x, 0, 1)

        lbl_ty = QLabel("Tiles Y")
        lbl_ty.setObjectName("FieldLabel")
        lbl_ty.setToolTip(
            "Number of displacement tiles vertically (each is 512 world units)"
        )
        dim_grid.addWidget(lbl_ty, 0, 2)
        self.spin_tiles_y = QSpinBox()
        self.spin_tiles_y.setRange(1, 64)
        dim_grid.addWidget(self.spin_tiles_y, 0, 3)

        lbl_hs = QLabel("Height")
        lbl_hs.setObjectName("FieldLabel")
        lbl_hs.setToolTip("Maximum terrain height in world units")
        dim_grid.addWidget(lbl_hs, 1, 0)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(128, 4096)
        dim_grid.addWidget(self.spin_height, 1, 1)

        lbl_pw = QLabel("Detail")
        lbl_pw.setObjectName("FieldLabel")
        lbl_pw.setToolTip("Displacement power — vertices per tile edge")
        dim_grid.addWidget(lbl_pw, 1, 2)
        self.combo_power = QComboBox()
        self.combo_power.addItems(["2 (5×5)", "3 (9×9)", "4 (17×17)"])
        dim_grid.addWidget(self.combo_power, 1, 3)

        config_layout.addLayout(dim_grid)

        # Live map-size info label
        self.lbl_map_info = QLabel()
        self.lbl_map_info.setObjectName("HintLabel")
        config_layout.addWidget(self.lbl_map_info)

        self.spin_tiles_x.valueChanged.connect(self.sync_to_model)
        self.spin_tiles_y.valueChanged.connect(self.sync_to_model)
        self.spin_height.valueChanged.connect(self.sync_to_model)
        self.combo_power.currentIndexChanged.connect(self.sync_to_model)

        config_layout.addWidget(make_divider())

        # ─── TERRAIN SHAPE ───
        config_layout.addWidget(make_section_label("TERRAIN SHAPE"))

        # Topology
        topo_row = QHBoxLayout()
        topo_row.setSpacing(8)
        lbl_topo = QLabel("Topology")
        lbl_topo.setObjectName("FieldLabel")
        lbl_topo.setToolTip("Select the fundamental layout structure")
        topo_row.addWidget(lbl_topo)
        self.combo_topology = QComboBox()
        self.combo_topology.addItems(
            ["Random", "Central Gorge", "Valley", "Two Lane", "Island", "Classic Cross"]
        )
        self.combo_topology.setCurrentIndex(0)
        topo_row.addWidget(self.combo_topology, 1)
        config_layout.addLayout(topo_row)

        # Lane Width
        lw_row = QHBoxLayout()
        lw_row.setSpacing(8)
        lbl_lw = QLabel("Lane Width")
        lbl_lw.setObjectName("FieldLabel")
        lbl_lw.setToolTip(
            "Scale for the width of main routes and paths (100% = default)"
        )
        lw_row.addWidget(lbl_lw)
        self.slider_lane_width = QSlider(Qt.Horizontal)
        self.slider_lane_width.setRange(0, 200)
        self.slider_lane_width.setValue(100)
        self.lbl_lane_width_val = QLabel("100%")
        lw_row.addWidget(
            make_slider_row(self.slider_lane_width, self.lbl_lane_width_val, "%"), 1
        )
        config_layout.addLayout(lw_row)


        # Mountain Height
        mh_row = QHBoxLayout()
        mh_row.setSpacing(8)
        lbl_mh = QLabel("Mountain Height")
        lbl_mh.setObjectName("FieldLabel")
        lbl_mh.setToolTip(
            "Scale for how tall impassable areas are relative to the floor (100% = default)"
        )
        mh_row.addWidget(lbl_mh)
        self.slider_mountain_height = QSlider(Qt.Horizontal)
        self.slider_mountain_height.setRange(0, 100)
        self.slider_mountain_height.setValue(50)
        self.lbl_mountain_height_val = QLabel("50%")
        mh_row.addWidget(
            make_slider_row(
                self.slider_mountain_height, self.lbl_mountain_height_val, "%"
            ),
            1,
        )
        config_layout.addLayout(mh_row)

        # Roughness
        rough_row = QHBoxLayout()
        rough_row.setSpacing(8)
        lbl_r = QLabel("Roughness")
        lbl_r.setObjectName("FieldLabel")
        lbl_r.setToolTip("Low = smooth rolling hills, High = jagged mountains")
        rough_row.addWidget(lbl_r)
        self.slider_rough = QSlider(Qt.Horizontal)
        self.slider_rough.setRange(0, 100)
        self.lbl_rough_val = QLabel("50%")
        rough_row.addWidget(
            make_slider_row(self.slider_rough, self.lbl_rough_val, "%"), 1
        )
        config_layout.addLayout(rough_row)

        # Erosion
        eros_row = QHBoxLayout()
        eros_row.setSpacing(8)
        lbl_e = QLabel("Erosion")
        lbl_e.setObjectName("FieldLabel")
        lbl_e.setToolTip("Hydraulic erosion — smooths sharp features naturally")
        eros_row.addWidget(lbl_e)
        self.slider_erosion = QSlider(Qt.Horizontal)
        self.slider_erosion.setRange(0, 100)
        self.lbl_erosion_val = QLabel("50%")
        eros_row.addWidget(
            make_slider_row(self.slider_erosion, self.lbl_erosion_val, "%"), 1
        )
        config_layout.addLayout(eros_row)

        # Connect slider value displays
        self.slider_lane_width.valueChanged.connect(
            lambda v: self.lbl_lane_width_val.setText(f"{v}%")
        )
        self.slider_mountain_height.valueChanged.connect(
            lambda v: self.lbl_mountain_height_val.setText(f"{v}%")
        )
        self.slider_rough.valueChanged.connect(
            lambda v: self.lbl_rough_val.setText(f"{v}%")
        )
        self.slider_erosion.valueChanged.connect(
            lambda v: self.lbl_erosion_val.setText(f"{v}%")
        )
        self.combo_topology.currentIndexChanged.connect(self.sync_to_model)
        self.slider_lane_width.valueChanged.connect(self.sync_to_model)
        self.slider_mountain_height.valueChanged.connect(self.sync_to_model)
        self.slider_rough.valueChanged.connect(self.sync_to_model)
        self.slider_erosion.valueChanged.connect(self.sync_to_model)

        config_layout.addWidget(make_divider())

        # ─── BASE AREAS ───
        config_layout.addWidget(make_section_label("BASE AREAS"))

        # Base Radius
        br_row = QHBoxLayout()
        br_row.setSpacing(8)
        lbl_br = QLabel("Clear Radius")
        lbl_br.setObjectName("FieldLabel")
        lbl_br.setToolTip("Radius of flat area around bases (0 = disabled)")
        br_row.addWidget(lbl_br)
        self.slider_base_radius = QSlider(Qt.Horizontal)
        self.slider_base_radius.setRange(0, 8192)
        self.lbl_base_radius_val = QLabel("0")
        br_row.addWidget(
            make_slider_row(self.slider_base_radius, self.lbl_base_radius_val), 1
        )
        config_layout.addLayout(br_row)

        # Base Flatness
        bf_row = QHBoxLayout()
        bf_row.setSpacing(8)
        lbl_bf = QLabel("Flatness")
        lbl_bf.setObjectName("FieldLabel")
        lbl_bf.setToolTip(
            "How flat the base area is (0 = natural, 100 = perfectly flat)"
        )
        bf_row.addWidget(lbl_bf)
        self.slider_base_flatness = QSlider(Qt.Horizontal)
        self.slider_base_flatness.setRange(0, 100)
        self.lbl_base_flat_val = QLabel("0%")
        bf_row.addWidget(
            make_slider_row(self.slider_base_flatness, self.lbl_base_flat_val, "%"), 1
        )
        config_layout.addLayout(bf_row)

        self.slider_base_radius.valueChanged.connect(
            lambda v: self.lbl_base_radius_val.setText(str(v))
        )
        self.slider_base_flatness.valueChanged.connect(
            lambda v: self.lbl_base_flat_val.setText(f"{v}%")
        )
        self.slider_base_radius.valueChanged.connect(self.sync_to_model)
        self.slider_base_flatness.valueChanged.connect(self.sync_to_model)

        config_layout.addWidget(make_divider())

        # ─── MATERIALS ───
        config_layout.addWidget(make_section_label("MATERIALS"))

        mat_row = QHBoxLayout()
        mat_row.setSpacing(8)
        lbl_mat = QLabel("Texture")
        lbl_mat.setObjectName("FieldLabel")
        lbl_mat.setToolTip("Ground surface blend material")
        mat_row.addWidget(lbl_mat)
        self.combo_material = QComboBox()
        self.combo_material.addItems(self.terrain_materials)
        self.combo_material.setCurrentText("common/nature/blend_grass_mountainwall_000")
        mat_row.addWidget(self.combo_material, 1)
        config_layout.addLayout(mat_row)
        self.combo_material.currentIndexChanged.connect(self.sync_to_model)

        sky_row = QHBoxLayout()
        sky_row.setSpacing(8)
        lbl_sky = QLabel("Skybox")
        lbl_sky.setObjectName("FieldLabel")
        sky_row.addWidget(lbl_sky)
        self.combo_skybox = QComboBox()
        self.combo_skybox.addItems(self.skyboxes)
        self.combo_skybox.setCurrentText("empsky_overcast3yellow")
        sky_row.addWidget(self.combo_skybox, 1)
        config_layout.addLayout(sky_row)
        self.combo_skybox.currentIndexChanged.connect(self.sync_to_model)

        config_layout.addWidget(make_divider())

        # ─── SPAWN SETTINGS ───
        config_layout.addWidget(make_section_label("SPAWN SETTINGS"))

        spawn_grid = QGridLayout()
        spawn_grid.setSpacing(4)

        self.chk_disable_commander = QCheckBox("No Commander")
        self.chk_disable_buildings = QCheckBox("No Buildings")
        self.chk_disable_resources = QCheckBox("No Resources")
        self.chk_minimal_map = QCheckBox("Minimal (No Props)")
        self.chk_terrain_only = QCheckBox("Terrain Only")

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
        config_layout.addLayout(spawn_grid)

        # ─── VALIDATION ───
        config_layout.addWidget(make_divider())
        self.lbl_validation = QLabel("✓  All checks passed")
        self.lbl_validation.setObjectName("ValidationLabel")
        self.lbl_validation.setWordWrap(True)
        config_layout.addWidget(self.lbl_validation)

        config_layout.addStretch()

        # Wrap in scroll area
        scroll_content = QWidget()
        scroll_content.setLayout(config_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumWidth(240)

        # ── Data & Tools Setup ──



        self.preview_widget = MapPreviewWidget()
        self.preview_widget.setMinimumWidth(200)




        # Inner splitter: config scroll | tabs
        self._inner_splitter = QSplitter(Qt.Horizontal)
        self._inner_splitter.addWidget(scroll)
        self._inner_splitter.addWidget(self.preview_widget)
        self._inner_splitter.setStretchFactor(0, 0)
        self.preview_widget.layout_changed.connect(self.on_layout_changed)
        self.preview_widget.base_moved.connect(self.on_base_moved)
        self.preview_widget.resource_moved.connect(self.on_resource_moved)
        self.preview_widget.resource_added.connect(self.on_resource_added)
        self._inner_splitter.setStretchFactor(1, 1)
        self._inner_splitter.setSizes([380, 620])
        self._inner_splitter.setChildrenCollapsible(False)

        main_area_layout.addWidget(self._inner_splitter)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.run_preview)

        self._root_splitter.addWidget(sidebar)
        self._root_splitter.addWidget(main_area)
        self._root_splitter.setStretchFactor(0, 0)
        self._root_splitter.setStretchFactor(1, 1)
        self._root_splitter.setSizes([220, 930])

    def validate_current_layout(self):
        """Validates layout and returns set of invalid entity IDs for UI highlighting."""
        try:
            spec = self.config_model.make_spec()
            layout_result = spec.validate_layout()
            # We don't update lbl_validation here because sync_to_model handles it,
            # but we return the invalid entities for the editor icons.
            return layout_result.invalid_entities
        except Exception:
            return set()

    def clear_resources(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all resource nodes?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return

        self.config_model.custom_resources = []
        invalid_entities = self.validate_current_layout()
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            [],
            invalid_entities=invalid_entities,
        )
        self.preview_timer.start(500)

    def on_tool_changed(self, id):
        pass # Tools are fully managed by preview_widget internally now

    def on_base_moved(self, faction, x, y):
        if x == 0.0 and y == 0.0:
            val_x, val_y = None, None
        else:
            val_x, val_y = x, y

        if faction == "imp":
            self.config_model.custom_imp_base_x = val_x
            self.config_model.custom_imp_base_y = val_y
        else:
            self.config_model.custom_nf_base_x = val_x
            self.config_model.custom_nf_base_y = val_y

        invalid_entities = self.validate_current_layout()
        # Ensure we sync invalid entities to canvas without wiping it out completely via set_entities
        # which creates a feedback loop with base_moved / layout_changed
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()
        self.preview_timer.start(500)

    def on_resource_moved(self, index, x, y):
        if self.config_model.custom_resources and 0 <= index < len(
            self.config_model.custom_resources
        ):
            self.config_model.custom_resources[index] = (x, y)
        invalid_entities = self.validate_current_layout()
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()
        # Resource positions do not affect the terrain heightmap itself,
        # so we don't necessarily need to re-run the pipeline on move,
        # but we can do it if desired.
        self.preview_timer.start(500)


    def on_layout_changed(self):
        # When clear all is called it doesn't emit resource removed signals, just layout changed.
        # We must sync everything from the preview widget's internal state.

        imp_pos = self.preview_widget.imp_base
        if imp_pos and imp_pos[0] is not None and imp_pos[1] is not None:
            self.config_model.custom_imp_base_x = imp_pos[0]
            self.config_model.custom_imp_base_y = imp_pos[1]
        else:
            self.config_model.custom_imp_base_x = None
            self.config_model.custom_imp_base_y = None

        nf_pos = self.preview_widget.nf_base
        if nf_pos and nf_pos[0] is not None and nf_pos[1] is not None:
            self.config_model.custom_nf_base_x = nf_pos[0]
            self.config_model.custom_nf_base_y = nf_pos[1]
        else:
            self.config_model.custom_nf_base_x = None
            self.config_model.custom_nf_base_y = None

        self.config_model.custom_resources = list(self.preview_widget.resources)

        # Sync the invalid entities back
        invalid_entities = self.validate_current_layout()
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()

        self.update_validation_status()
        self.preview_timer.start(500)

    def on_resource_added(self, x, y):
        if self.config_model.custom_resources is None:
            self.config_model.custom_resources = []
        
        # Deduplicate: don't add if a resource already exists at this exact spot
        for rx, ry in self.config_model.custom_resources:
            if abs(rx - x) < 1.0 and abs(ry - y) < 1.0:
                return

        self.config_model.custom_resources.append((x, y))
        invalid_entities = self.validate_current_layout()
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()
        self.preview_timer.start(500)

    def run_preview(self):
        if not hasattr(self, "preview_worker") or not self.preview_worker.isRunning():
            nodes, connections, resources = self.preview_widget.get_layout_from_editor()
            self.preview_worker = PreviewWorker(
                self.config_model,
                custom_nodes=nodes if nodes else None,
                custom_connections=connections if connections else None,
                custom_resources=resources
            )
            self.preview_worker.finished.connect(self.on_preview_finished)
            self.preview_worker.start()

    def on_preview_finished(self, grid, spec):
        if getattr(sys, "frozen", False) and not grid:
            log_path = Path(sys.executable).parent / "preview_signal_received.log"
            with open(log_path, "w") as f:
                f.write("Signal received but grid is None.\n")

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
            self.preview_widget.set_raw_heights(heights)

            imp_pos = (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y)
            nf_pos = (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y)

            res = (
                self.config_model.custom_resources
                if self.config_model.custom_resources
                else []
            )
            invalid_entities = self.validate_current_layout()
            self.preview_widget.set_entities(
                imp_pos, nf_pos, res, invalid_entities=invalid_entities
            )

    def apply_dark_theme(self):
        ACCENT = "#1d6feb"  # steel blue
        ACCENT_HOVER = "#4d8ef5"  # lighter blue
        ACCENT_ACTIVE = "#1553c7"  # dark blue
        BG_BASE = "#0f1117"
        BG_PANEL = "#14161d"
        BG_WIDGET = "#1c1e28"
        BG_INPUT = "#22243000".replace("00", "")
        BG_INPUT = "#21232e"
        BORDER = "#2a2d3a"
        BORDER_FOCUS = ACCENT
        TEXT_PRI = "#e8eaf0"
        TEXT_SEC = "#8890a4"
        TEXT_DIM = "#484c5c"
        GREEN = "#22c55e"
        RED = "#ef4444"
        BLUE = ACCENT

        style = f"""
        /* ── Global ── */
        QMainWindow, QWidget {{
            background-color: {BG_BASE};
            color: {TEXT_PRI};
            font-family: 'Segoe UI', 'Inter', 'Ubuntu', Helvetica, Arial, sans-serif;
            font-size: 12px;
        }}

        /* ── Sidebar ── */
        QWidget#Sidebar {{
            background-color: {BG_PANEL};
            border-right: 1px solid {BORDER};
        }}
        QLabel#BrandTitle {{
            font-size: 13px;
            font-weight: bold;
            color: {TEXT_PRI};
            border-left: 3px solid {ACCENT};
            padding-left: 8px;
            padding-top: 2px;
            padding-bottom: 2px;
        }}
        QLabel#SectionLabel {{
            font-size: 9px;
            font-weight: bold;
            color: {TEXT_DIM};
            letter-spacing: 1.5px;
            padding-top: 2px;
        }}
        QLabel#HintLabel {{
            font-size: 10px;
            color: {TEXT_SEC};
        }}
        QWidget#Divider {{
            background-color: {BORDER};
        }}

        /* \u2500\u2500 Preset Buttons \u2500\u2500 */
        QPushButton#PresetButton {{
            background-color: {BG_WIDGET};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 5px 8px;
            color: {TEXT_SEC};
            font-size: 11px;
        }}
        QPushButton#PresetButton:hover {{
            background-color: #2a2a34;
            border: 1px solid #44444e;
            color: {TEXT_PRI};
        }}
        QPushButton#PresetButton:checked {{
            background-color: {ACCENT_ACTIVE};
            border: 1px solid {ACCENT};
            color: white;
        }}
        QPushButton#PresetButton:pressed {{
            background-color: {ACCENT_ACTIVE};
        }}

        /* \u2500\u2500 Small Button \u2500\u2500 */
        QPushButton#SmallButton {{
            background: transparent;
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px 10px;
            color: {TEXT_SEC};
            font-size: 10px;
        }}
        QPushButton#SmallButton:hover {{
            background: {BG_WIDGET};
            color: {TEXT_PRI};
            border: 1px solid #44444e;
        }}

        /* ── Generate Button ── */
        QPushButton#GenerateButton {{
            background: {ACCENT};
            border: none;
            border-radius: 7px;
            color: white;
            font-weight: 600;
            font-size: 12px;
            padding: 10px;
            letter-spacing: 0.3px;
        }}
        QPushButton#GenerateButton:hover {{
            background: {ACCENT_HOVER};
        }}
        QPushButton#GenerateButton:pressed {{
            background: {ACCENT_ACTIVE};
        }}
        QPushButton#GenerateButton:disabled {{
            background: #1c2030;
            color: {TEXT_DIM};
        }}

        /* ── Compile Button ── */
        QPushButton#CompileButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #26a854, stop:1 #1a7a3c);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: bold;
            font-size: 12px;
            padding: 10px;
        }}
        QPushButton#CompileButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #30d068, stop:1 #22a050);
        }}
        QPushButton#CompileButton:pressed {{
            background: #155c30;
        }}
        QPushButton#CompileButton:disabled {{
            background: #1e2e24;
            color: {TEXT_DIM};
        }}

        /* ── Generic Buttons ── */
        QPushButton {{
            background-color: {BG_WIDGET};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 7px 12px;
            color: {TEXT_PRI};
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: #2c2c38;
            border: 1px solid #44444e;
        }}
        QPushButton:pressed {{
            background-color: {BG_INPUT};
            border: 1px solid {BORDER};
        }}
        QPushButton:disabled {{
            background-color: #1a1a1f;
            color: {TEXT_DIM};
            border: 1px solid #22222a;
        }}

        /* ── GroupBox ── */
        QGroupBox {{
            border: 1px solid {BORDER};
            border-radius: 8px;
            margin-top: 14px;
            padding-top: 6px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
            color: {TEXT_SEC};
        }}

        /* ── Inputs ── */
        QSpinBox, QComboBox, QLineEdit {{
            background-color: {BG_INPUT};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 5px 9px;
            color: {TEXT_PRI};
            selection-background-color: {ACCENT};
        }}
        QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
            border: 1px solid {BORDER_FOCUS};
            background-color: #2c2c36;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 0;
            height: 0;
            border: none;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {TEXT_SEC};
            margin-right: 8px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {BG_WIDGET};
            border: 1px solid {BORDER};
            selection-background-color: {ACCENT};
            color: {TEXT_PRI};
            outline: none;
        }}

        /* ── Sliders ── */
        QSlider {{
            height: 24px;
        }}
        QSlider::groove:horizontal {{
            border: none;
            height: 6px;
            background: #252832;
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: #ffffff;
            border: 2px solid {ACCENT};
            width: 14px;
            height: 14px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: #ffffff;
            border: 2px solid {ACCENT_HOVER};
            width: 16px;
            height: 16px;
            margin: -7px 0;
            border-radius: 10px;
        }}
        QSlider::handle:horizontal:pressed {{
            background: {ACCENT};
            border: 2px solid #ffffff;
        }}

        /* ── Checkboxes ── */
        QCheckBox {{
            spacing: 7px;
            color: {TEXT_PRI};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {BORDER};
            background: {BG_INPUT};
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT};
            border: 1px solid {ACCENT};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {ACCENT};
        }}
        QCheckBox:disabled {{
            color: {TEXT_DIM};
        }}

        /* ── Radio Buttons ── */
        QRadioButton {{
            spacing: 6px;
            font-size: 11px;
            color: {TEXT_PRI};
        }}
        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 8px;
            border: 1px solid {BORDER};
            background: {BG_INPUT};
        }}
        QRadioButton::indicator:checked {{
            background: {ACCENT};
            border: 2px solid {ACCENT_HOVER};
        }}

        /* ── ScrollArea ── */
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 8px;
        }}
        QScrollBar::handle:vertical {{
            background: #38383e;
            min-height: 24px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #505060;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            border: none;
            background: transparent;
            height: 8px;
        }}
        QScrollBar::handle:horizontal {{
            background: #38383e;
            min-width: 24px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #505060;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* ── Splitter ── */
        QSplitter::handle {{
            background: {BORDER};
        }}
        QSplitter::handle:horizontal {{
            width: 1px;
        }}
        QSplitter::handle:hover {{
            background: {ACCENT};
        }}

        /* ── Config panel ── */
        QLabel#FieldLabel {{
            font-size: 11px;
            font-weight: 600;
            color: {TEXT_SEC};
            min-width: 80px;
        }}
        QLabel#ConfigSection {{
            font-size: 9px;
            font-weight: bold;
            color: {TEXT_DIM};
            letter-spacing: 1.5px;
            padding: 6px 0 2px 0;
        }}
        QLabel#SliderValue {{
            font-size: 11px;
            font-weight: bold;
            color: {TEXT_SEC};
            font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace;
            min-width: 36px;
        }}
        QLabel#ValidationLabel {{
            font-size: 11px;
            padding: 8px 10px;
            border-radius: 6px;
        }}

        /* ── Tool Buttons (preview toolbar) ── */
        QPushButton#ToolButton, QPushButton#ToolButtonBlue,
        QPushButton#ToolButtonRed, QPushButton#ToolButtonGreen,
        QPushButton#SmallButton {{
            background: {BG_WIDGET};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px 6px;
            font-size: 9px;
            color: {TEXT_SEC};
            min-width: 38px;
        }}
        QPushButton#ToolButton:checked, QPushButton#SmallButton:active {{
            background: {ACCENT_ACTIVE};
            border: 1px solid {ACCENT};
            color: white;
        }}
        QPushButton#ToolButtonBlue:checked {{
            background: #1e3a5f;
            border: 1px solid {BLUE};
            color: {BLUE};
        }}
        QPushButton#ToolButtonRed:checked {{
            background: #3f1e1e;
            border: 1px solid {RED};
            color: {RED};
        }}
        QPushButton#ToolButtonGreen:checked {{
            background: #1e3f24;
            border: 1px solid {GREEN};
            color: {GREEN};
        }}
        QPushButton#ToolButton:hover, QPushButton#ToolButtonBlue:hover,
        QPushButton#ToolButtonRed:hover, QPushButton#ToolButtonGreen:hover,
        QPushButton#SmallButton:hover {{
            background: #2a2a34;
            border: 1px solid #44444e;
        }}
        """
        self.setStyleSheet(style)


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

    def on_auto_copy_changed(self):
        """Toggle UI elements based on the auto copy setting."""
        is_auto = self.chk_auto_copy.isChecked()
        self.config.set("auto_copy_to_empires", is_auto)
        self.custom_output_container.setVisible(not is_auto)

    def on_custom_output_changed(self, text):
        """Handle changes to custom output path."""
        self.config.set("custom_output_folder", text)
        self.update_custom_status()

    def browse_custom_output(self):
        """Browse for custom output folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Custom Output Folder"
        )
        if folder:
            self.edit_custom_output.setText(folder)
            self.config.set("custom_output_folder", folder)
            self.update_custom_status()

    def update_custom_status(self):
        path = self.edit_custom_output.text()
        if not path:
            self.lbl_custom_status.setText("Not configured")
            self.lbl_custom_status.setStyleSheet("color: #555560; font-size: 10px;")
        elif not Path(path).exists():
            self.lbl_custom_status.setText("✗  Not Found")
            self.lbl_custom_status.setStyleSheet("color: #ef4444; font-size: 10px;")
        else:
            self.lbl_custom_status.setText("✓  Valid")
            self.lbl_custom_status.setStyleSheet(
                "color: #22c55e; font-size: 10px; font-weight: bold;"
            )

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
            self.lbl_empires_status.setStyleSheet("color: #555560; font-size: 10px;")
        else:
            is_valid, msg = validate_empires_path(path)
            if is_valid:
                self.lbl_empires_status.setText("✓  Valid")
                self.lbl_empires_status.setStyleSheet(
                    "color: #22c55e; font-size: 10px; font-weight: bold;"
                )
            else:
                self.lbl_empires_status.setText(f"✗  {msg}")
                self.lbl_empires_status.setStyleSheet(
                    "color: #ef4444; font-size: 10px;"
                )

    def on_empires_path_changed(self, text):
        """Handle changes to the Empires path field."""
        self.config.set("empires_path", text)
        self.update_empires_status()

    def sync_to_ui(self):
        """Updates UI components to match the config model."""
        with self._block_signals(
            self.spin_seed,
            self.spin_tiles_x,
            self.spin_tiles_y,
            self.spin_height,
            self.combo_topology,
            self.slider_lane_width,
            self.slider_mountain_height,
            self.slider_rough,
            self.slider_erosion,
            self.slider_base_radius,
            self.slider_base_flatness,
            self.combo_power,
            self.combo_material,
            self.combo_skybox,
            self.chk_disable_commander,
            self.chk_disable_buildings,
            self.chk_disable_resources,
            self.chk_minimal_map,
            self.chk_terrain_only,
        ):
            self.spin_seed.setValue(self.config_model.seed)
            self.spin_tiles_x.setValue(self.config_model.tiles_x)
            self.spin_tiles_y.setValue(self.config_model.tiles_y)
            self.spin_height.setValue(self.config_model.height_scale)
            topology_map = {
                "random": 0,
                "central_gorge": 1,
                "valley": 2,
                "two_lane": 3,
                "island": 4,
                "classic_cross": 5,
            }
            self.combo_topology.setCurrentIndex(
                topology_map.get(self.config_model.topology, 0)
            )
            self.slider_lane_width.setValue(
                int(self.config_model.lane_width_scale * 100)
            )
            self.slider_mountain_height.setValue(
                int(min(1.0, self.config_model.mountain_height_scale) * 100)
            )
            self.slider_rough.setValue(int(self.config_model.roughness * 100))
            self.slider_erosion.setValue(int(self.config_model.erosion_strength * 100))
            self.slider_base_radius.setValue(self.config_model.base_clear_radius)
            self.slider_base_flatness.setValue(
                int(self.config_model.base_flatness * 100)
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
            self.chk_disable_resources.setChecked(
                self.config_model.disable_resource_nodes
            )
            self.chk_minimal_map.setChecked(self.config_model.minimal_map)
            self.chk_terrain_only.setChecked(self.config_model.terrain_only)

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

        topology_reverse_map = {
            0: "random",
            1: "central_gorge",
            2: "valley",
            3: "two_lane",
            4: "island",
            5: "classic_cross",
        }
        self.config_model.topology = topology_reverse_map.get(
            self.combo_topology.currentIndex(), "random"
        )
        self.config_model.lane_width_scale = self.slider_lane_width.value() / 100.0
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_lane_scale(self.config_model.lane_width_scale)
        self.config_model.mountain_height_scale = (
            self.slider_mountain_height.value() / 100.0
        )

        self.config_model.roughness = self.slider_rough.value() / 100.0
        self.config_model.erosion_strength = self.slider_erosion.value() / 100.0
        self.config_model.base_clear_radius = self.slider_base_radius.value()
        self.config_model.base_flatness = self.slider_base_flatness.value() / 100.0

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

        # Update map info line
        tx = self.spin_tiles_x.value()
        ty = self.spin_tiles_y.value()
        w = tx * 512
        h = ty * 512
        self.lbl_map_info.setText(f"{w}×{h} units  ·  {tx}×{ty} tiles")

        if is_valid:
            # Check layout from editor
            if hasattr(self, "preview_widget"):
                try:
                    nodes, _, _ = self.preview_widget.get_layout_from_editor()
                    if nodes:
                        temp_spec = self.config_model.make_spec()
                        
                        # Extract base and resource positions from editor nodes
                        imp_pos = next(((n.x, n.y) for n in nodes if "imp" in n.type.lower() or (n.type == "base_zone" and nodes.index(n) == 0)), None)
                        nf_pos = next(((n.x, n.y) for n in nodes if "nf" in n.type.lower() or (n.type == "base_zone" and nodes.index(n) == 1)), None)
                        res_positions = [(n.x, n.y) for n in nodes if "resource" in n.type.lower()]
                        
                        if imp_pos:
                            temp_spec.custom_imp_base_x, temp_spec.custom_imp_base_y = imp_pos
                        if nf_pos:
                            temp_spec.custom_nf_base_x, temp_spec.custom_nf_base_y = nf_pos
                        if res_positions:
                            temp_spec.custom_resources = res_positions
                            
                        val_result = temp_spec.validate_layout()
                        if not val_result.valid:
                            is_valid = False
                            msg = val_result.errors[0]
                except Exception:
                    # Ignore errors during real-time validation to prevent UI hang
                    pass

        if is_valid:
            self.lbl_validation.setText("✓  All checks passed")
            self.lbl_validation.setStyleSheet(
                "color: #22c55e; font-size: 11px; "
                "background: #122218; border-radius: 6px; padding: 8px 10px;"
            )
            self.btn_generate.setEnabled(True)
        else:
            self.lbl_validation.setText(f"✗  {msg}")
            self.lbl_validation.setStyleSheet(
                "color: #ef4444; font-size: 11px; "
                "background: #221212; border-radius: 6px; padding: 8px 10px;"
            )
            self.btn_generate.setEnabled(False)

    def generate_map(self):
        is_valid, msg = self.config_model.validate()
        if not is_valid:
            return

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating...")

        # Run generation in background
        map_name = self.txt_map_name.text().strip() or "gui_terrain"
        layout_nodes, layout_conns, layout_res = self.preview_widget.get_layout_from_editor()
        
        self.worker = GenerationWorker(
            self.config_model,
            custom_nodes=layout_nodes if layout_nodes else None,
            custom_connections=layout_conns if layout_conns else None,
            custom_resources=layout_res,
            output_filename=map_name
        )
        self.worker.finished.connect(self.on_generation_finished)
        self.worker.start()

    def on_generation_finished(self, success, msg):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Generate VMF")

        if success:
            map_name = self.txt_map_name.text().strip() or "gui_terrain"
            self._last_vmf_path = str(OUTPUT_DIR / f"{map_name}.vmf")

            # If auto-copy is false and custom folder is set, copy files to the custom folder
            auto_copy = self.config.get("auto_copy_to_empires", True)
            custom_folder = self.config.get("custom_output_folder", "")
            if not auto_copy and custom_folder and Path(custom_folder).exists():
                try:
                    import shutil
                    custom_path = Path(custom_folder)

                    vmf_dir = custom_path / "vmf"
                    vmf_dir.mkdir(parents=True, exist_ok=True)
                    vmf_src = OUTPUT_DIR / f"{map_name}.vmf"
                    if vmf_src.exists():
                        shutil.copy2(vmf_src, vmf_dir / f"{map_name}.vmf")

                    txt_dir = custom_path / "txt"
                    txt_dir.mkdir(parents=True, exist_ok=True)
                    txt_src = OUTPUT_DIR / f"{map_name}.txt"
                    if txt_src.exists():
                        shutil.copy2(txt_src, txt_dir / f"{map_name}.txt")

                    minimap_dir = custom_path / "minimap"
                    minimap_dir.mkdir(parents=True, exist_ok=True)
                    vmt_src = OUTPUT_DIR / f"{map_name}.vmt"
                    if vmt_src.exists():
                        shutil.copy2(vmt_src, minimap_dir / f"{map_name}.vmt")
                    vtf_src = OUTPUT_DIR / f"{map_name}.vtf"
                    if vtf_src.exists():
                        shutil.copy2(vtf_src, minimap_dir / f"{map_name}.vtf")

                    msg += f"\nFiles copied to {custom_folder}"
                except Exception as e:
                    msg += f"\nWarning: Failed to copy to custom folder: {e}"

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
        auto_copy = self.config.get("auto_copy_to_empires", True)
        custom_folder = self.config.get("custom_output_folder", "")

        self.compile_worker = CompileWorker(vmf_path, empires_path, auto_copy, custom_folder)
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

    def __init__(self, vmf_path, empires_path="", auto_copy=True, custom_folder=""):
        super().__init__()
        self.vmf_path = vmf_path
        self.empires_path = empires_path
        self.auto_copy = auto_copy
        self.custom_folder = custom_folder

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
                        auto_copy=self.auto_copy,
                        custom_output=self.custom_folder,
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

                if not self.auto_copy:
                    cmd.append("--no-auto-copy")
                if self.custom_folder:
                    cmd.extend(["--custom-output", self.custom_folder])

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

            success_msg = "BSP compiled"
            if self.auto_copy:
                success_msg += " and deployed to Empires.\nOverview TXT + minimap VMT were also deployed for stability."
            elif self.custom_folder:
                success_msg += f" and moved to custom folder:\n{self.custom_folder}"
            else:
                success_msg += " successfully."

            self.finished.emit(True, success_msg)
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TerrainGeneratorGUI()
    window.show()
    sys.exit(app.exec())
