import sys
import json
import random
import math
from pathlib import Path

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

import os
from contextlib import contextmanager
from typing import List, Optional, Tuple

if not getattr(sys, "frozen", False):
    os.chdir(PROJECT_ROOT)

from PySide6.QtWidgets import (
    QApplication,
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
    QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import (
    QIcon,
    QImage,
    QShortcut,
    QKeySequence,
)
from tools.preview_widget import MapPreviewWidget


from src.config_model import GUIConfigModel, MAX_MAP_DISPINFO, MAX_MAP_WORLD_SIZE

def _read_vpk_string(f) -> str:
    """Read null-terminated string from binary file."""
    chars = []
    while True:
        c = f.read(1)
        if c == b'\x00' or c == b'':
            break
        chars.append(c)
    return b''.join(chars).decode('utf-8', errors='replace')


def parse_vpk_dir(vpk_dir_path: str) -> set[str]:
    """
    Parse a Source Engine _dir.vpk file and return a set of all
    file paths contained in the VPK archive.

    VPK dir format (binary):
    - 4 bytes: signature (0x55AA1234)
    - 2 bytes: version
    - 2 bytes: tree size
    - Then: tree of extension -> path -> filename entries
    """
    import struct

    paths = set()
    try:
        with open(vpk_dir_path, 'rb') as f:
            # Header
            sig = struct.unpack('<I', f.read(4))[0]
            if sig != 0x55AA1234:
                return paths
            version = struct.unpack('<H', f.read(2))[0]
            f.read(2)  # tree_size
            if version == 2:
                f.read(16)  # extra header fields

            # Tree: extension -> directory -> filename
            while True:
                ext = _read_vpk_string(f)
                if ext == '':
                    break
                while True:
                    directory = _read_vpk_string(f)
                    if directory == '':
                        break
                    while True:
                        filename = _read_vpk_string(f)
                        if filename == '':
                            break
                        # Skip entry data (18 bytes)
                        f.read(18)
                        # Build full path
                        if directory == ' ':
                            full = f"{filename}.{ext}"
                        else:
                            full = f"{directory}/{filename}.{ext}"
                        paths.add(full.lower())
    except Exception as e:
        print(f"[VPK] Failed to parse {vpk_dir_path}: {e}")
    return paths
from src.terrain_pipeline import (  # noqa: E402
    run_pipeline,
    calculate_slopes,
    export_minimap,
    apply_pipeline_for_preview,
    NUMBA_AVAILABLE,
)
from src.export_utils import export_vmf, get_versioned_path  # noqa: E402
from src.vmf_gen import (  # noqa: E402
    SAFE_EMPIRES_SKYBOXES,
    DEFAULT_SAFE_SKYBOX,
)
from src.steam_paths import validate_empires_path  # noqa: E402
from config import Config  # noqa: E402
from src import project_utils  # noqa: E402
from src.qt_widgets import WidePopupComboBox  # noqa: E402

# Ensure OUTPUT_DIR is writable. In bundled mode, avoid the executable's directory
# as it may be installed in a protected location like Program Files.
if getattr(sys, "frozen", False):
    # Use user's Documents folder instead
    OUTPUT_DIR = Path.home() / "Documents" / "TerrainGenerator" / "output"
else:
    OUTPUT_DIR = PROJECT_ROOT / "output"

# Make sure it exists
try:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    # Fallback to local app data if Documents is somehow not writable
    OUTPUT_DIR = Path.home() / ".local" / "share" / "TerrainGenerator" / "output"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class PreviewWorker(QThread):
    finished = Signal(object, object)  # grid, spec

    def __init__(
        self,
        config_model,
        custom_nodes=None,
        custom_connections=None,
        custom_resources=None,
        global_selection_mask=None,
        initial_heights=None,
        texture_overlay=None,
        texture_mapping=None,
        tile_overlay=None,
        tile_paint_target="floor",
    ):
        super().__init__()
        self.config_model = config_model
        self.custom_nodes = custom_nodes
        self.custom_connections = custom_connections
        self.custom_resources = custom_resources
        self.global_selection_mask = global_selection_mask
        self.initial_heights = initial_heights
        self.texture_overlay = texture_overlay
        self.texture_mapping = texture_mapping
        self.tile_overlay = tile_overlay
        self.tile_paint_target = tile_paint_target

    def run(self):
        try:
            # We must not modify the original model's spec, but we can make a custom spec
            # Pass validate=False so we still get a preview even if nodes are being dragged
            spec = self.config_model.make_spec(validate=False)
            spec.displacement_power = (
                3  # Power 3 is still fast but shows much more detail
            )
            # Enable scaled-down erosion for preview (max 20000 iterations)
            # Use 50% scaling because the preview grid is faster than the full VMF one
            spec.erosion_iterations = min(int(spec.erosion_iterations * 0.5), 20000)
            spec.disable_commander = True
            spec.disable_buildings = True
            spec.disable_resource_nodes = True
            spec.custom_tile_paint_target = self.tile_paint_target

            if self.custom_nodes is not None:
                spec.custom_layout_nodes = self.custom_nodes
            if self.custom_connections is not None:
                spec.custom_layout_connections = self.custom_connections

            if self.custom_resources is not None:
                spec.custom_resources = self.custom_resources

            if self.texture_overlay is not None and self.texture_mapping:
                id_to_material = {v: k for k, v in self.texture_mapping.items()}
                custom_materials = {}
                h, w = self.texture_overlay.shape
                # Calculate number of tiles
                tiles_x = spec.tiles_x
                tiles_y = spec.tiles_y
                step_y = max(1, h / tiles_y)
                step_x = max(1, w / tiles_x)
                for ty in range(tiles_y):
                    for tx in range(tiles_x):
                        sample_y = min(h - 1, int((ty + 0.5) * step_y))
                        sample_x = min(w - 1, int((tx + 0.5) * step_x))
                        mat_id = int(self.texture_overlay[sample_y, sample_x])
                        if mat_id > 0 and mat_id in id_to_material:
                            custom_materials[(tx, ty)] = id_to_material[mat_id]
                if custom_materials:
                    spec.custom_tile_materials = custom_materials

            if self.tile_overlay is not None and self.texture_mapping:
                id_to_material = {v: k for k, v in self.texture_mapping.items()}
                if spec.custom_tile_materials is None:
                    spec.custom_tile_materials = {}

                ty, tx = self.tile_overlay.shape
                for y in range(ty):
                    for x in range(tx):
                        mat_id = int(self.tile_overlay[y, x])
                        if mat_id != 0 and mat_id in id_to_material:
                            spec.custom_tile_materials[(x, y)] = id_to_material[mat_id]

            # Skip layout validation during preview to prevent crashes while dragging

            # Use initial_heights ONLY if manual_terrain is True
            initial_h = self.initial_heights if getattr(spec, "manual_terrain", False) else None

            result = run_pipeline(
                spec,
                skip_layout_validation=True,
                global_selection_mask=self.global_selection_mask,
                initial_heights=initial_h,
            )
            grid = result["grid"]
            if "pure_heights" in result:
                grid.pure_heights = result["pure_heights"]
            self.finished.emit(grid, result["spec"])
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
    finished = Signal(bool, str, object)  # success, message, warning

    def __init__(
        self,
        config_model,
        custom_nodes=None,
        custom_connections=None,
        custom_resources=None,
        output_filename="gui_terrain",
        height_overlay=None,
        global_selection_mask=None,
        initial_heights=None,
        texture_overlay=None,
        texture_mapping=None,
        tile_overlay=None,
        tile_paint_target="floor",
    ):
        super().__init__()
        self.config_model = config_model
        self.custom_nodes = custom_nodes
        self.custom_connections = custom_connections
        self.custom_resources = custom_resources
        self.output_filename = output_filename
        self.height_overlay = height_overlay
        self.global_selection_mask = global_selection_mask
        self.initial_heights = initial_heights
        self.texture_overlay = texture_overlay
        self.texture_mapping = texture_mapping
        self.tile_overlay = tile_overlay
        self.tile_paint_target = tile_paint_target
        self.project_root = None
        
        # Ensure layout data is persisted to the model for export_vmf awareness
        self.config_model.custom_layout_nodes = custom_nodes
        self.config_model.custom_layout_connections = custom_connections
        self.config_model.custom_resources = custom_resources
        self.config_model.custom_tile_materials = {} # Will be filled below

    def run(self):
        try:
            # Create a versioned project root
            self.project_root = get_versioned_path(OUTPUT_DIR, self.output_filename)
            self.project_root.mkdir(parents=True, exist_ok=True)

            spec = self.config_model.make_spec()
            spec.custom_tile_paint_target = self.tile_paint_target
            if self.custom_nodes and self.custom_connections:
                spec.custom_layout_nodes = self.custom_nodes
                spec.custom_layout_connections = self.custom_connections

            if self.custom_resources is not None:
                spec.custom_resources = self.custom_resources

            # Prepare custom tile materials for both preview and export
            custom_materials = {}
            id_to_material = {v: k for k, v in self.texture_mapping.items()} if self.texture_mapping else {}
            
            if self.texture_overlay is not None and id_to_material:
                h, w = self.texture_overlay.shape
                tiles_x = self.config_model.tiles_x
                tiles_y = self.config_model.tiles_y
                step_y = max(1, h / tiles_y)
                step_x = max(1, w / tiles_x)
                for ty in range(tiles_y):
                    for tx in range(tiles_x):
                        sample_y = min(h - 1, int((ty + 0.5) * step_y))
                        sample_x = min(w - 1, int((tx + 0.5) * step_x))
                        mat_id = int(self.texture_overlay[sample_y, sample_x])
                        if mat_id > 0 and mat_id in id_to_material:
                            custom_materials[(tx, ty)] = id_to_material[mat_id]

            if self.tile_overlay is not None and id_to_material:
                ty, tx = self.tile_overlay.shape
                for y in range(ty):
                    for x in range(tx):
                        mat_id = int(self.tile_overlay[y, x])
                        if mat_id != 0 and mat_id in id_to_material:
                            custom_materials[(x, y)] = id_to_material[mat_id]

            self.config_model.custom_tile_materials = custom_materials
            spec.custom_tile_materials = custom_materials

            # Run pipeline
            result = run_pipeline(
                spec,
                map_name=self.output_filename,
                output_dir=str(self.project_root),
                global_selection_mask=self.global_selection_mask,
                initial_heights=self.initial_heights,
            )
            if result["errors"]:
                raise Exception(f"Pipeline errors: {result['errors']}")

            grid = result["grid"]

            # Apply sculpting height overlay if present
            sculpt_warning = None
            if self.height_overlay is not None and self.height_overlay.any():
                import numpy as np
                from src.compat_utils import scipy_zoom_equivalent

                h, w = self.height_overlay.shape
                target_h = grid.rows
                target_w = grid.cols

                try:
                    # Overlay is now natively matched to bottom-to-top grid
                    overlay_to_apply = self.height_overlay

                    if (h, w) != (target_h, target_w):
                        # Rescale overlay to match the final height grid dimensions
                        scale_y = target_h / h
                        scale_x = target_w / w
                        rescaled_overlay = scipy_zoom_equivalent(
                            overlay_to_apply, (scale_y, scale_x)
                        )
                    else:
                        rescaled_overlay = overlay_to_apply

                    # Add overlay to the height grid
                    grid_heights = np.array(grid.heights, dtype=np.float64)
                    grid_heights += rescaled_overlay
                    grid.heights = grid_heights.astype(np.float32)

                    # CRITICAL: Recalculate slopes so rock textures appear on steep sculpted terrain
                    calculate_slopes(grid)

                    # CRITICAL: Re-export the minimap so the mountain appears in-game
                    export_minimap(spec, grid, self.output_filename, self.project_root)

                    print(
                        f"DEBUG: Grid max height after sculpting: {grid.max_height()}"
                    )
                except Exception as e:
                    sculpt_warning = f"Manual sculpting application failed: {e}"

            message, export_warning = export_vmf(
                grid,
                self.config_model,
                self.project_root,
                self.output_filename,
            )

            final_warning = ""
            if getattr(grid, "report", None) and grid.report.get("fallback_used"):
                final_warning += "Warning: Canyon generator failed to find a fully connected path. Generated a pure noise canyon instead.\n\n"
            if sculpt_warning:
                final_warning += sculpt_warning + "\n"
            if export_warning:
                final_warning += export_warning

            self.finished.emit(True, message, final_warning if final_warning else None)
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e), None)



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

        self._numba_first_run = True
        self._vpk_index = set()
        self.config_model = GUIConfigModel()
        self._is_dirty = False
        self.config = Config()
        self.config_model.use_smart_details = self.config.get("smart_details", True)

        # Load Empires path from config to build VPK index early
        empires_path = self.config.get("empires_path", "")
        self._vpk_index = self._build_vpk_index(empires_path)

        self.skyboxes, self.texture_themes = self.load_textures()

        self.setup_ui()
        self.apply_dark_theme()

        with self._block_signals(self.edit_empires_path):
            self.edit_empires_path.setText(empires_path)
        self.update_empires_status()

        # Initial sync and validation
        self.sync_to_ui()
        self.sync_to_model()

        # F12 screenshot
        sc = QShortcut(QKeySequence("F12"), self)
        sc.activated.connect(self.take_screenshot)

    def _build_vpk_index(self, empires_path: str) -> set[str]:
        """
        Parse all _dir.vpk files in empires_path and return
        combined set of available file paths.
        """
        available = set()
        if not empires_path or not os.path.exists(empires_path):
            return available

        dir_vpks = [
            "materials_dir.vpk",
            "materials_legacy_dir.vpk",
            "models_dir.vpk",
            "models_legacy_dir.vpk",
            "misc_dir.vpk",
        ]
        for vpk_name in dir_vpks:
            vpk_path = os.path.join(empires_path, vpk_name)
            if os.path.exists(vpk_path):
                found = parse_vpk_dir(vpk_path)
                available.update(found)
                print(f"[VPK] {vpk_name}: {len(found)} entries")
            else:
                print(f"[VPK] Not found: {vpk_path}")

        # Also check loose files in materials/ and models/ folders
        for root, dirs, files in os.walk(empires_path):
            for fname in files:
                rel = os.path.relpath(
                    os.path.join(root, fname), empires_path
                ).replace(os.sep, '/').lower()
                available.add(rel)

        print(f"[VPK] Total available files: {len(available)}")
        return available

    def is_texture_available(self, material_path: str) -> bool:
        """
        Check if a material is available in the VPK index.
        material_path: e.g. "common/nature/blend_grass_mountainwall_000"
        """
        if not self._vpk_index:
            return True  # no path configured -> assume all available
        vmt = f"materials/{material_path.lower()}.vmt"
        return vmt in self._vpk_index

    def is_model_available(self, model_path: str) -> bool:
        """
        model_path: e.g. "models/props_foliage/tree_pine01.mdl"
        """
        if not self._vpk_index:
            return True
        return model_path.lower() in self._vpk_index

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
            themes = data.get("themes", {})
            skyboxes = data.get("skyboxes", SAFE_EMPIRES_SKYBOXES) or SAFE_EMPIRES_SKYBOXES
            return skyboxes, themes

        default_mat = "common/nature/blend_grass_mountainwall_000"
        return [DEFAULT_SAFE_SKYBOX], {
            "General": {"defaults": {"primary_floor": default_mat}, "materials": [{"name": "Grass", "path": default_mat}]}
        }

    def _theme_default_floor(self, theme_name: str) -> Optional[str]:
        theme_obj = self.texture_themes.get(theme_name)
        if not isinstance(theme_obj, dict):
            return None
        defaults = theme_obj.get("defaults") or {}
        return defaults.get("primary_floor")

    def _material_entries_for_theme(self, theme_name: str) -> List[Tuple[str, str]]:
        from src.material_manager import is_blend_floor_material

        theme_obj = self.texture_themes.get(theme_name)
        if isinstance(theme_obj, dict):
            mats_list = theme_obj.get("materials", [])
        elif isinstance(theme_obj, list):
            mats_list = theme_obj
        else:
            mats_list = []
        labeled: List[Tuple[str, str]] = []
        for mat_entry in mats_list:
            mat = mat_entry["path"]
            if not is_blend_floor_material(mat):
                continue
            name = mat_entry.get("name") or Path(mat).name.replace("_", " ").title()
            labeled.append((name, mat))
        labeled.sort(key=lambda x: x[1].lower())
        return labeled

    def _fill_material_combo(self, theme_name: str, preserve_path: Optional[str] = None) -> None:
        self.combo_material.blockSignals(True)
        self.combo_material.clear()
        for display_text, clean_path in self._material_entries_for_theme(theme_name):
            self.combo_material.addItem(display_text, clean_path)
            idx = self.combo_material.count() - 1
            self.combo_material.setItemData(
                idx, f"{display_text}\n{clean_path}", Qt.ItemDataRole.ToolTipRole
            )
            if not self.is_texture_available(clean_path):
                self.combo_material.setItemData(idx, Qt.gray, Qt.ForegroundRole)
        self.combo_material.blockSignals(False)

        chosen_idx = -1
        if preserve_path:
            chosen_idx = self.combo_material.findData(preserve_path)
        if chosen_idx < 0:
            default_floor = self._theme_default_floor(theme_name)
            if default_floor:
                chosen_idx = self.combo_material.findData(default_floor)
        if chosen_idx >= 0:
            self.combo_material.setCurrentIndex(chosen_idx)
        self._refresh_ground_texture_tooltip()

    def _refresh_ground_texture_tooltip(self) -> None:
        idx = self.combo_material.currentIndex()
        if idx < 0:
            self.combo_material.setToolTip("")
            return
        path = self.combo_material.itemData(idx)
        name = self.combo_material.itemText(idx)
        if path:
            self.combo_material.setToolTip(f"{name}\n{path}")
        else:
            self.combo_material.setToolTip(name)

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
        sidebar.setMinimumWidth(218)
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

        self.on_auto_copy_changed()  # Trigger initial state setup

        sidebar_layout.addStretch()

        project_row = QHBoxLayout()
        project_row.setSpacing(6)

        self.btn_open_project = QPushButton("📂 Open")
        self.btn_open_project.setObjectName("SmallButton")
        self.btn_open_project.setMinimumHeight(34)
        self.btn_open_project.clicked.connect(self.on_open_project)
        project_row.addWidget(self.btn_open_project, 1)

        self.btn_save_project = QPushButton("💾 Save")
        self.btn_save_project.setObjectName("SmallButton")
        self.btn_save_project.setMinimumHeight(34)
        self.btn_save_project.clicked.connect(self.on_save_project)
        project_row.addWidget(self.btn_save_project, 1)

        sidebar_layout.addLayout(project_row)
        sidebar_layout.addSpacing(4)

        self.btn_compile = QPushButton("Compile VMT/BSP")
        self.btn_compile.setObjectName("CompileButton")
        self.btn_compile.setMinimumHeight(40)
        self.btn_compile.clicked.connect(self.compile_map_action)
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

        self.tab_widget = QTabWidget()
        config_layout.addWidget(self.tab_widget)

        self.tab_main = QScrollArea()
        self.tab_main.setWidgetResizable(True)
        self.tab_main.setFrameShape(QScrollArea.NoFrame)
        self.tab_main_content = QWidget()
        self.tab_main_layout = QVBoxLayout(self.tab_main_content)
        self.tab_main_layout.setAlignment(Qt.AlignTop)
        self.tab_main.setWidget(self.tab_main_content)

        self.tab_shape_content = QWidget()
        self.tab_shape_layout = QVBoxLayout(self.tab_shape_content)
        self.tab_shape_layout.setAlignment(Qt.AlignTop)

        self.tab_gameplay = QScrollArea()
        self.tab_gameplay.setWidgetResizable(True)
        self.tab_gameplay.setFrameShape(QScrollArea.NoFrame)
        self.tab_gameplay_content = QWidget()
        self.tab_gameplay_layout = QVBoxLayout(self.tab_gameplay_content)
        self.tab_gameplay_layout.setAlignment(Qt.AlignTop)
        self.tab_gameplay.setWidget(self.tab_gameplay_content)

        self.tab_widget.addTab(self.tab_main, "Main")
        self.tab_widget.addTab(self.tab_shape_content, "Shape")
        self.tab_widget.addTab(self.tab_gameplay, "Gameplay")

        # ─── GENERAL ───
        lbl_sec_general = QLabel("GENERAL")
        lbl_sec_general.setObjectName("ConfigSection")
        self.tab_main_layout.addWidget(lbl_sec_general)

        sec_general = QWidget()
        sec_general.content_layout = QVBoxLayout(sec_general)
        sec_general.content_layout.setContentsMargins(0,0,0,0)
        self.tab_main_layout.addWidget(sec_general)

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
        sec_general.content_layout.addLayout(name_row)

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
        sec_general.content_layout.addLayout(seed_row)
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
        sec_general.content_layout.addLayout(img_row)
        self.chk_custom_image.toggled.connect(self.toggle_custom_image)
        self.btn_browse.clicked.connect(self.browse_image)


        # ─── MAP DIMENSIONS ───
        lbl_sec_dimensions = QLabel("MAP DIMENSIONS")
        lbl_sec_dimensions.setObjectName("ConfigSection")
        self.tab_main_layout.addWidget(lbl_sec_dimensions)

        sec_dimensions = QWidget()
        sec_dimensions.content_layout = QVBoxLayout(sec_dimensions)
        sec_dimensions.content_layout.setContentsMargins(0,0,0,0)
        self.tab_main_layout.addWidget(sec_dimensions)

        dim_header = QHBoxLayout()
        dim_header.setSpacing(8)
        dim_header.addStretch()
        self.btn_size_help = QPushButton("Size Help")
        self.btn_size_help.setObjectName("SmallButton")
        self.btn_size_help.setToolTip(
            "Explain world-size and displacement limits for large maps"
        )
        self.btn_size_help.clicked.connect(self.show_map_size_help)
        dim_header.addWidget(self.btn_size_help)
        sec_dimensions.content_layout.addLayout(dim_header)

        dim_grid = QGridLayout()
        dim_grid.setSpacing(6)
        dim_grid.setColumnStretch(1, 1)
        dim_grid.setColumnStretch(3, 1)

        lbl_tx = QLabel("Tiles X")
        lbl_tx.setObjectName("FieldLabel")
        lbl_tx.setToolTip("Number of displacement tiles horizontally")
        dim_grid.addWidget(lbl_tx, 0, 0)
        self.spin_tiles_x = QSpinBox()
        self.spin_tiles_x.setRange(1, 64)
        dim_grid.addWidget(self.spin_tiles_x, 0, 1)

        lbl_ty = QLabel("Tiles Y")
        lbl_ty.setObjectName("FieldLabel")
        lbl_ty.setToolTip("Number of displacement tiles vertically")
        dim_grid.addWidget(lbl_ty, 0, 2)
        self.spin_tiles_y = QSpinBox()
        self.spin_tiles_y.setRange(1, 64)
        dim_grid.addWidget(self.spin_tiles_y, 0, 3)

        lbl_ts = QLabel("Tile Size")
        lbl_ts.setObjectName("FieldLabel")
        lbl_ts.setToolTip("World units per displacement tile edge")
        dim_grid.addWidget(lbl_ts, 1, 0)
        self.spin_tile_size = QSpinBox()
        self.spin_tile_size.setRange(128, 2048)
        self.spin_tile_size.setSingleStep(64)
        dim_grid.addWidget(self.spin_tile_size, 1, 1)

        lbl_hs = QLabel("Height")
        lbl_hs.setObjectName("FieldLabel")
        lbl_hs.setToolTip("Maximum terrain height in world units")
        dim_grid.addWidget(lbl_hs, 1, 2)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(1, 999999)
        lbl_skybox = QLabel("Skybox Ceil")
        lbl_skybox.setObjectName("FieldLabel")
        lbl_skybox.setToolTip("Skybox ceiling height above ground")
        dim_grid.addWidget(lbl_skybox, 2, 2)
        self.spin_skybox_ceiling = QSpinBox()
        self.spin_skybox_ceiling.setRange(1, 999999)
        dim_grid.addWidget(self.spin_skybox_ceiling, 2, 3)

        dim_grid.addWidget(self.spin_height, 1, 3)

        lbl_pw = QLabel("Detail")
        lbl_pw.setObjectName("FieldLabel")
        lbl_pw.setToolTip("Displacement power — vertices per tile edge")
        dim_grid.addWidget(lbl_pw, 2, 0)
        self.combo_power = QComboBox()
        self.combo_power.addItems(["2 (5×5)", "3 (9×9)", "4 (17×17)"])
        dim_grid.addWidget(self.combo_power, 2, 1)

        sec_dimensions.content_layout.addLayout(dim_grid)

        size_auto_row = QHBoxLayout()
        size_auto_row.setSpacing(8)
        lbl_target_size = QLabel("Target Size")
        lbl_target_size.setObjectName("FieldLabel")
        lbl_target_size.setToolTip(
            "Desired max map dimension in world units. "
            "Auto Tile Size uses this plus current tile counts."
        )
        size_auto_row.addWidget(lbl_target_size)
        self.spin_target_map_size = QSpinBox()
        self.spin_target_map_size.setRange(512, MAX_MAP_WORLD_SIZE)
        self.spin_target_map_size.setSingleStep(64)
        size_auto_row.addWidget(self.spin_target_map_size, 1)
        self.btn_auto_tile_size = QPushButton("Auto Tile Size")
        self.btn_auto_tile_size.setObjectName("SmallButton")
        self.btn_auto_tile_size.setToolTip(
            "Compute tile size from target map size and current Tiles X/Y"
        )
        self.btn_auto_tile_size.clicked.connect(self.auto_compute_tile_size_from_target)
        size_auto_row.addWidget(self.btn_auto_tile_size)
        sec_dimensions.content_layout.addLayout(size_auto_row)

        # Live map-size info label
        self.lbl_map_info = QLabel()
        self.lbl_map_info.setObjectName("HintLabel")
        sec_dimensions.content_layout.addWidget(self.lbl_map_info)

        self.spin_tiles_x.valueChanged.connect(self.sync_to_model)
        self.spin_tiles_y.valueChanged.connect(self.sync_to_model)
        self.spin_tile_size.valueChanged.connect(self.sync_to_model)
        self.spin_height.valueChanged.connect(self.sync_to_model)
        self.spin_skybox_ceiling.valueChanged.connect(self.sync_to_model)
        self.combo_power.currentIndexChanged.connect(self.sync_to_model)

        # ─── TERRAIN SHAPE ───
        lbl_sec_terrain_shape = QLabel("TERRAIN SHAPE")
        lbl_sec_terrain_shape.setObjectName("ConfigSection")
        self.tab_shape_layout.addWidget(lbl_sec_terrain_shape)

        sec_terrain_shape = QWidget()
        sec_terrain_shape.content_layout = QVBoxLayout(sec_terrain_shape)
        sec_terrain_shape.content_layout.setContentsMargins(0,0,0,0)
        self.tab_shape_layout.addWidget(sec_terrain_shape)

        # Topology
        topo_row = QHBoxLayout()
        topo_row.setSpacing(8)
        lbl_topo = QLabel("Topology")
        lbl_topo.setObjectName("FieldLabel")
        lbl_topo.setToolTip("Select the fundamental layout structure")
        topo_row.addWidget(lbl_topo)
        self.combo_topology = QComboBox()
        self.combo_topology.addItems(
            [
                "Canyon Maze",
            ]
        )
        self.combo_topology.setCurrentIndex(0)
        topo_row.addWidget(self.combo_topology, 1)
        sec_terrain_shape.content_layout.addLayout(topo_row)

        # Lane Node Radius
        lnr_row = QHBoxLayout()
        lnr_row.setSpacing(8)
        lbl_lnr = QLabel("Lane Node Radius")
        lbl_lnr.setObjectName("FieldLabel")
        lbl_lnr.setToolTip(
            "Radius of strategic lane nodes (separate from terrain flattening)"
        )
        lnr_row.addWidget(lbl_lnr)
        self.slider_lane_node_radius = QSlider(Qt.Horizontal)
        self.slider_lane_node_radius.setRange(0, 4096)
        self.slider_lane_node_radius.setValue(512)
        self.lbl_lane_node_radius_val = QLabel("512")
        lnr_row.addWidget(
            make_slider_row(
                self.slider_lane_node_radius, self.lbl_lane_node_radius_val
            ),
            1,
        )
        sec_terrain_shape.content_layout.addLayout(lnr_row)

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
        sec_terrain_shape.content_layout.addLayout(lw_row)

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
        self.slider_mountain_height.setRange(0, 800)
        self.slider_mountain_height.setValue(100)
        self.lbl_mountain_height_val = QLabel("100%")
        mh_row.addWidget(
            make_slider_row(
                self.slider_mountain_height, self.lbl_mountain_height_val, "%"
            ),
            1,
        )
        sec_terrain_shape.content_layout.addLayout(mh_row)

        # Canyon Depth (previously canyon_threshold)
        cd_row = QHBoxLayout()
        cd_row.setSpacing(8)
        lbl_cd = QLabel("Canyon Depth")
        lbl_cd.setObjectName("FieldLabel")
        lbl_cd.setToolTip("How deep the canyon floor is relative to the mountains. High = deep trench, Low = shallow.")
        cd_row.addWidget(lbl_cd)
        self.slider_canyon_depth = QSlider(Qt.Horizontal)
        self.slider_canyon_depth.setRange(1, 100)
        self.slider_canyon_depth.setValue(72)
        self.lbl_canyon_depth_val = QLabel("72%")
        cd_row.addWidget(
            make_slider_row(
                self.slider_canyon_depth, self.lbl_canyon_depth_val, "%"
            ),
            1,
        )
        sec_terrain_shape.content_layout.addLayout(cd_row)

        # Wall Steepness (previously plateau gap / plateau_threshold)
        cs_row = QHBoxLayout()
        cs_row.setSpacing(8)
        lbl_cs = QLabel("Wall Steepness")
        lbl_cs.setObjectName("FieldLabel")
        lbl_cs.setToolTip("How steep the canyon walls are. High = sharp cliff, Low = smooth valley.")
        cs_row.addWidget(lbl_cs)
        self.slider_canyon_steepness = QSlider(Qt.Horizontal)
        self.slider_canyon_steepness.setRange(1, 100)
        self.slider_canyon_steepness.setValue(94)  # Maps to a slope of ~0.06
        self.lbl_canyon_steepness_val = QLabel("94%")
        cs_row.addWidget(
            make_slider_row(
                self.slider_canyon_steepness, self.lbl_canyon_steepness_val, "%"
            ),
            1,
        )
        sec_terrain_shape.content_layout.addLayout(cs_row)

        # Lane Elevation
        le_row = QHBoxLayout()
        le_row.setSpacing(8)
        lbl_le = QLabel("Lane Elevation")
        lbl_le.setObjectName("FieldLabel")
        lbl_le.setToolTip(
            "Base height of the lanes as a percentage of max terrain height."
        )
        le_row.addWidget(lbl_le)
        self.slider_lane_elevation = QSlider(Qt.Horizontal)
        self.slider_lane_elevation.setRange(0, 100)
        self.slider_lane_elevation.setValue(15)
        self.lbl_lane_elevation_val = QLabel("15%")
        le_row.addWidget(
            make_slider_row(
                self.slider_lane_elevation, self.lbl_lane_elevation_val, "%"
            ),
            1,
        )
        sec_terrain_shape.content_layout.addLayout(le_row)

        # Feature Scale
        fs_row = QHBoxLayout()
        fs_row.setSpacing(8)
        lbl_fs = QLabel("Feature Scale")
        lbl_fs.setObjectName("FieldLabel")
        lbl_fs.setToolTip(
            "How large/wide the canyon structures generate (100% = default)"
        )
        fs_row.addWidget(lbl_fs)
        self.slider_feature_scale = QSlider(Qt.Horizontal)
        self.slider_feature_scale.setRange(10, 5000)
        self.slider_feature_scale.setValue(180)  # 1.8 * 100
        self.lbl_feature_scale_val = QLabel("180%")
        fs_row.addWidget(
            make_slider_row(self.slider_feature_scale, self.lbl_feature_scale_val, "%"),
            1,
        )
        sec_terrain_shape.content_layout.addLayout(fs_row)

        # Warp Strength
        warp_row = QHBoxLayout()
        warp_row.setSpacing(8)
        lbl_w = QLabel("Wall Warping")
        lbl_w.setObjectName("FieldLabel")
        lbl_w.setToolTip("Low = straight canyons, High = twisty, organic canyon walls")
        warp_row.addWidget(lbl_w)
        self.slider_warp = QSlider(Qt.Horizontal)
        self.slider_warp.setRange(0, 100) # maps to 0.0 to 1.0
        self.lbl_warp_val = QLabel("100%")
        warp_row.addWidget(make_slider_row(self.slider_warp, self.lbl_warp_val, "%"), 1)
        sec_terrain_shape.content_layout.addLayout(warp_row)

        # Roughness
        rough_row = QHBoxLayout()
        rough_row.setSpacing(8)
        lbl_r = QLabel("Roughness")
        lbl_r.setObjectName("FieldLabel")
        lbl_r.setToolTip("Terrain surface roughness")
        rough_row.addWidget(lbl_r)
        self.slider_rough = QSlider(Qt.Horizontal)
        self.slider_rough.setRange(0, 100)
        self.lbl_rough_val = QLabel("50%")
        rough_row.addWidget(make_slider_row(self.slider_rough, self.lbl_rough_val, "%"), 1)
        sec_terrain_shape.content_layout.addLayout(rough_row)

        # Plateau Noise
        pn_row = QHBoxLayout()
        pn_row.setSpacing(8)
        lbl_pn = QLabel("Plateau Noise")
        lbl_pn.setObjectName("FieldLabel")
        lbl_pn.setToolTip("FBM noise amplitude on plateaus")
        pn_row.addWidget(lbl_pn)
        self.slider_plateau_noise = QSlider(Qt.Horizontal)
        self.slider_plateau_noise.setRange(0, 100) # maps to 0.0 to 1.0
        self.lbl_plateau_noise_val = QLabel("12%")
        pn_row.addWidget(make_slider_row(self.slider_plateau_noise, self.lbl_plateau_noise_val, "%"), 1)
        sec_terrain_shape.content_layout.addLayout(pn_row)

        # Erosion
        eros_row = QHBoxLayout()
        eros_row.setSpacing(8)
        lbl_e = QLabel("Edge Smoothing")
        lbl_e.setObjectName("FieldLabel")
        lbl_e.setToolTip(
            "Blur radius to soften canyon steps — High = Source-like rolling drops"
        )
        eros_row.addWidget(lbl_e)
        self.slider_erosion = QSlider(Qt.Horizontal)
        self.slider_erosion.setRange(0, 100)
        self.lbl_erosion_val = QLabel("0%")
        eros_row.addWidget(
            make_slider_row(self.slider_erosion, self.lbl_erosion_val, "%"), 1
        )
        sec_terrain_shape.content_layout.addLayout(eros_row)

        # ─── MAZE SETTINGS ───
        self.lbl_sec_maze_settings = QLabel("MAZE SETTINGS")
        self.lbl_sec_maze_settings.setObjectName("ConfigSection")
        self.tab_shape_layout.addWidget(self.lbl_sec_maze_settings)

        self.sec_maze_settings = QWidget()
        self.sec_maze_settings.content_layout = QVBoxLayout(self.sec_maze_settings)
        self.sec_maze_settings.content_layout.setContentsMargins(0,0,0,0)
        self.tab_shape_layout.addWidget(self.sec_maze_settings)

        # Maze Size
        ms_row = QHBoxLayout()
        ms_row.setSpacing(8)
        lbl_ms = QLabel("Maze Size")
        lbl_ms.setObjectName("FieldLabel")
        lbl_ms.setToolTip("Scale for the bounding box the maze generates within (10% to 90%)")
        ms_row.addWidget(lbl_ms)
        self.slider_maze_size = QSlider(Qt.Horizontal)
        self.slider_maze_size.setRange(10, 100)
        self.slider_maze_size.setValue(90)
        self.lbl_maze_size_val = QLabel("90%")
        ms_row.addWidget(make_slider_row(self.slider_maze_size, self.lbl_maze_size_val, "%"), 1)
        self.sec_maze_settings.content_layout.addLayout(ms_row)

        # Lane Numbers (Density)
        ln_row = QHBoxLayout()
        ln_row.setSpacing(8)
        lbl_ln = QLabel("Lane Numbers")
        lbl_ln.setObjectName("FieldLabel")
        lbl_ln.setToolTip("Grid density of the maze pathways (2 to 10)")
        ln_row.addWidget(lbl_ln)
        self.slider_lane_numbers = QSlider(Qt.Horizontal)
        self.slider_lane_numbers.setRange(2, 10)
        self.slider_lane_numbers.setValue(6)
        self.lbl_lane_numbers_val = QLabel("6")
        ln_row.addWidget(make_slider_row(self.slider_lane_numbers, self.lbl_lane_numbers_val), 1)
        self.sec_maze_settings.content_layout.addLayout(ln_row)

        # Connect slider value displays
        self.slider_lane_width.valueChanged.connect(
            lambda v: self.lbl_lane_width_val.setText(f"{v}%")
        )
        self.slider_mountain_height.valueChanged.connect(
            lambda v: self.lbl_mountain_height_val.setText(f"{v}%")
        )
        self.slider_canyon_steepness.valueChanged.connect(lambda v: self.lbl_canyon_steepness_val.setText(f"{v}%"))
        self.slider_canyon_depth.valueChanged.connect(lambda v: self.lbl_canyon_depth_val.setText(f"{v}%"))
        self.slider_lane_elevation.valueChanged.connect(
            lambda v: self.lbl_lane_elevation_val.setText(f"{v}%")
        )
        self.slider_warp.valueChanged.connect(lambda v: self.lbl_warp_val.setText(f"{v}%"))
        self.slider_rough.valueChanged.connect(lambda v: self.lbl_rough_val.setText(f"{v}%"))
        self.slider_plateau_noise.valueChanged.connect(lambda v: self.lbl_plateau_noise_val.setText(f"{v}%"))
        self.slider_erosion.valueChanged.connect(
            lambda v: self.lbl_erosion_val.setText(f"{v}%")
        )
        self.slider_feature_scale.valueChanged.connect(
            lambda v: self.lbl_feature_scale_val.setText(f"{v}%")
        )
        self.slider_lane_node_radius.valueChanged.connect(
            lambda v: self.lbl_lane_node_radius_val.setText(str(v))
        )
        self.slider_maze_size.valueChanged.connect(lambda v: self.lbl_maze_size_val.setText(f"{v}%"))
        self.slider_lane_numbers.valueChanged.connect(lambda v: self.lbl_lane_numbers_val.setText(str(v)))

        self.combo_topology.currentIndexChanged.connect(self.sync_to_model)
        self.combo_topology.currentIndexChanged.connect(self._update_maze_visibility)
        self.slider_lane_width.valueChanged.connect(self.sync_to_model)
        self.slider_mountain_height.valueChanged.connect(self.sync_to_model)
        self.slider_canyon_steepness.valueChanged.connect(self.sync_to_model)
        self.slider_canyon_depth.valueChanged.connect(self.sync_to_model)
        self.slider_lane_elevation.valueChanged.connect(self.sync_to_model)
        self.slider_warp.valueChanged.connect(self.sync_to_model)
        self.slider_rough.valueChanged.connect(self.sync_to_model)
        self.slider_plateau_noise.valueChanged.connect(self.sync_to_model)
        self.slider_erosion.valueChanged.connect(self.sync_to_model)
        self.slider_feature_scale.valueChanged.connect(self.sync_to_model)
        self.slider_lane_node_radius.valueChanged.connect(self.sync_to_model)
        self.slider_maze_size.valueChanged.connect(self.sync_to_model)
        self.slider_lane_numbers.valueChanged.connect(self.sync_to_model)


        # ─── BASE AREAS ───
        lbl_sec_base_areas = QLabel("BASE AREAS")
        lbl_sec_base_areas.setObjectName("ConfigSection")
        self.tab_gameplay_layout.addWidget(lbl_sec_base_areas)

        sec_base_areas = QWidget()
        sec_base_areas.content_layout = QVBoxLayout(sec_base_areas)
        sec_base_areas.content_layout.setContentsMargins(0,0,0,0)
        self.tab_gameplay_layout.addWidget(sec_base_areas)

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
        sec_base_areas.content_layout.addLayout(br_row)

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
        sec_base_areas.content_layout.addLayout(bf_row)

        # Resource Node Clear Radius
        res_row = QHBoxLayout()
        res_row.setSpacing(8)
        lbl_res = QLabel("Resource Clear")
        lbl_res.setObjectName("FieldLabel")
        lbl_res.setToolTip("Radius of flat area around resource nodes (0 = disabled)")
        res_row.addWidget(lbl_res)
        self.slider_resource_clear = QSlider(Qt.Horizontal)
        self.slider_resource_clear.setRange(0, 4096)
        self.lbl_resource_clear_val = QLabel("0")
        res_row.addWidget(
            make_slider_row(self.slider_resource_clear, self.lbl_resource_clear_val), 1
        )
        sec_base_areas.content_layout.addLayout(res_row)

        self.slider_base_radius.valueChanged.connect(
            lambda v: self.lbl_base_radius_val.setText(str(v))
        )
        self.slider_base_flatness.valueChanged.connect(
            lambda v: self.lbl_base_flat_val.setText(f"{v}%")
        )
        self.slider_base_radius.valueChanged.connect(self.sync_to_model)
        self.slider_base_flatness.valueChanged.connect(self.sync_to_model)
        self.slider_resource_clear.valueChanged.connect(
            lambda v: self.lbl_resource_clear_val.setText(str(v))
        )
        self.slider_resource_clear.valueChanged.connect(self.sync_to_model)
        self.slider_base_radius.valueChanged.connect(self.update_node_clear_radii)
        self.slider_resource_clear.valueChanged.connect(self.update_node_clear_radii)


        # ─── MATERIALS & THEME ───
        lbl_sec_materials = QLabel("MATERIALS & THEME")
        lbl_sec_materials.setObjectName("ConfigSection")
        self.tab_shape_layout.addWidget(lbl_sec_materials)

        materials_card = QFrame()
        materials_card.setObjectName("MaterialsCard")
        card_layout = QVBoxLayout(materials_card)
        card_layout.setContentsMargins(9, 9, 9, 9)
        card_layout.setSpacing(6)

        cap_look = QLabel("Terrain appearance")
        cap_look.setObjectName("MaterialsCardCaption")
        card_layout.addWidget(cap_look)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(6)
        lbl_theme = QLabel("Theme")
        lbl_theme.setObjectName("MaterialsFieldLabel")
        lbl_theme.setToolTip(
            "Skybox default, texture scale rules, and which materials appear in the list"
        )
        theme_row.addWidget(lbl_theme)
        self.combo_theme = QComboBox()
        self.combo_theme.setObjectName("ThemeCombo")
        self.combo_theme.addItems(sorted(self.texture_themes.keys()))
        if self.config_model.current_theme in self.texture_themes:
            self.combo_theme.setCurrentText(self.config_model.current_theme)
        theme_row.addWidget(self.combo_theme, 1)
        card_layout.addLayout(theme_row)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_changed_sync)

        mat_row = QHBoxLayout()
        mat_row.setSpacing(6)
        lbl_mat = QLabel("Ground texture")
        lbl_mat.setObjectName("MaterialsFieldLabel")
        lbl_mat.setToolTip(
            "Default displacement blend for this theme (same pool as Texture paint)"
        )
        mat_row.addWidget(lbl_mat)
        self.combo_material = WidePopupComboBox()
        self.combo_material.setObjectName("GroundTextureCombo")
        self.combo_material.setMaxVisibleItems(14)
        self.combo_material.setMinimumWidth(222)
        mat_row.addWidget(self.combo_material, 1)
        card_layout.addLayout(mat_row)
        self.combo_material.currentIndexChanged.connect(self.sync_to_model)
        self.combo_material.currentIndexChanged.connect(self._refresh_ground_texture_tooltip)

        sky_row = QHBoxLayout()
        sky_row.setSpacing(6)
        lbl_sky = QLabel("Skybox")
        lbl_sky.setObjectName("MaterialsFieldLabel")
        sky_row.addWidget(lbl_sky)
        self.combo_skybox = QComboBox()
        self.combo_skybox.setObjectName("SkyboxCombo")
        self.combo_skybox.addItems(self.skyboxes)
        self.combo_skybox.setCurrentText("empsky_overcast3yellow")
        sky_row.addWidget(self.combo_skybox, 1)
        card_layout.addLayout(sky_row)
        self.combo_skybox.currentIndexChanged.connect(self.sync_to_model)

        divider = QFrame()
        divider.setObjectName("MaterialsCardDivider")
        divider.setFixedHeight(1)
        card_layout.addWidget(divider)

        ts_row = QHBoxLayout()
        ts_row.setSpacing(6)
        self.chk_auto_texture_scale = QCheckBox("Auto-Scale by Theme")
        self.chk_auto_texture_scale.setChecked(True)
        self.chk_auto_texture_scale.setToolTip(
            "When checked, texture scale adapts to the active theme automatically"
        )
        ts_row.addWidget(self.chk_auto_texture_scale)
        self.slider_texture_scale = QSlider(Qt.Horizontal)
        self.slider_texture_scale.setRange(10, 200)
        self.slider_texture_scale.setEnabled(False)
        self.lbl_texture_scale_val = QLabel("Auto")
        ts_row.addWidget(self.slider_texture_scale, 1)
        ts_row.addWidget(self.lbl_texture_scale_val)
        card_layout.addLayout(ts_row)
        self.chk_auto_texture_scale.toggled.connect(self._on_auto_scale_toggled)
        self.slider_texture_scale.valueChanged.connect(
            lambda v: self.lbl_texture_scale_val.setText(f"{v / 100:.1f}")
        )
        self.slider_texture_scale.valueChanged.connect(self.sync_to_model)

        cdw_row = QHBoxLayout()
        cdw_row.setSpacing(6)
        lbl_cdw = QLabel("Detail Width")
        lbl_cdw.setObjectName("FieldLabel")
        lbl_cdw.setToolTip("How far from lanes to keep high-detail (props/alphas)")
        cdw_row.addWidget(lbl_cdw)
        self.slider_corridor_width = QSlider(Qt.Horizontal)
        self.slider_corridor_width.setRange(512, 8192)
        self.lbl_corridor_width_val = QLabel("2048")
        cdw_row.addWidget(
            make_slider_row(self.slider_corridor_width, self.lbl_corridor_width_val), 1
        )
        card_layout.addLayout(cdw_row)

        tw_row = QHBoxLayout()
        tw_row.setSpacing(6)
        lbl_tw = QLabel("Transition Width")
        lbl_tw.setObjectName("FieldLabel")
        lbl_tw.setToolTip("Width of the blended belt between Action and Scenery zones")
        tw_row.addWidget(lbl_tw)
        self.slider_transition_width = QSlider(Qt.Horizontal)
        self.slider_transition_width.setRange(0, 8192)
        self.lbl_transition_width_val = QLabel("1536")
        tw_row.addWidget(
            make_slider_row(self.slider_transition_width, self.lbl_transition_width_val), 1
        )
        card_layout.addLayout(tw_row)

        hpd_row = QHBoxLayout()
        hpd_row.setSpacing(6)
        lbl_hpd = QLabel("Scenery Props")
        lbl_hpd.setObjectName("FieldLabel")
        lbl_hpd.setToolTip("Density of large hero prop clusters in the background")
        hpd_row.addWidget(lbl_hpd)
        self.slider_hero_prop = QSlider(Qt.Horizontal)
        self.slider_hero_prop.setRange(0, 100)
        self.lbl_hero_prop_val = QLabel("50%")
        hpd_row.addWidget(
            make_slider_row(self.slider_hero_prop, self.lbl_hero_prop_val, "%"), 1
        )
        card_layout.addLayout(hpd_row)

        self.slider_corridor_width.valueChanged.connect(self.sync_to_model)
        self.slider_transition_width.valueChanged.connect(self.sync_to_model)
        self.slider_hero_prop.valueChanged.connect(self.sync_to_model)

        self._fill_material_combo(self.combo_theme.currentText())

        self.tab_shape_layout.addWidget(materials_card)
        # ─── SETTINGS ───
        lbl_sec_settings = QLabel("SETTINGS")
        lbl_sec_settings.setObjectName("ConfigSection")
        self.tab_gameplay_layout.addWidget(lbl_sec_settings)

        sec_settings = QWidget()
        sec_settings.content_layout = QVBoxLayout(sec_settings)
        sec_settings.content_layout.setContentsMargins(0,0,0,0)
        self.tab_gameplay_layout.addWidget(sec_settings)

        spawn_grid = QGridLayout()
        spawn_grid.setSpacing(4)

        self.chk_disable_commander = QCheckBox("No Commander")
        self.chk_disable_buildings = QCheckBox("No Buildings")
        self.chk_disable_resources = QCheckBox("No Resources")
        self.chk_disable_flags = QCheckBox("No Flags")
        self.chk_minimal_map = QCheckBox("Minimal (No Props)")
        self.chk_terrain_only = QCheckBox("Terrain Only")
        self.chk_smart_details = QCheckBox("Enable Smart Details")
        self.chk_smart_details.setToolTip("Recommended for large maps to avoid hitting detail prop limits.")
        self.chk_manual_terrain = QCheckBox("Manual terrain")
        self.chk_invert_lanes = QCheckBox("Invert Lanes (Raised)")
        self.chk_preview_pipeline = QCheckBox("Preview with pipeline")

        self.chk_disable_commander.toggled.connect(self.sync_to_model)
        self.chk_disable_buildings.toggled.connect(self.sync_to_model)
        self.chk_disable_resources.toggled.connect(self.sync_to_model)
        self.chk_disable_flags.toggled.connect(self.sync_to_model)
        self.chk_minimal_map.toggled.connect(self.sync_to_model)
        self.chk_terrain_only.toggled.connect(self.sync_to_model)
        self.chk_smart_details.toggled.connect(self.on_smart_details_changed)
        self.chk_manual_terrain.toggled.connect(self.on_manual_terrain_toggled)
        self.chk_invert_lanes.toggled.connect(self.sync_to_model)
        self.chk_preview_pipeline.toggled.connect(self.sync_to_model)

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
            self.chk_disable_flags.setEnabled(not disable_individual)
            if disable_individual:
                self.chk_disable_commander.setChecked(False)
                self.chk_disable_buildings.setChecked(False)
                self.chk_disable_resources.setChecked(False)
                self.chk_disable_flags.setChecked(False)

        self.chk_minimal_map.toggled.connect(update_spawn_checks)
        self.chk_terrain_only.toggled.connect(update_spawn_checks)

        spawn_grid.addWidget(self.chk_disable_commander, 0, 0)
        spawn_grid.addWidget(self.chk_disable_buildings, 0, 1)
        spawn_grid.addWidget(self.chk_disable_resources, 1, 0)
        spawn_grid.addWidget(self.chk_disable_flags, 1, 1)
        spawn_grid.addWidget(self.chk_minimal_map, 2, 0)
        spawn_grid.addWidget(self.chk_terrain_only, 2, 1)
        spawn_grid.addWidget(self.chk_smart_details, 3, 0, 1, 2)
        sec_settings.content_layout.addLayout(spawn_grid)

        preview_grid = QGridLayout()
        preview_grid.setSpacing(4)
        lbl_preview_opts = QLabel("Advanced Settings")
        lbl_preview_opts.setObjectName("FieldLabel")
        lbl_preview_opts.setToolTip("Control how the preview displays terrain")
        preview_grid.addWidget(lbl_preview_opts, 0, 0, 1, 2)
        preview_grid.addWidget(self.chk_manual_terrain, 1, 0, 1, 2)
        preview_grid.addWidget(self.chk_invert_lanes, 2, 0, 1, 2)
        preview_grid.addWidget(self.chk_preview_pipeline, 3, 0, 1, 2)
        sec_settings.content_layout.addLayout(preview_grid)

        # ─── VALIDATION ───
        self.lbl_validation = QLabel("✓  All checks passed")
        self.lbl_validation.setObjectName("ValidationLabel")
        self.lbl_validation.setWordWrap(True)
        config_layout.addWidget(self.lbl_validation)

        config_layout.addStretch()

        # Wrap in scroll area
        scroll_content = QWidget()
        scroll_content.setLayout(config_layout)

        scroll = scroll_content # The tabs themselves have scroll areas inside now
        scroll.setMinimumWidth(240)

        # ── Data & Tools Setup ──

        self.preview_widget = MapPreviewWidget()
        self.preview_widget.set_themes(self.texture_themes, self.config_model.current_theme)
        self.preview_widget.set_tile_paint_target(
            getattr(self.config_model, "custom_tile_paint_target", "floor")
        )
        self.preview_widget.setMinimumWidth(200)

        # Inner splitter: config scroll | tabs
        self._inner_splitter = QSplitter(Qt.Horizontal)
        self._inner_splitter.addWidget(scroll)
        self._inner_splitter.addWidget(self.preview_widget)
        self._inner_splitter.setStretchFactor(0, 0)
        self.preview_widget.layout_changed.connect(self.on_layout_changed)
        self.preview_widget.lanes_changed.connect(self.on_lanes_changed)
        self.preview_widget.base_moved.connect(self.on_base_moved)
        self.preview_widget.resource_moved.connect(self.on_resource_moved)
        self.preview_widget.resource_added.connect(self.on_resource_added)
        self._inner_splitter.setChildrenCollapsible(False)
        self._force_full_regen = True
        main_area_layout.addWidget(self._inner_splitter)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.run_preview)

        self._root_splitter.addWidget(sidebar)
        self._root_splitter.addWidget(main_area)
        self._root_splitter.setStretchFactor(0, 0)
        self._root_splitter.setStretchFactor(1, 1)
        self._root_splitter.setSizes([226, 924])

        self._update_maze_visibility()

    def _update_maze_visibility(self):
        """Show or hide maze settings depending on current topology."""
        if self.combo_topology.currentText() == "Canyon Maze":
            self.sec_maze_settings.setVisible(True)
            if hasattr(self, "lbl_sec_maze_settings"):
                self.lbl_sec_maze_settings.setVisible(True)
        else:
            self.sec_maze_settings.setVisible(False)
            if hasattr(self, "lbl_sec_maze_settings"):
                self.lbl_sec_maze_settings.setVisible(False)

    def validate_current_layout(self):
        """Validates layout and returns (invalid_entity_ids, error_messages)."""
        try:
            spec = self.config_model.make_spec()
            layout_result = spec.validate_layout()
            return layout_result.invalid_entities, layout_result.errors
        except Exception:
            return set(), []

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
        invalid_entities, _ = self.validate_current_layout()
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            [],
            invalid_entities=invalid_entities,
        )
        self.preview_timer.start(150)
        self._is_dirty = True

    def on_tool_changed(self, id):
        pass  # Tools are fully managed by preview_widget internally now

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

        invalid_entities, _ = self.validate_current_layout()
        # which creates a feedback loop with base_moved / layout_changed
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()
        self.preview_timer.start(150)
        self._is_dirty = True

    def on_resource_moved(self, index, x, y):
        if self.config_model.custom_resources and 0 <= index < len(
            self.config_model.custom_resources
        ):
            self.config_model.custom_resources[index] = (x, y)
        invalid_entities, _ = self.validate_current_layout()
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()
        # Resource positions do not affect the terrain heightmap itself,
        # so we don't necessarily need to re-run the pipeline on move,
        # but we can do it if desired.
        self.preview_timer.start(150)
        self._is_dirty = True

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
        invalid_entities, _ = self.validate_current_layout()
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()

        self.update_validation_status()
        self._is_dirty = True

    def on_lanes_changed(self):
        """Lane topology changed — re-run the preview so the canyon is carved
        along the new lane. The pipeline receives initial_heights so manual
        sculpts stored in _height_overlay are composited back on top after
        the run completes (handled in set_raw_heights / _rerender_heightmap).
        """
        self._is_dirty = True
        self._force_full_regen = False
        self.preview_timer.start(150)

    def on_resource_added(self, x, y):
        if self.config_model.custom_resources is None:
            self.config_model.custom_resources = []

        # Deduplicate: don't add if a resource already exists at this exact spot
        for rx, ry in self.config_model.custom_resources:
            if abs(rx - x) < 1.0 and abs(ry - y) < 1.0:
                return

        self.config_model.custom_resources.append((x, y))
        invalid_entities, _ = self.validate_current_layout()
        self.preview_widget.invalid_entities = invalid_entities
        self.preview_widget.redraw_fixed_entities()
        self.preview_timer.start(150)
        self._is_dirty = True

    def run_preview(self):
        if hasattr(self, "preview_worker") and self.preview_worker.isRunning():
            # If a preview is still generating, skip starting a new one
            # and reschedule another attempt shortly to prevent garbage
            # collection of a running QThread which causes PySide6 crashes.
            self.preview_timer.start(150)
            return

        try:
            self.config_model.vpk_index = list(self._vpk_index)
            nodes, connections, resources, _, global_mask, texture_overlay, texture_mapping, next_texture_id, tile_overlay = (
                self.preview_widget.get_layout_from_editor()
            )
            tile_paint_target = self.preview_widget.get_tile_paint_target()
            self.config_model.custom_tile_paint_target = tile_paint_target

            initial_heights = None
            if not self._force_full_regen and hasattr(self.preview_widget, "_base_heights"):
                initial_heights = self.preview_widget._base_heights

            self.preview_worker = PreviewWorker(
                self.config_model,
                custom_nodes=nodes if nodes else None,
                custom_connections=connections if connections else None,
                custom_resources=resources,
                global_selection_mask=global_mask,
                initial_heights=initial_heights,
                texture_overlay=texture_overlay,
                texture_mapping=texture_mapping,
                tile_overlay=tile_overlay,
                tile_paint_target=tile_paint_target,
            )
            self.preview_worker.finished.connect(self.on_preview_finished)
            self.preview_worker.start()
            # Reset flag after starting. Default to full regen for the next trigger unless specified.
            self._force_full_regen = True
        except Exception:
            import traceback

            traceback.print_exc()
            # If prep fails, unlock so we aren't permanently stuck
            pass

    def on_preview_finished(self, grid, spec):
        if getattr(sys, "frozen", False) and not grid:
            log_path = Path(sys.executable).parent / "preview_signal_received.log"
            with open(log_path, "w") as f:
                f.write("Signal received but grid is None.\n")

        if grid and spec:
            self.lbl_validation.setText("✓  Preview updated")
            self.lbl_validation.setStyleSheet(
                "color: #22c55e; font-size: 11px; "
                "background: #122218; border-radius: 6px; padding: 8px 10px;"
            )
            import numpy as np

            display_grid = grid
            if self.config_model.preview_with_pipeline:
                display_grid = apply_pipeline_for_preview(grid, spec)

            if hasattr(grid, 'pure_heights'):
                pure_heights = np.array(grid.pure_heights)
            else:
                pure_heights = np.array(grid.heights)

            heights = np.array(display_grid.heights)

            # Use original pure height range for consistent tone mapping
            # This prevents exposure flashing on erosion runs

            # Find the actual min ignoring the purely black empty edge areas (which are close to 0)
            valid_pure_heights = pure_heights[pure_heights > 0.1]
            if len(valid_pure_heights) > 0:
                min_h = float(valid_pure_heights.min())
            else:
                min_h = float(pure_heights.min())
            max_h = float(pure_heights.max())

            if max_h > min_h:
                normalized = (heights - min_h) / (max_h - min_h)
                # Clip to 0-1 to prevent wrap-around bugs if heights has lower/higher values after erosion
                normalized = np.clip(normalized, 0, 1)
            else:
                normalized = np.zeros_like(heights)

            img_data = (normalized * 255).astype(np.uint8)
            h, w = img_data.shape

            bytes_per_line = w
            self._current_preview_data = img_data
            qimg = QImage(
                self._current_preview_data.data,
                w,
                h,
                bytes_per_line,
                QImage.Format_Grayscale8,
            ).copy()

            self.preview_widget.set_map_image(
                qimg,
                spec.origin_x,
                spec.origin_y,
                spec.size_x,
                spec.size_y,
                spec.cell_size,
                spec.tiles_x,
                spec.tiles_y,
            )
            # Pass the mask from the grid to preserve it through preview updates
            grid_mask = (
                grid.global_selection_mask
                if hasattr(grid, "global_selection_mask")
                else None
            )
            # Pass the pure base heights so they can be reused cleanly for iterative previews
            self.preview_widget.set_raw_heights(pure_heights, mask=grid_mask)

            imp_pos = (
                self.config_model.custom_imp_base_x,
                self.config_model.custom_imp_base_y,
            )
            nf_pos = (
                self.config_model.custom_nf_base_x,
                self.config_model.custom_nf_base_y,
            )

            res = (
                self.config_model.custom_resources
                if self.config_model.custom_resources
                else []
            )
            invalid_entities, _ = self.validate_current_layout()
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

        /* ── QTabWidget ── */
        QTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        QTabBar::tab {{
            background: transparent;
            color: #888888;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 11px;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:hover {{
            color: #ffffff;
            background: #2a2a34;
        }}
        QTabBar::tab:selected {{
            color: #4a90e2;
            border-bottom: 2px solid #4a90e2;
            background: #1a2332;
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
        QWidget#MaterialsCard {{
            background-color: #161822;
            border: 1px solid #2a3045;
            border-radius: 7px;
        }}
        QLabel#MaterialsCardCaption {{
            font-size: 8px;
            font-weight: 700;
            color: #636b86;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            padding: 0 1px 2px 1px;
        }}
        QLabel#MaterialsFieldLabel {{
            font-size: 11px;
            font-weight: 600;
            color: {TEXT_SEC};
            min-width: 88px;
            max-width: 88px;
        }}
        QFrame#MaterialsCardDivider {{
            background-color: #2a3048;
            border: none;
            margin-top: 2px;
            margin-bottom: 2px;
        }}
        QComboBox#GroundTextureCombo, QComboBox#ThemeCombo, QComboBox#SkyboxCombo {{
            min-height: 24px;
            max-height: 26px;
            padding: 3px 8px;
            font-size: 11px;
        }}
        QComboBox#ThemeCombo {{
            font-weight: 600;
        }}
        QComboBox#GroundTextureCombo QAbstractItemView::item {{
            padding: 5px 10px;
            min-height: 20px;
            border-radius: 3px;
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

        /* ── Unified Toolbar Styles ── */

        /* Tab Container (Capsule) */
        QWidget#TabContainer {{
            background-color: #1f1f26;
            border: 1px solid #2a2a34;
            border-radius: 6px;
        }}

        /* Tabs */
        QPushButton#TabButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 5px;
            font-weight: 600;
            color: #888888;
            padding: 6px 12px;
            font-size: 11px;
            margin: 2px;
        }}
        QPushButton#TabButton:hover {{
            color: #ffffff;
            background-color: #2a2a34;
        }}
        QPushButton#TabButton:checked {{
            background-color: #1a3a5a;
            border: 1px solid #4a90e2;
            color: #4a90e2;
        }}

        /* Contextual Tools */
        QPushButton#ContextToolBtn, QPushButton#GlobalActionBtn, QPushButton#DangerActionBtn {{
            background-color: transparent;
            border: 1px solid transparent;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 10px;
            color: #aaaaaa;
        }}
        QPushButton#ContextToolBtn:hover, QPushButton#GlobalActionBtn:hover {{
            background-color: #2a2a34;
            border: 1px solid #444444;
            color: #ffffff;
        }}
        QPushButton#ContextToolBtn:checked {{
            background-color: #1a3a5a;
            border: 1px solid #4a90e2;
            color: #4a90e2;
        }}

        /* Danger Action */
        QPushButton#DangerActionBtn {{
            color: #ff6666;
        }}
        QPushButton#DangerActionBtn:hover {{
            background-color: #552222;
            border: 1px solid #ff4444;
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

    def on_smart_details_changed(self):
        """Save smart details setting to config."""
        enabled = self.chk_smart_details.isChecked()
        self.config.set("smart_details", enabled)
        self.config_model.use_smart_details = enabled

    def on_manual_terrain_toggled(self, checked):
        if checked and hasattr(self, "preview_widget"):
            self.preview_widget.clear_lanes()
        self.sync_to_model()

    def show_map_size_help(self):
        """Show compile-safe size guidance for current map settings."""
        tile_size = self.spin_tile_size.value()
        tiles_x = self.spin_tiles_x.value()
        tiles_y = self.spin_tiles_y.value()
        map_size_x = tiles_x * tile_size
        map_size_y = tiles_y * tile_size
        disp_count = tiles_x * tiles_y

        max_tiles_world = MAX_MAP_WORLD_SIZE // max(tile_size, 1)
        max_square_by_disp = int(MAX_MAP_DISPINFO**0.5)
        max_square_tiles = min(max_tiles_world, max_square_by_disp)
        max_y_for_current_x = MAX_MAP_DISPINFO // max(tiles_x, 1)

        is_valid, msg = self.config_model.validate()
        status = (
            "Current setup: OK" if is_valid else f"Current setup: Not valid ({msg})"
        )

        help_text = (
            "Map Size Guide\n\n"
            "Two limits matter:\n"
            f"1. Compile-safe world size: {MAX_MAP_WORLD_SIZE} x {MAX_MAP_WORLD_SIZE} units\n"
            f"2. Displacement count: max {MAX_MAP_DISPINFO} (Tiles X * Tiles Y)\n\n"
            f"Current values:\n"
            f"- Tile Size: {tile_size}\n"
            f"- Tiles: {tiles_x} x {tiles_y}\n"
            f"- World Size: {map_size_x} x {map_size_y}\n"
            f"- Displacements: {disp_count}/{MAX_MAP_DISPINFO}\n\n"
            f"For Tile Size {tile_size}, max tiles by world-size is {max_tiles_world} per axis.\n"
            f"For current Tiles X={tiles_x}, max Tiles Y by displacement limit is {max_y_for_current_x}.\n"
            f"Safe square recommendation for this Tile Size: up to {max_square_tiles} x {max_square_tiles}.\n\n"
            "Tips:\n"
            "- Larger world with fewer displacements: increase Tile Size.\n"
            "- More detail: increase Tiles (if limits allow).\n"
            "- If compile fails near limits, reduce one step.\n\n"
            f"{status}"
        )
        QMessageBox.information(self, "Map Size Help", help_text)

    def browse_custom_output(self):
        """Browse for custom output folder."""
        folder = QFileDialog.getExistingDirectory(self, "Select Custom Output Folder")
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

    def _on_theme_changed_sync(self, index):
        """Handle global theme changes: ground texture list, preview paint list, skybox default."""
        theme_name = self.combo_theme.currentText()
        self._fill_material_combo(theme_name)
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_material_theme(theme_name)

        textures_path = PROJECT_ROOT / "config" / "textures.json"
        if textures_path.exists():
            with open(textures_path, "r") as f:
                data = json.load(f)
                theme_data = data.get("themes", {}).get(theme_name, {})
                defaults = theme_data.get("defaults", {})
                new_sky = defaults.get("skybox")
                if new_sky:
                    self.combo_skybox.setCurrentText(new_sky)

        self.sync_to_model()

    def _on_auto_scale_toggled(self, checked: bool):
        """Enable/disable texture scale slider based on auto checkbox."""
        self.slider_texture_scale.setEnabled(not checked)
        if checked:
            self.lbl_texture_scale_val.setText("Auto")
        else:
            v = self.slider_texture_scale.value()
            self.lbl_texture_scale_val.setText(f"{v / 100:.1f}")
        self.sync_to_model()

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

        # Rebuild VPK index and update combo boxes
        self._vpk_index = self._build_vpk_index(text)
        self._refresh_material_combobox()

    def _refresh_material_combobox(self):
        theme_name = self.combo_theme.currentText()
        current_data = self.combo_material.currentData()
        self._fill_material_combo(theme_name, preserve_path=current_data)

    def sync_to_ui(self):
        """Updates UI components to match the config model."""
        with self._block_signals(
            self.spin_seed,
            self.spin_tiles_x,
            self.spin_tiles_y,
            self.spin_tile_size,
            self.spin_target_map_size,
            self.spin_height,
            self.spin_skybox_ceiling,
            self.combo_topology,
            self.slider_lane_width,
            self.slider_mountain_height,
            self.slider_canyon_steepness,
            self.slider_canyon_depth,
            self.slider_lane_elevation,
            self.slider_warp,
            self.slider_rough,
            self.slider_plateau_noise,
            self.slider_erosion,
            self.slider_feature_scale,
            self.slider_lane_node_radius,
            self.slider_maze_size,
            self.slider_lane_numbers,
            self.slider_base_radius,
            self.slider_base_flatness,
            self.combo_power,
            self.combo_material,
            self.combo_skybox,
            self.combo_theme,
            self.chk_disable_commander,
            self.chk_disable_buildings,
            self.chk_disable_resources,
            self.chk_disable_flags,
            self.chk_minimal_map,
            self.chk_terrain_only,
            self.chk_smart_details,
            self.slider_resource_clear,
            self.chk_manual_terrain,
            self.chk_invert_lanes,
            self.chk_preview_pipeline,
            self.chk_auto_texture_scale,
            self.slider_texture_scale,
        ):
            self.spin_seed.setValue(self.config_model.seed)
            self.spin_tiles_x.setValue(self.config_model.tiles_x)
            self.spin_tiles_y.setValue(self.config_model.tiles_y)
            self.spin_tile_size.setValue(self.config_model.cell_size)
            self.spin_target_map_size.setValue(
                max(self.config_model.map_size_x, self.config_model.map_size_y)
            )
            self.spin_height.setValue(self.config_model.height_scale)
            self.spin_skybox_ceiling.setValue(self.config_model.skybox_ceiling)
            # We currently only have Canyon Maze (index 0 -> "canyon")
            self.combo_topology.setCurrentIndex(0)
            self.slider_lane_node_radius.setValue(self.config_model.lane_node_radius)
            self.lbl_lane_node_radius_val.setText(
                str(self.config_model.lane_node_radius)
            )
            self.slider_lane_width.setValue(
                int(self.config_model.lane_width_scale * 100)
            )
            self.lbl_lane_width_val.setText(f"{int(self.config_model.lane_width_scale * 100)}%")
            self.slider_mountain_height.setValue(
                int(self.config_model.mountain_height_scale * 100)
            )
            self.lbl_mountain_height_val.setText(f"{int(self.config_model.mountain_height_scale * 100)}%")
            self.slider_canyon_depth.setValue(int(self.config_model.lane_depth * 100))
            self.lbl_canyon_depth_val.setText(f"{int(self.config_model.lane_depth * 100)}%")
            # Wall steepness: 100% means sheer cliff (wall_slope near 0), 1% means smooth valley (wall_slope near 0.5)
            # wall_slope = (1.0 - steepness_factor) * 0.5
            steepness_factor = 1.0 - (self.config_model.wall_slope / 0.5)
            self.slider_canyon_steepness.setValue(max(1, min(100, int(steepness_factor * 100))))
            self.lbl_canyon_steepness_val.setText(f"{max(1, min(100, int(steepness_factor * 100)))}%")
            self.slider_lane_elevation.setValue(int(min(1.0, self.config_model.lane_elevation) * 100))
            self.lbl_lane_elevation_val.setText(f"{int(min(1.0, self.config_model.lane_elevation) * 100)}%")
            self.slider_warp.setValue(int(self.config_model.warp_strength * 100))
            self.lbl_warp_val.setText(f"{int(self.config_model.warp_strength * 100)}%")
            self.slider_rough.setValue(int(self.config_model.roughness * 100))
            self.lbl_rough_val.setText(f"{int(self.config_model.roughness * 100)}%")
            self.slider_plateau_noise.setValue(int(self.config_model.plateau_noise * 100))
            self.lbl_plateau_noise_val.setText(f"{int(self.config_model.plateau_noise * 100)}%")
            
            # blur_radius 0.0 -> slider 0; 0.5-10.0 -> slider 1-100
            br = self.config_model.blur_radius
            if br <= 0.0:
                _ero_slider = 0
            elif br < 0.5:
                _ero_slider = 1
            else:
                _ero_slider = int(min(100, (br / 10.0) * 100))
            self.slider_erosion.setValue(_ero_slider)
            self.lbl_erosion_val.setText(f"{_ero_slider}%")

            self.slider_feature_scale.setValue(
                int(self.config_model.feature_scale * 100)
            )
            self.lbl_feature_scale_val.setText(f"{int(self.config_model.feature_scale * 100)}%")

            self.slider_maze_size.setValue(self.config_model.maze_size)
            self.lbl_maze_size_val.setText(f"{self.config_model.maze_size}%")
            self.slider_lane_numbers.setValue(self.config_model.lane_numbers)
            self.lbl_lane_numbers_val.setText(str(self.config_model.lane_numbers))

            self.slider_base_radius.setValue(self.config_model.base_clear_radius)
            self.slider_base_flatness.setValue(
                int(self.config_model.base_flatness * 100)
            )
            self.lbl_base_radius_val.setText(str(self.config_model.base_clear_radius))
            self.lbl_base_flat_val.setText(
                f"{int(self.config_model.base_flatness * 100)}%"
            )
            self.slider_resource_clear.setValue(self.config_model.resource_clear_radius)
            self.lbl_resource_clear_val.setText(
                str(self.config_model.resource_clear_radius)
            )

            p = self.config_model.displacement_power
            if p == 2:
                self.combo_power.setCurrentIndex(0)
            elif p == 3:
                self.combo_power.setCurrentIndex(1)

            self.combo_theme.setCurrentText(self.config_model.current_theme)
            self._fill_material_combo(
                self.config_model.current_theme,
                preserve_path=self.config_model.terrain_material,
            )
            self.combo_skybox.setCurrentText(self.config_model.skybox)

            self.chk_disable_commander.setChecked(self.config_model.disable_commander)
            self.chk_disable_buildings.setChecked(self.config_model.disable_buildings)
            self.chk_disable_resources.setChecked(
                self.config_model.disable_resource_nodes
            )
            self.chk_disable_flags.setChecked(self.config_model.disable_capture_points)
            self.chk_minimal_map.setChecked(self.config_model.minimal_map)
            self.chk_terrain_only.setChecked(self.config_model.terrain_only)
            self.chk_smart_details.setChecked(self.config_model.use_smart_details)
            self.chk_manual_terrain.setChecked(self.config_model.manual_terrain)
            self.chk_invert_lanes.setChecked(self.config_model.invert_lanes)
            self.chk_preview_pipeline.setChecked(
                self.config_model.preview_with_pipeline
            )
        
        self.chk_auto_texture_scale.setChecked(self.config_model.auto_texture_scale)
        self.slider_texture_scale.setEnabled(not self.config_model.auto_texture_scale)
        if self.config_model.auto_texture_scale or self.config_model.terrain_texture_scale is None:
            self.slider_texture_scale.setValue(100)  # 1.0 = neutral position
            self.lbl_texture_scale_val.setText("Auto")
        else:
            sv = int(self.config_model.terrain_texture_scale * 100)
            self.slider_texture_scale.setValue(sv)
            self.lbl_texture_scale_val.setText(f"{self.config_model.terrain_texture_scale:.1f}")
        self.slider_corridor_width.setValue(self.config_model.corridor_detail_width)
        self.lbl_corridor_width_val.setText(str(self.config_model.corridor_detail_width))
        self.slider_transition_width.setValue(self.config_model.transition_width)
        self.lbl_transition_width_val.setText(str(self.config_model.transition_width))
        self.slider_hero_prop.setValue(int(self.config_model.hero_prop_density * 100))
        self.lbl_hero_prop_val.setText(f"{int(self.config_model.hero_prop_density * 100)}%")
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_tile_paint_target(
                getattr(self.config_model, "custom_tile_paint_target", "floor")
            )
            self.preview_widget.set_material_theme(self.config_model.current_theme)

        if self.config_model.custom_image_path:
            self.chk_custom_image.setChecked(True)
            self.lbl_image_path.setText(Path(self.config_model.custom_image_path).name)
        else:
            self.chk_custom_image.setChecked(False)
            self.lbl_image_path.setText("None")

        self.update_validation_status()

        self._update_maze_visibility()

        # Sync clear radii to preview widget after UI update
        self.update_node_clear_radii()

    def sync_to_model(self):
        """Updates config model from UI components and validates."""
        self.config_model.seed = self.spin_seed.value()
        self.config_model.tiles_x = self.spin_tiles_x.value()
        self.config_model.tiles_y = self.spin_tiles_y.value()
        self.config_model.cell_size = self.spin_tile_size.value()
        self.config_model.height_scale = self.spin_height.value()
        self.config_model.skybox_ceiling = self.spin_skybox_ceiling.value()

        # We currently only have Canyon Maze (index 0 -> "canyon")
        self.config_model.topology = "canyon"
        self.config_model.canyon_natural = False
        self.config_model.lane_node_radius = self.slider_lane_node_radius.value()
        
        self.config_model.current_theme = self.combo_theme.currentText()
        self.config_model.auto_texture_scale = self.chk_auto_texture_scale.isChecked()
        if self.chk_auto_texture_scale.isChecked():
            self.config_model.terrain_texture_scale = None
        else:
            self.config_model.terrain_texture_scale = self.slider_texture_scale.value() / 100.0
        self.config_model.corridor_detail_width = self.slider_corridor_width.value()
        self.lbl_corridor_width_val.setText(str(self.config_model.corridor_detail_width))
        self.config_model.transition_width = self.slider_transition_width.value()
        self.lbl_transition_width_val.setText(str(self.config_model.transition_width))
        self.config_model.hero_prop_density = self.slider_hero_prop.value() / 100.0
        self.lbl_hero_prop_val.setText(f"{self.slider_hero_prop.value()}%")
        self.config_model.lane_width_scale = self.slider_lane_width.value() / 100.0
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_lane_scale(self.config_model.lane_width_scale)
            self.config_model.custom_tile_paint_target = (
                self.preview_widget.get_tile_paint_target()
            )
        self.config_model.mountain_height_scale = (
            self.slider_mountain_height.value() / 100.0
        )
        self.config_model.lane_depth = self.slider_canyon_depth.value() / 100.0
        # Wall steepness: 100% means sheer cliff (wall_slope near 0), 1% means smooth valley (wall_slope near 0.5)
        steepness_factor = self.slider_canyon_steepness.value() / 100.0
        self.config_model.wall_slope = max(0.001, (1.0 - steepness_factor) * 0.5)
        self.config_model.lane_elevation = self.slider_lane_elevation.value() / 100.0
        self.config_model.warp_strength = self.slider_warp.value() / 100.0
        self.config_model.roughness = self.slider_rough.value() / 100.0
        self.config_model.plateau_noise = self.slider_plateau_noise.value() / 100.0
        # Edge smoothing: 0 = off; 1-100 maps to 0.5-10.0 passes (immediately visible)
        _es = self.slider_erosion.value()
        if _es == 0:
            self.config_model.blur_radius = 0.0
        else:
            self.config_model.blur_radius = 0.5 + (_es - 1) / 99.0 * 9.5

        self.config_model.feature_scale = self.slider_feature_scale.value() / 100.0
        self.config_model.maze_size = self.slider_maze_size.value()
        self.config_model.lane_numbers = self.slider_lane_numbers.value()

        self.config_model.base_clear_radius = self.slider_base_radius.value()
        self.config_model.base_flatness = self.slider_base_flatness.value() / 100.0
        self.config_model.resource_clear_radius = self.slider_resource_clear.value()

        idx = self.combo_power.currentIndex()
        if idx == 0:
            self.config_model.displacement_power = 2
        elif idx == 1:
            self.config_model.displacement_power = 3

        self.config_model.terrain_material = self.combo_material.currentData()
        self.config_model.skybox = self.combo_skybox.currentText()

        self.config_model.disable_commander = self.chk_disable_commander.isChecked()
        self.config_model.disable_buildings = self.chk_disable_buildings.isChecked()
        self.config_model.disable_resource_nodes = (
            self.chk_disable_resources.isChecked()
        )
        self.config_model.disable_capture_points = self.chk_disable_flags.isChecked()
        self.config_model.minimal_map = self.chk_minimal_map.isChecked()
        self.config_model.terrain_only = self.chk_terrain_only.isChecked()
        self.config_model.use_smart_details = self.chk_smart_details.isChecked()
        self.config_model.manual_terrain = self.chk_manual_terrain.isChecked()
        self.config_model.invert_lanes = self.chk_invert_lanes.isChecked()
        self.config_model.preview_with_pipeline = self.chk_preview_pipeline.isChecked()

        self.update_validation_status()
        if hasattr(self, "preview_timer"):
            self._force_full_regen = True
            self.preview_timer.start(150)
        self._is_dirty = True

    def update_validation_status(self):
        is_valid, msg = self.config_model.validate()

        # Update map info line
        tx = self.spin_tiles_x.value()
        ty = self.spin_tiles_y.value()
        tile_size = self.spin_tile_size.value()
        w = tx * tile_size
        h = ty * tile_size
        disp_count = tx * ty
        self.lbl_map_info.setText(
            f"{w}×{h} units  ·  {tx}×{ty} tiles  ·  {disp_count}/{MAX_MAP_DISPINFO} disps"
        )

        if is_valid:
            # Check layout from editor
            if hasattr(self, "preview_widget"):
                try:
                    (
                        nodes,
                        _,
                        resources,
                        _,
                        _,
                        _,
                        _,
                        _,
                        _,
                    ) = self.preview_widget.get_layout_from_editor()
                    if nodes:
                        temp_spec = self.config_model.make_spec()

                        # Extract base and resource positions from editor nodes
                        imp_pos = next(
                            (
                                (n.x, n.y)
                                for n in nodes
                                if "imp" in n.type.lower()
                                or (n.type == "base_zone" and nodes.index(n) == 0)
                            ),
                            None,
                        )
                        nf_pos = next(
                            (
                                (n.x, n.y)
                                for n in nodes
                                if "nf" in n.type.lower()
                                or (n.type == "base_zone" and nodes.index(n) == 1)
                            ),
                            None,
                        )
                        res_positions = [
                            (n.x, n.y) for n in nodes if "resource" in n.type.lower()
                        ]

                        if imp_pos:
                            temp_spec.custom_imp_base_x, temp_spec.custom_imp_base_y = (
                                imp_pos
                            )
                        if nf_pos:
                            temp_spec.custom_nf_base_x, temp_spec.custom_nf_base_y = (
                                nf_pos
                            )
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
            self.btn_compile.setEnabled(True)
        else:
            self.lbl_validation.setText(f"✗  {msg}")
            self.lbl_validation.setStyleSheet(
                "color: #ef4444; font-size: 11px; "
                "background: #221212; border-radius: 6px; padding: 8px 10px;"
            )
            self.btn_compile.setEnabled(False)

    def update_node_clear_radii(self):
        """Update clear radii on all visual nodes in editor/preview."""
        base_r = self.slider_base_radius.value()
        res_r = self.slider_resource_clear.value()
        if hasattr(self, "preview_widget"):
            # Update stored radii so redraws use new values
            self.preview_widget.base_clear_radius = base_r
            self.preview_widget.resource_clear_radius = res_r
            self.preview_widget.update_clear_radii(base_r, res_r)

    def _quantize_tile_size(self, value: float) -> int:
        """Quantize tile size to compile-safe UI step and limits."""
        snapped = int(math.floor(value / 64.0) * 64)
        return max(128, min(2048, snapped))

    def _max_tile_size_for_tiles(self, tiles_x: int, tiles_y: int) -> int:
        """Maximum compile-safe tile size for current tile counts."""
        max_for_x = MAX_MAP_WORLD_SIZE // max(tiles_x, 1)
        max_for_y = MAX_MAP_WORLD_SIZE // max(tiles_y, 1)
        return max(128, min(2048, max_for_x, max_for_y))

    def auto_compute_tile_size_from_target(self):
        """Auto-calculate tile size and counts to reach target map size efficiently."""
        # Target size is bounded by MAX_MAP_WORLD_SIZE through the UI, but enforce it here too just in case.
        target_size = min(self.spin_target_map_size.value(), MAX_MAP_WORLD_SIZE)

        # We want to find the best tile_size (max 2048) and tiles_x/tiles_y
        # that gets as close to target_size as possible while keeping
        # displacement counts low (larger tile sizes are better).

        best_diff = float('inf')
        best_tile_size = 2048
        best_tiles = 1

        for tile_size in range(2048, 127, -64):
            # Calculate optimal tile count for this size.
            tiles = round(target_size / tile_size)

            # Bound the number of tiles to safe limits
            max_tiles_disp = int(MAX_MAP_DISPINFO**0.5)
            max_tiles_world = MAX_MAP_WORLD_SIZE // tile_size
            tiles = min(tiles, max_tiles_disp, max_tiles_world)
            tiles = max(1, tiles)

            actual_size = tiles * tile_size
            diff = abs(actual_size - target_size)

            # Prefer larger tile sizes when difference is the same or slightly worse
            # but strictly favor smaller differences.
            if diff < best_diff:
                best_diff = diff
                best_tile_size = tile_size
                best_tiles = tiles

        self.spin_tiles_x.setValue(best_tiles)
        self.spin_tiles_y.setValue(best_tiles)
        self.spin_tile_size.setValue(best_tile_size)

        actual_map_x = best_tiles * best_tile_size
        actual_map_y = best_tiles * best_tile_size
        QMessageBox.information(
            self,
            "Tile Size Calculated",
            (
                f"Target size: {target_size} units\n"
                f"Tiles: {best_tiles} x {best_tiles}\n"
                f"Computed tile size: {best_tile_size}\n"
                f"Actual map size: {actual_map_x} x {actual_map_y}"
            ),
        )

    def generate_map(self):
        if (
            hasattr(self, "worker")
            and getattr(self.worker, "isRunning", lambda: False)()
        ):
            self.worker.wait(1000)

        is_valid, msg = self.config_model.validate()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Configuration", msg)
            return

        spec = self.config_model.make_spec()
        layout_result = spec.validate_layout()
        if layout_result.errors:
            QMessageBox.warning(
                self,
                "Invalid Layout",
                "Cannot generate:\n" + "\n".join(layout_result.errors),
            )
            return

        self.btn_compile.setEnabled(False)
        self.btn_compile.setText("Generating...")

        # Copy the VPK index so it's available to the worker
        self.config_model.vpk_index = list(self._vpk_index)

        # Run generation in background
        map_name = self.txt_map_name.text().strip() or "gui_terrain"
        layout_nodes, layout_conns, layout_res, height_overlay, global_mask, texture_overlay, texture_mapping, next_texture_id, tile_overlay = (
            self.preview_widget.get_layout_from_editor()
        )
        tile_paint_target = self.preview_widget.get_tile_paint_target()
        self.config_model.custom_tile_paint_target = tile_paint_target

        initial_heights = None
        if hasattr(self.preview_widget, "_base_heights"):
            initial_heights = self.preview_widget._base_heights

        self.worker = GenerationWorker(
            self.config_model,
            custom_nodes=layout_nodes if layout_nodes else None,
            custom_connections=layout_conns if layout_conns else None,
            custom_resources=layout_res,
            output_filename=map_name,
            height_overlay=height_overlay,
            global_selection_mask=global_mask,
            initial_heights=initial_heights,
            texture_overlay=texture_overlay,
            texture_mapping=texture_mapping,
            tile_overlay=tile_overlay,
            tile_paint_target=tile_paint_target,
        )
        self.worker.finished.connect(self.on_generation_finished)

        if NUMBA_AVAILABLE and self._numba_first_run:
            self.statusBar().showMessage("First run: compiling erosion kernel, this may take 10-30 seconds...")
            self._numba_first_run = False

        self.worker.start()

    def on_save_project(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Terrain Project", "", "Terrain Project (*.terrain)"
        )
        if not file_path:
            return

        if not file_path.endswith(".terrain"):
            file_path += ".terrain"

        try:
            nodes, conns, res, overlay, mask, texture_overlay, texture_mapping, next_texture_id, tile_overlay = (
                self.preview_widget.get_layout_from_editor()
            )

            layout_data = {
                "nodes": nodes,
                "connections": conns,
                "resources": res,
                "imp_base": self.preview_widget.imp_base,
                "nf_base": self.preview_widget.nf_base,
                "height_overlay": overlay,
                "global_mask": mask,
                "texture_overlay": texture_overlay,
                "texture_mapping": texture_mapping,
                "next_texture_id": next_texture_id,
                "tile_overlay": tile_overlay,
                "tile_paint_target": self.preview_widget.get_tile_paint_target(),
                "map_name": self.txt_map_name.text().strip(),
            }

            project_utils.save_project(file_path, self.config_model, layout_data)
            self._is_dirty = False
            self.statusBar().showMessage(f"Project saved to {file_path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save project:\n{e}")

    def on_open_project(self):
        if self._is_dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before opening a new project?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Save:
                self.on_save_project()
                if self._is_dirty:  # If save was cancelled
                    return
            elif reply == QMessageBox.Cancel:
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Terrain Project", "", "Terrain Project (*.terrain)"
        )
        if not file_path:
            return

        try:
            data = project_utils.load_project(file_path)

            # Apply loaded state
            self.config_model = data["config"]
            self.txt_map_name.setText(data["map_name"])

            # Use sync_to_ui which already has signal blocking for widgets
            self.sync_to_ui()

            # Restore layout in editor
            self.preview_widget.set_layout_to_editor(
                data["nodes"],
                data["connections"],
                data["resources"],
                data["imp_base"],
                data["nf_base"],
                data["height_overlay"],
                data["global_mask"],
                data.get("texture_overlay"),
                data.get("texture_mapping"),
                data.get("next_texture_id", 1),
                data.get("tile_overlay"),
                data.get("tile_paint_target", getattr(self.config_model, "custom_tile_paint_target", "floor")),
            )

            self._is_dirty = False
            self.run_preview()
            self.statusBar().showMessage(f"Project loaded from {file_path}", 5000)

        except Exception as e:
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self, "Load Error", f"Could not load project:\n{e}")

    def on_generation_finished(self, success, msg, warning):
        self.btn_compile.setEnabled(True)
        self.btn_compile.setText("Compile VMT/BSP")

        if success:
            map_name = self.txt_map_name.text().strip() or "gui_terrain"
            project_root = getattr(self.worker, "project_root", None)
            if project_root:
                vmf_path = project_root / "mapsrc" / f"{map_name}.vmf"
                self._last_vmf_path = str(vmf_path)
                print(
                    f"DEBUG: VMF path set to: {self._last_vmf_path}, exists={vmf_path.exists()}"
                )
            else:
                print("DEBUG: project_root is None!")
                self._last_vmf_path = None

            self._last_custom_project_root = None

            # If auto-copy is false and custom folder is set, copy the whole project to the custom folder
            auto_copy = self.config.get("auto_copy_to_empires", True)
            custom_folder = self.config.get("custom_output_folder", "")
            if (
                not auto_copy
                and custom_folder
                and Path(custom_folder).exists()
                and project_root
            ):
                try:
                    import shutil

                    # Create a versioned path in the custom folder
                    custom_dest = get_versioned_path(Path(custom_folder), map_name)
                    shutil.copytree(project_root, custom_dest)
                    self._last_custom_project_root = str(custom_dest)

                    msg += f"\nFiles copied to {custom_dest}"
                except Exception as e:
                    msg += f"\nWarning: Failed to copy to custom folder: {e}"

            if warning:
                QMessageBox.warning(
                    self, "Generation Warning", f"{msg}\n\nWARNING:\n{warning}"
                )
            elif not getattr(self, "_wants_compile", False):
                QMessageBox.information(self, "Success", msg)

            # Optionally start compile step if user requested it
            if getattr(self, "_wants_compile", False):
                self._wants_compile = False # reset flag
                self.start_compile_process()
        else:
            QMessageBox.critical(self, "Generation Failed", msg)
            self._wants_compile = False

    def compile_map_action(self):
        # Ask user whether to just generate VMF, or generate and then compile
        reply = QMessageBox.question(
            self,
            "Compile VMT/BSP",
            "Do you want to run the full BSP compile process?\n\n"
            "Yes: Generates VMF and compiles to BSP/VMT.\n"
            "No: Generates VMF only.",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Cancel:
            return

        # Store user intent
        self._wants_compile = (reply == QMessageBox.Yes)

        # Start generation first
        self.generate_map()

    def start_compile_process(self):
        vmf_path = getattr(self, "_last_vmf_path", None)
        if not vmf_path or not Path(vmf_path).exists():
            QMessageBox.warning(
                self, "No VMF", "Map generation failed or missing, cannot compile."
            )
            return

        self.btn_compile.setEnabled(False)
        self.btn_compile.setText("Compiling...")

        empires_path = self.config.get("empires_path", "")
        auto_copy = self.config.get("auto_copy_to_empires", True)

        custom_folder = getattr(self, "_last_custom_project_root", None)
        if not custom_folder:
            custom_folder = self.config.get("custom_output_folder", "")

        self.compile_worker = CompileWorker(
            vmf_path, empires_path, auto_copy, custom_folder
        )
        self.compile_worker.finished.connect(self.on_compile_finished)
        self.compile_worker.start()

    def on_compile_finished(self, success, msg):
        self.btn_compile.setEnabled(True)
        self.btn_compile.setText("Compile VMT/BSP")

        if success:
            QMessageBox.information(self, "Compile Success", msg)
        else:
            QMessageBox.critical(self, "Compile Failed", msg)


class CompileWorker(QThread):
    finished = Signal(bool, str)

    def __init__(
        self,
        vmf_path,
        empires_path="",
        auto_copy=True,
        custom_folder="",
        nodetail=False,
    ):
        super().__init__()
        self.vmf_path = vmf_path
        self.empires_path = empires_path
        self.auto_copy = auto_copy
        self.custom_folder = custom_folder
        self.nodetail = nodetail

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
                        nodetail=self.nodetail,
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
                ]
                if self.nodetail:
                    cmd.append("--nodetail")
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
