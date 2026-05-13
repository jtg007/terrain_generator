import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QByteArray
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QImage,
    QPixmap,
    QVector3D,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QButtonGroup,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QLabel,
    QSlider,
    QSizePolicy,
    QComboBox,
    QStackedWidget,
)

from src.material_manager import is_blend_floor_material
from src.qt_widgets import WidePopupComboBox
from src.terrain_spec import ZoneType, LayoutNode, LayoutConnection


# Global SVG Renderers
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent.parent

ICONS_DIR = PROJECT_ROOT / "icons"


def _load_svg(path):
    with open(path, "rb") as f:
        data = f.read()
    return QSvgRenderer(QByteArray(data))


SVG_RENDERERS = {
    "imp": _load_svg(ICONS_DIR / "be base.svg"),
    "nf": _load_svg(ICONS_DIR / "nf base.svg"),
    "res": _load_svg(ICONS_DIR / "resource_node.svg"),
}

MODELS_DIR = PROJECT_ROOT / "models"
MESH_CACHE: Dict[str, Optional[Tuple[np.ndarray, np.ndarray]]] = {}


def load_obj_mesh(filepath: Path) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    cache_key = str(filepath)
    if cache_key in MESH_CACHE:
        return MESH_CACHE[cache_key]

    if not filepath.exists():
        MESH_CACHE[cache_key] = None
        return None

    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("v "):
                    parts = line.split()
                    if len(parts) >= 4:
                        vertices.append(
                            (float(parts[1]), float(parts[2]), float(parts[3]))
                        )
                    continue

                if not line.startswith("f "):
                    continue

                parts = line.split()[1:]
                if len(parts) < 3:
                    continue

                face_indices: List[int] = []
                for token in parts:
                    idx_token = token.split("/")[0]
                    if not idx_token:
                        continue

                    idx = int(idx_token)
                    if idx < 0:
                        idx = len(vertices) + idx
                    else:
                        idx -= 1
                    face_indices.append(idx)

                if len(face_indices) < 3:
                    continue

                for i in range(1, len(face_indices) - 1):
                    faces.append(
                        (face_indices[0], face_indices[i], face_indices[i + 1])
                    )
    except (OSError, ValueError):
        MESH_CACHE[cache_key] = None
        return None

    if not vertices or not faces:
        MESH_CACHE[cache_key] = None
        return None

    verts_arr = np.array(vertices, dtype=np.float32)
    faces_arr = np.array(faces, dtype=np.int32)

    if faces_arr.min() < 0 or faces_arr.max() >= len(verts_arr):
        MESH_CACHE[cache_key] = None
        return None

    MESH_CACHE[cache_key] = (verts_arr, faces_arr)
    return MESH_CACHE[cache_key]


class VisualFreehandEdge(QGraphicsItem):
    def __init__(self, points, width, start_node=None, end_node=None, parent=None):
        super().__init__(parent)
        self.points = points  # List of QPointF (in scene coords)
        self.base_points = [
            p for p in points
        ]  # Keep original points for offset calculation
        self.base_width = width
        self.start_node = start_node
        self.end_node = end_node
        self.setZValue(1)
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self._update_pen()

    def _update_pen(self):
        # Use the scale from the parent widget if possible
        scale = 1.0
        try:
            if self.scene() and self.scene().views():
                parent = self.scene().views()[0].parent()
                if hasattr(parent, "global_lane_scale"):
                    scale = parent.global_lane_scale
        except (AttributeError, IndexError):
            pass

        pen_w = max(4, (self.base_width * scale) / 25.0)
        self.pen = QPen(QColor(255, 255, 255, 90), pen_w)
        self.pen.setCapStyle(Qt.RoundCap)
        self.pen.setJoinStyle(Qt.RoundJoin)

        self.outline_pen = QPen(QColor(200, 200, 255, 120), 2)
        self.outline_pen.setCapStyle(Qt.RoundCap)
        self.outline_pen.setJoinStyle(Qt.RoundJoin)
        self.update()

    @property
    def logical_width(self):
        scale = 1.0
        if (
            self.scene()
            and self.scene().views()
            and isinstance(self.scene().views()[0].parent(), MapPreviewWidget)
        ):
            scale = self.scene().views()[0].parent().global_lane_scale
        return self.base_width * scale

    def update_position(self):
        if not self.points or len(self.points) < 2:
            return
        self.prepareGeometryChange()

        # If both ends are attached, interpolate the stretch. If one, translate.
        if self.start_node and self.end_node:
            start_pos = self.start_node.scenePos()
            end_pos = self.end_node.scenePos()
            orig_start = self.base_points[0]
            orig_end = self.base_points[-1]

            dx = end_pos.x() - start_pos.x()
            dy = end_pos.y() - start_pos.y()
            orig_dx = orig_end.x() - orig_start.x()
            orig_dy = orig_end.y() - orig_start.y()

            new_points = []
            for i, bp in enumerate(self.base_points):
                if i == 0:
                    new_points.append(start_pos)
                elif i == len(self.base_points) - 1:
                    new_points.append(end_pos)
                else:
                    # Very simple linear interpolation of movement
                    if abs(orig_dx) > 0 or abs(orig_dy) > 0:
                        t = i / (len(self.base_points) - 1)
                        new_x = (
                            start_pos.x()
                            + t * dx
                            + (bp.x() - (orig_start.x() + t * orig_dx))
                        )
                        new_y = (
                            start_pos.y()
                            + t * dy
                            + (bp.y() - (orig_start.y() + t * orig_dy))
                        )
                        new_points.append(QPointF(new_x, new_y))
                    else:
                        new_points.append(bp)
            self.points = new_points
        elif self.start_node:
            start_pos = self.start_node.scenePos()
            dx = start_pos.x() - self.base_points[0].x()
            dy = start_pos.y() - self.base_points[0].y()
            self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.base_points]
        elif self.end_node:
            end_pos = self.end_node.scenePos()
            dx = end_pos.x() - self.base_points[-1].x()
            dy = end_pos.y() - self.base_points[-1].y()
            self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.base_points]

        self.update()

    def boundingRect(self):
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        margin = self.pen.width()
        return QRectF(
            min(xs) - margin,
            min(ys) - margin,
            max(xs) - min(xs) + 2 * margin,
            max(ys) - min(ys) + 2 * margin,
        )

    def paint(self, painter, option, widget):
        if len(self.points) < 2:
            return

        from PySide6.QtGui import QPainterPath

        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)

        # Draw translucent thick body
        painter.setPen(self.pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Draw thin crisp outline
        painter.setPen(self.outline_pen)
        painter.drawPath(path)


class VisualEdge(QGraphicsLineItem):
    def __init__(self, start_node, end_node, parent=None):
        super().__init__(parent)
        self.start_node = start_node
        self.end_node = end_node
        self.base_width = 600.0
        self.setZValue(1)
        self._update_pen()
        self.update_position()

    def _update_pen(self):
        scale = 1.0
        try:
            if self.scene() and self.scene().views():
                parent = self.scene().views()[0].parent()
                if hasattr(parent, "global_lane_scale"):
                    scale = parent.global_lane_scale
        except (AttributeError, IndexError):
            pass

        pen_w = max(4, (self.base_width * scale) / 25.0)
        pen = QPen(QColor(255, 255, 255, 90), pen_w)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)

    @property
    def logical_width(self):
        scale = 1.0
        if (
            self.scene()
            and self.scene().views()
            and isinstance(self.scene().views()[0].parent(), MapPreviewWidget)
        ):
            scale = self.scene().views()[0].parent().global_lane_scale
        return self.base_width * scale

    def update_position(self):
        self.setLine(
            self.start_node.scenePos().x(),
            self.start_node.scenePos().y(),
            self.end_node.scenePos().x(),
            self.end_node.scenePos().y(),
        )


class VisualNode(QGraphicsEllipseItem):
    def __init__(self, x, y, radius, node_type, scene, parent=None):
        super().__init__(-10, -10, 20, 20, parent)
        self.node_type = node_type
        self.clear_radius = radius
        self.edges = []

        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(2)

        scene.addItem(self)

    def paint(self, painter, option, widget):
        painter.save()
        painter.scale(1, -1)
        r = 84
        rect = QRectF(-r, -r, r * 2, r * 2)

        if self.node_type == ZoneType.RESOURCE:
            if not SVG_RENDERERS["res"].render(painter, rect):
                # Fallback if SVG fails
                painter.setPen(QPen(QColor(100, 255, 100), 2))
                painter.setBrush(QBrush(QColor(0, 150, 0, 180)))
                painter.drawEllipse(QRectF(-30, -30, 60, 60))
        elif self.node_type == ZoneType.BASE:
            if not SVG_RENDERERS["imp"].render(painter, rect):
                painter.setPen(QPen(QColor(100, 100, 255), 2))
                painter.setBrush(QBrush(QColor(0, 0, 150, 180)))
                painter.drawEllipse(QRectF(-30, -30, 60, 60))
        else:
            # Wilderness node - simple dot
            painter.setPen(QPen(QColor(150, 150, 180), 2))
            painter.setBrush(QBrush(QColor(80, 80, 100, 150)))
            painter.drawEllipse(QRectF(-20, -20, 40, 40))

        # Draw clearing radius (only if > 0)
        if self.clear_radius > 0:
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.DashLine))
            painter.setBrush(QBrush(QColor(255, 255, 255, 5)))
            r_clear = self.clear_radius
            painter.drawEllipse(QRectF(-r_clear, -r_clear, r_clear * 2, r_clear * 2))

        # Draw lane node radius for bases
        if self.node_type in (ZoneType.BASE,) and getattr(self, 'lane_radius', 0) > 0:
            painter.setPen(QPen(QColor(255, 255, 100, 40), 2, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            r_lane = self.lane_radius
            painter.drawEllipse(QRectF(-r_lane, -r_lane, r_lane * 2, r_lane * 2))

        painter.restore()

    def boundingRect(self):
        r1 = self.clear_radius if self.clear_radius > 0 else 0
        r2 = self.lane_radius if self.node_type == ZoneType.BASE and getattr(self, 'lane_radius', 0) > 0 else 0
        max_r = max(84, r1, r2)
        if max_r == 84:
            return QRectF(-94, -94, 188, 188)
        return QRectF(-max_r - 10, -max_r - 10, max_r * 2 + 20, max_r * 2 + 20)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
        return super().itemChange(change, value)


class MapPreviewWidget(QWidget):
    # Signals for entity placement updates
    base_moved = Signal(str, float, float)  # (faction, x, y)
    resource_moved = Signal(int, float, float)  # (index, x, y)
    resource_added = Signal(float, float)  # (x, y)
    layout_changed = Signal()  # emitted when nodes/links change to update preview
    lanes_changed = Signal()   # emitted only for node/lane topology changes (no heightmap regen)
    lane_width_changed = Signal(float)  # Emits absolute width in units

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        from PySide6.QtWidgets import QFrame

        def create_divider():
            line = QFrame()
            line.setFixedWidth(1)
            line.setStyleSheet("background-color: #383842; margin: 4px 6px;")
            return line

        def add_tool(layout_obj, text, tool_id):
            btn = QPushButton(text)
            btn.setObjectName("ContextToolBtn")
            btn.setCheckable(True)
            self.tool_group.addButton(btn, tool_id)
            layout_obj.addWidget(btn)
            return btn

        # Action history for Undo/Redo
        self.history = []
        self.redo_history = []

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.idClicked.connect(self.on_tool_changed)

        # ── Top Row: Globals & Tabs ──
        top_row_layout = QHBoxLayout()
        top_row_layout.setContentsMargins(4, 4, 4, 2)
        top_row_layout.setSpacing(6)

        # Handle
        handle = QLabel("⋮")
        handle.setStyleSheet("color: #555566; font-size: 15px; font-weight: bold; margin-bottom: 2px; padding-left: 2px;")
        top_row_layout.addWidget(handle)
        top_row_layout.addWidget(create_divider())

        # Global Actions
        self.btn_undo = QPushButton("↶\nUndo")
        self.btn_undo.setObjectName("GlobalActionBtn")
        self.btn_undo.clicked.connect(self.undo)
        top_row_layout.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↷\nRedo")
        self.btn_redo.setObjectName("GlobalActionBtn")
        self.btn_redo.clicked.connect(self.redo)
        top_row_layout.addWidget(self.btn_redo)

        self.btn_toggle_3d = QPushButton("👁️\n3D View")
        self.btn_toggle_3d.setObjectName("GlobalActionBtn")
        self.btn_toggle_3d.clicked.connect(self.toggle_3d_view)
        top_row_layout.addWidget(self.btn_toggle_3d)

        top_row_layout.addWidget(create_divider())

        # Tabs Container
        tab_container = QWidget()
        tab_container.setObjectName("TabContainer")
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(2, 2, 2, 2)
        tab_layout.setSpacing(2)

        self.tab_group = QButtonGroup(self)
        tabs = [("⛰️ Terrain", 0), ("🚩 Entities", 1), ("🛣️ Layout", 2)]
        for text, idx in tabs:
            btn = QPushButton(text)
            btn.setObjectName("TabButton")
            btn.setCheckable(True)
            self.tab_group.addButton(btn, idx)
            tab_layout.addWidget(btn)

        self.tab_group.idClicked.connect(self.on_tab_changed)
        top_row_layout.addWidget(tab_container)
        
        top_row_layout.addStretch()

        # Clear All Action
        top_row_layout.addWidget(create_divider())
        self.btn_clear = QPushButton("🗑️\nClear All")
        self.btn_clear.setObjectName("DangerActionBtn")
        self.btn_clear.clicked.connect(self.clear_scene_nodes)
        top_row_layout.addWidget(self.btn_clear)

        layout.addLayout(top_row_layout)

        # ── Bottom Row: Context Tools ──
        self.stacked_tools = QStackedWidget()
        self.stacked_tools.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        # -- Page 0: Terrain --
        page_terrain = QWidget()
        layout_t = QHBoxLayout(page_terrain)
        layout_t.setContentsMargins(4, 2, 4, 4)

        self.btn_raise = add_tool(layout_t, "▲\nRaise", 8)
        self.btn_lower = add_tool(layout_t, "▼\nLower", 9)
        self.btn_flatten = add_tool(layout_t, "▬\nFlatten", 10)
        self.btn_mask = add_tool(layout_t, "🎭\nMask", 11)
        self.btn_tile_paint = add_tool(layout_t, "🧱\nTile Paint\n(WIP)", 13)

        layout_t.addWidget(create_divider())

        # Sliders
        sliders_layout = QGridLayout()
        sliders_layout.setContentsMargins(4, 0, 4, 0)
        sliders_layout.setSpacing(6)
        
        lbl_size = QLabel("Size:")
        lbl_size.setStyleSheet("color: #999; font-size: 10px;")
        sliders_layout.addWidget(lbl_size, 0, 0)
        
        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_slider.setRange(64, 4096)
        self.brush_size_slider.setValue(512)
        self.brush_size_slider.setFixedWidth(80)
        sliders_layout.addWidget(self.brush_size_slider, 0, 1)
        
        self.brush_size_label = QLabel("512")
        self.brush_size_label.setStyleSheet("color: #ccc; font-size: 10px; font-family: monospace;")
        self.brush_size_slider.valueChanged.connect(
            lambda v: self.brush_size_label.setText(str(v))
        )
        sliders_layout.addWidget(self.brush_size_label, 0, 2)

        lbl_str = QLabel("Str:")
        lbl_str.setStyleSheet("color: #999; font-size: 10px;")
        sliders_layout.addWidget(lbl_str, 1, 0)
        
        self.brush_strength_slider = QSlider(Qt.Horizontal)
        self.brush_strength_slider.setRange(5, 200)
        self.brush_strength_slider.setValue(50)
        self.brush_strength_slider.setFixedWidth(80)
        sliders_layout.addWidget(self.brush_strength_slider, 1, 1)
        
        self.brush_strength_label = QLabel("50")
        self.brush_strength_label.setStyleSheet("color: #ccc; font-size: 10px; font-family: monospace;")
        self.brush_strength_slider.valueChanged.connect(
            lambda v: self.brush_strength_label.setText(str(v))
        )
        sliders_layout.addWidget(self.brush_strength_label, 1, 2)

        layout_t.addLayout(sliders_layout)

        # Paint material list follows the main window "Global Theme" (see set_material_theme).
        self.combo_texture = WidePopupComboBox()
        self.combo_texture.setObjectName("GroundTextureCombo")
        self.combo_texture.setMaxVisibleItems(14)
        self.combo_texture.setMinimumWidth(172)
        self.combo_texture.setToolTip("Paint material (same theme as sidebar)")
        # Added to layout, but visibility handled by mode change
        layout_t.addWidget(self.combo_texture)
        self.combo_texture.setVisible(False)

        self.combo_paint_target = QComboBox()
        self.combo_paint_target.setObjectName("TilePaintTargetCombo")
        self.combo_paint_target.setFixedWidth(90)
        self.combo_paint_target.setToolTip("Choose which terrain slopes tile paint affects")
        self.combo_paint_target.addItem("Floor", "floor")
        self.combo_paint_target.addItem("Walls", "walls")
        self.combo_paint_target.addItem("All", "all")
        layout_t.addWidget(self.combo_paint_target)
        self.combo_paint_target.setVisible(False)
        self.combo_paint_target.currentIndexChanged.connect(
            self._on_tile_paint_target_changed
        )

        self.lbl_mode_info = QLabel("")
        self.lbl_mode_info.setStyleSheet("color: #aaa; font-size: 10px; font-weight: bold; margin-left: 10px;")
        layout_t.addWidget(self.lbl_mode_info)

        layout_t.addWidget(create_divider())

        self.btn_invert_terrain = QPushButton("⛰️\nInvert Terrain")
        self.btn_invert_terrain.setObjectName("GlobalActionBtn")
        self.btn_invert_terrain.clicked.connect(self.invert_terrain)
        layout_t.addWidget(self.btn_invert_terrain)

        self.btn_invert_mask = QPushButton("🔄\nInvert Mask")
        self.btn_invert_mask.setObjectName("GlobalActionBtn")
        self.btn_invert_mask.clicked.connect(self.invert_mask)
        layout_t.addWidget(self.btn_invert_mask)

        self.btn_clear_mask = QPushButton("🗑️\nClear Mask")
        self.btn_clear_mask.setObjectName("GlobalActionBtn")
        self.btn_clear_mask.clicked.connect(self.clear_mask)
        layout_t.addWidget(self.btn_clear_mask)

        self.btn_reset_mask = QPushButton("↺\nReset Mask")
        self.btn_reset_mask.setObjectName("GlobalActionBtn")
        self.btn_reset_mask.clicked.connect(self.reset_mask)
        layout_t.addWidget(self.btn_reset_mask)

        layout_t.addStretch()
        self.stacked_tools.addWidget(page_terrain)

        # -- Page 1: Entities --
        page_entities = QWidget()
        layout_e = QHBoxLayout(page_entities)
        layout_e.setContentsMargins(4, 2, 4, 4)

        self.btn_move_ent = add_tool(layout_e, "🖱️\nMove", 200)
        self.btn_remove_ent = add_tool(layout_e, "❌\nRemove", 201)
        layout_e.addWidget(create_divider())
        self.btn_set_be = add_tool(layout_e, "🔵\nSet BE", 2)
        self.btn_set_nf = add_tool(layout_e, "🔴\nSet NF", 7)
        self.btn_add_res = add_tool(layout_e, "💎\nAdd Res", 3)

        layout_e.addStretch()
        self.stacked_tools.addWidget(page_entities)

        # -- Page 2: Layout --
        page_layout = QWidget()
        layout_l = QHBoxLayout(page_layout)
        layout_l.setContentsMargins(4, 2, 4, 4)

        self.btn_move_lay = add_tool(layout_l, "🖱️\nMove", 300)
        self.btn_remove_lay = add_tool(layout_l, "❌\nRemove", 301)
        layout_l.addWidget(create_divider())
        self.btn_lane = add_tool(layout_l, "🛣️\nLane", 6)

        layout_l.addWidget(create_divider())
        lbl_width = QLabel("Width:")
        lbl_width.setStyleSheet("color: #999; font-size: 10px;")
        layout_l.addWidget(lbl_width)
        
        self.thickness_slider = QSlider(Qt.Horizontal)
        self.thickness_slider.setRange(0, 800)
        self.thickness_slider.setValue(600)
        self.thickness_slider.setFixedWidth(80)
        layout_l.addWidget(self.thickness_slider)
        
        self.thickness_label = QLabel("600")
        self.thickness_label.setStyleSheet("color: #ccc; font-size: 10px; font-family: monospace;")
        self.thickness_slider.valueChanged.connect(self._on_thickness_slider_changed)
        layout_l.addWidget(self.thickness_label)

        layout_l.addStretch()
        self.stacked_tools.addWidget(page_layout)

        layout.addWidget(self.stacked_tools)

        # ── Graphics View ──
        class CustomGraphicsView(QGraphicsView):
            def __init__(self, scene, parent_widget):
                super().__init__(scene)
                self.parent_widget = parent_widget

            def wheelEvent(self, event):
                self.parent_widget.on_wheel_event(event)

            def mousePressEvent(self, event):
                # Always handle middle-button panning in all modes
                if event.button() == Qt.MiddleButton:
                    self.parent_widget.on_mouse_press(event)
                    return

                mode = self.parent_widget.current_mode
                if mode == 0:
                    # Move tool: let Qt handle item selection & dragging
                    super().mousePressEvent(event)
                else:
                    # Other tools: run custom logic, skip super()
                    # so Qt doesn't grab items and steal the event
                    self.parent_widget.on_mouse_press(event)

            def mouseMoveEvent(self, event):
                mode = self.parent_widget.current_mode
                if mode == 0:
                    super().mouseMoveEvent(event)
                self.parent_widget.on_mouse_move(event)

            def mouseReleaseEvent(self, event):
                mode = self.parent_widget.current_mode
                if mode == 0:
                    super().mouseReleaseEvent(event)
                self.parent_widget.on_mouse_release(event)

        class CustomGLViewWidget(gl.GLViewWidget):
            def __init__(self, parent_widget, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent_widget = parent_widget
                self._last_hover_tile = (None, None)

            def _pick_tile(self, mouse_x, mouse_y):
                """Map screen click to VMF tile (tx, ty) using robust matrix inversion."""
                try:
                    w = self.width()
                    h = self.height()
                    if w == 0 or h == 0:
                        return None, None

                    # NDC: map pixel to -1..1
                    x = (2.0 * mouse_x / w) - 1.0
                    y = 1.0 - (2.0 * mouse_y / h)

                    # Get pyqtgraph matrices
                    vp = (0, 0, w, h)
                    pm = self.projectionMatrix(region=vp, viewport=vp)
                    vm = self.viewMatrix()
                    
                    # Combine and invert
                    inv_mvp = (pm * vm).inverted()[0]
                    
                    # Near and far points in world space
                    p0 = inv_mvp.map(QVector3D(x, y, -1.0))
                    p1 = inv_mvp.map(QVector3D(x, y, 1.0))
                    
                    p0 = np.array([p0.x(), p0.y(), p0.z()])
                    p1 = np.array([p1.x(), p1.y(), p1.z()])
                    
                    ray_dir = p1 - p0
                    ray_dir /= np.linalg.norm(ray_dir)
                    
                    # Terrain is centered at z=0 in GL space (since we subtract mean_h)
                    target_z = 0.0
                    if abs(ray_dir[2]) < 1e-6:
                        return None, None
                    
                    t = (target_z - p0[2]) / ray_dir[2]
                    if t < 0:
                        return None, None
                        
                    hit = p0 + t * ray_dir

                    # Map world XY to tile index
                    map_w = getattr(self, '_map_size_x', 8192)
                    map_h = getattr(self, '_map_size_y', 8192)
                    tiles_x = getattr(self, '_tiles_x', 16)
                    tiles_y = getattr(self, '_tiles_y', 16)

                    # Adjust for origin-centered grid (matching _update_3d_view)
                    # rel_x: -map_w/2 -> 0, +map_w/2 -> 1
                    rel_x = (hit[0] + map_w / 2.0) / map_w
                    # rel_y: -map_h/2 -> 0, +map_h/2 -> 1
                    rel_y = (hit[1] + map_h / 2.0) / map_h

                    tx = int(rel_x * tiles_x)
                    ty = int(rel_y * tiles_y)

                    if 0 <= tx < tiles_x and 0 <= ty < tiles_y:
                        return tx, ty
                except Exception as e:
                    print(f"[TilePaint] _pick_tile matrix error: {e}")
                return None, None

            def mousePressEvent(self, event):
                if self.parent_widget.current_mode == 13:
                    if event.button() == Qt.LeftButton:
                        tx, ty = self._pick_tile(event.position().x(), event.position().y())
                        if tx is not None:
                            self.parent_widget._begin_tile_paint()
                            self.parent_widget._paint_tile(tx, ty, erase=False)
                        return   # consume left click
                    if event.button() == Qt.RightButton:
                        tx, ty = self._pick_tile(event.position().x(), event.position().y())
                        if tx is not None:
                            self.parent_widget._begin_tile_paint()
                            self.parent_widget._paint_tile(tx, ty, erase=True)
                        return   # consume right click
                    # Middle button and anything else: fall through to orbit
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                if self.parent_widget.current_mode == 13:
                    tx, ty = self._pick_tile(event.position().x(), event.position().y())
                    if event.buttons() & Qt.LeftButton:
                        if tx is not None:
                            self.parent_widget._paint_tile(tx, ty, erase=False)
                        return
                    if event.buttons() & Qt.RightButton:
                        if tx is not None:
                            self.parent_widget._paint_tile(tx, ty, erase=True)
                        return
                    if (tx, ty) != self._last_hover_tile:
                        self._last_hover_tile = (tx, ty)
                        self.parent_widget._set_tile_hover(tx, ty)
                super().mouseMoveEvent(event)

            def mouseReleaseEvent(self, event):
                if self.parent_widget.current_mode == 13:
                    self.parent_widget._end_tile_paint()
                super().mouseReleaseEvent(event)

            def wheelEvent(self, event):
                # Always pass wheel to super — never intercept zoom
                super().wheelEvent(event)

        self.scene = QGraphicsScene()
        self.view = CustomGraphicsView(self.scene, self)
        self.view.scale(1, -1)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.setStyleSheet("background-color: #0d0d10; border: 1px solid #2e2e36;")

        self.view_3d = CustomGLViewWidget(self)
        self.view_3d.setBackgroundColor((13, 13, 20, 255))

        # --- 3D Controls Toolbar ---
        _ctrl_style = """
            QPushButton {
                background: #1e1e2a; color: #c8cad4; border: 1px solid #35364a;
                border-radius: 4px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #2a2b3d; border-color: #5b8dee; color: #e8eaf0; }
            QPushButton:checked { background: #3a4a7a; border-color: #5b8dee; color: #ffffff; }
        """
        _sep_style = "color: #35364a; font-size: 13px;"

        ctrl_bar = QWidget()
        ctrl_bar.setFixedHeight(30)
        ctrl_bar.setStyleSheet("background: #13131d; border-bottom: 1px solid #2a2b3a;")
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(6, 2, 6, 2)
        ctrl_layout.setSpacing(4)

        def _mk_btn(label, tip, checkable=False):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setStyleSheet(_ctrl_style)
            b.setCheckable(checkable)
            b.setFixedHeight(22)
            return b

        self.btn_3d_reset   = _mk_btn("⟳ Reset",   "Reset camera to default perspective")
        self.btn_3d_top     = _mk_btn("⬆ Top",     "Top-down view")
        self.btn_3d_iso     = _mk_btn("⬡ Iso",     "Isometric view (45° elevation)")
        self.btn_3d_side    = _mk_btn("⬛ Side",    "Side view")
        self.btn_3d_wire    = _mk_btn("⬜ Wire",    "Toggle wireframe overlay", checkable=True)

        self.btn_3d_reset.clicked.connect(self._3d_reset_camera)
        self.btn_3d_top.clicked.connect(self._3d_view_top)
        self.btn_3d_iso.clicked.connect(self._3d_view_iso)
        self.btn_3d_side.clicked.connect(self._3d_view_side)
        self.btn_3d_wire.toggled.connect(self._3d_toggle_wireframe)

        sep = QLabel("│")
        sep.setStyleSheet(_sep_style)

        self.lbl_3d_zoom = QLabel("Zoom")
        self.lbl_3d_zoom.setStyleSheet("color: #6a6c80; font-size: 10px; margin-left: 4px;")
        self.btn_3d_zoom_in  = _mk_btn("+", "Zoom in")
        self.btn_3d_zoom_out = _mk_btn("−", "Zoom out")
        self.btn_3d_zoom_in.setFixedWidth(22)
        self.btn_3d_zoom_out.setFixedWidth(22)
        self.btn_3d_zoom_in.clicked.connect(lambda: self._3d_zoom(0.7))
        self.btn_3d_zoom_out.clicked.connect(lambda: self._3d_zoom(1.4))

        for w in [self.btn_3d_reset, self.btn_3d_top, self.btn_3d_iso, self.btn_3d_side,
                  sep, self.btn_3d_wire]:
            ctrl_layout.addWidget(w)
        ctrl_layout.addStretch()
        for w in [self.lbl_3d_zoom, self.btn_3d_zoom_out, self.btn_3d_zoom_in]:
            ctrl_layout.addWidget(w)

        view_3d_container = QWidget()
        _v3d_layout = QVBoxLayout(view_3d_container)
        _v3d_layout.setContentsMargins(0, 0, 0, 0)
        _v3d_layout.setSpacing(0)
        _v3d_layout.addWidget(ctrl_bar)
        _v3d_layout.addWidget(self.view_3d)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.view)
        self.view_stack.addWidget(view_3d_container)

        layout.addWidget(self.view_stack)

        self.current_mode = 0
        self.tab_group.button(0).setChecked(True)
        self.on_tab_changed(0)

        # State
        self.map_image = None
        self.map_pixmap_item = QGraphicsPixmapItem()
        self.map_pixmap_item.setZValue(-10)
        self.scene.addItem(self.map_pixmap_item)

        self.map_size_x = 8192
        self.map_size_y = 8192
        self.origin_x = -4096
        self.origin_y = -4096

        self.scene.setSceneRect(
            self.origin_x, self.origin_y, self.map_size_x, self.map_size_y
        )

        # In world coordinates
        self.imp_base = None  # (x, y)
        self.nf_base = None  # (x, y)
        self.resources = []  # [(x, y), ...]
        self.invalid_entities = set()

        # Grid
        self.grid_size = 512
        self.grid_items = []
        self._show_2d_grid = False
        self.draw_grid()

        self.panning = False
        self.pan_start_pos = QPointF()

        self.drawing_lane = False
        self.current_freehand_path = []
        self.current_freehand_item = None
        self.freehand_start_node = None
        self.current_base_width = 600.0
        self.global_lane_scale = 1.0

        # Sculpting state
        self._base_heights = None  # numpy float64 from pipeline
        self._height_overlay = None  # numpy float64 additive delta
        self._global_selection_mask = None # numpy bool
        self._texture_overlay = None  # numpy int32 mapping to materials
        self._tile_overlay = None     # numpy int32 mapping to materials (per displacement tile)
        self._texture_mapping = {}    # mapping from string material to integer id (and 0=default)
        self._all_themes = {}        # {theme_name: [material_entries]}
        self._next_texture_id = 1
        self._tile_paint_target = "floor"
        self._sculpting = False
        self._tile_painting = False
        self._tile_paint_snapshot = None
        self._tile_hover = (None, None)
        self._tile_hover_item = QGraphicsRectItem()
        hover_pen = QPen(QColor(255, 255, 255, 230), 0)
        hover_pen.setCosmetic(True)
        self._tile_hover_item.setPen(hover_pen)
        self._tile_hover_item.setBrush(QBrush(QColor(255, 255, 255, 32)))
        self._tile_hover_item.setZValue(6)
        self._tile_hover_item.setVisible(False)
        self.scene.addItem(self._tile_hover_item)
        self._flatten_target_height = None
        self._active_mouse_button = None
        # Clear radii for entity zones
        self.base_clear_radius = 0
        self.resource_clear_radius = 256
        self.lane_node_radius = 512

        self._last_z_array = None
        self._last_x_array = None
        self._last_y_array = None
        self._surface_item = None
        self._tile_mesh_items = []
        self._tile_grid_lines = []
        self.resource_clear_radius = 256
        self.lane_node_radius = 512


    def draw_grid(self):
        if not getattr(self, "_show_2d_grid", False):
            for item in self.grid_items:
                self.scene.removeItem(item)
            self.grid_items.clear()
            return

        for item in self.grid_items:
            self.scene.removeItem(item)
        self.grid_items.clear()

        grid_pen = QPen(QColor(50, 50, 60, 100))  # Semi-transparent grid
        grid_pen.setWidth(0)
        left = int(self.scene.sceneRect().left())
        right = int(self.scene.sceneRect().right())
        top = int(self.scene.sceneRect().top())
        bottom = int(self.scene.sceneRect().bottom())

        for x in range(left, right, self.grid_size):
            line = QGraphicsLineItem(x, top, x, bottom)
            line.setPen(grid_pen)
            line.setZValue(-5)
            self.scene.addItem(line)
            self.grid_items.append(line)

        for y in range(top, bottom, self.grid_size):
            line = QGraphicsLineItem(left, y, right, y)
            line.setPen(grid_pen)
            line.setZValue(-5)
            self.scene.addItem(line)
            self.grid_items.append(line)

    def set_map_image(
        self,
        image: QImage,
        origin_x,
        origin_y,
        size_x,
        size_y,
        tile_size: int = 512,
        tiles_x: int = 16,
        tiles_y: int = 16,
    ):
        self.map_image = image
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.map_size_x = size_x
        self.map_size_y = size_y
        self.grid_size = max(1, int(tile_size))
        self._tiles_x = tiles_x
        self._tiles_y = tiles_y

        self.scene.setSceneRect(
            self.origin_x, self.origin_y, self.map_size_x, self.map_size_y
        )
        # Update tile overlay shape if map dimensions changed
        if self._tile_overlay is None or self._tile_overlay.shape != (self._tiles_y, self._tiles_x):
            old_overlay = self._tile_overlay
            self._tile_overlay = np.zeros((self._tiles_y, self._tiles_x), dtype=np.int32)
            if old_overlay is not None:
                keep_y = min(old_overlay.shape[0], self._tiles_y)
                keep_x = min(old_overlay.shape[1], self._tiles_x)
                self._tile_overlay[:keep_y, :keep_x] = old_overlay[:keep_y, :keep_x]

        self.draw_grid()
        self.update_pixmap()

    def set_entities(self, imp_base, nf_base, resources, invalid_entities=None):
        self.imp_base = imp_base
        self.nf_base = nf_base
        self.resources = resources if resources else []
        self.invalid_entities = invalid_entities if invalid_entities else set()

        # We need to draw these entities using QGraphicsItems
        # Currently, doing a full re-draw logic since MapPreviewWidget did it in paintEvent
        # Let's remove old overlay items and add new ones
        self.redraw_fixed_entities()

    def redraw_fixed_entities(self):
        # Remove old custom entities
        for item in self.scene.items():
            if hasattr(item, "is_fixed_entity"):
                self.scene.removeItem(item)

        # Store current radii for new items
        getattr(self, "base_clear_radius", 512)
        getattr(self, "resource_clear_radius", 256)
        getattr(self, "lane_node_radius", 512)

        # A helper class for non-node bases/resources that MapPreviewWidget used to draw natively
        class FixedEntityItem(QGraphicsItem):
            def __init__(
                self,
                x,
                y,
                entity_type,
                clear_radius=0,
                lane_radius=0,
                index=None,
                invalid=False,
                parent=None,
            ):
                super().__init__(parent)
                self.x_coord = x
                self.y_coord = y
                self.entity_type = entity_type
                self.clear_radius = clear_radius
                self.lane_radius = lane_radius
                self.index = index
                self.invalid = invalid
                self.setPos(x, y)
                self.setZValue(3)
                self.is_fixed_entity = True
                self.setFlags(
                    QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges
                )
                # Flip the node vertically because the view is flipped
                # No transform needed, stars should be at the bottom
                pass

            def boundingRect(self):
                r = max(84, self.clear_radius) if self.clear_radius > 0 else 84
                return QRectF(-r - 10, -r - 10, r * 2 + 20, r * 2 + 20)

            def itemChange(self, change, value):
                return super().itemChange(change, value)

            def mouseReleaseEvent(self, event):
                super().mouseReleaseEvent(event)
                # Emit only on release to prevent constant synchronous rebuilds while dragging
                if self.entity_type == "imp":
                    if isinstance(self.scene().views()[0].parent(), MapPreviewWidget):
                        pw = self.scene().views()[0].parent()
                        if pw._base_heights is not None:
                            pw.update_3d_view(pw._base_heights + (pw._height_overlay if pw._height_overlay is not None else 0))
                        pw.base_moved.emit(
                            "imp", self.x(), self.y()
                        )
                elif self.entity_type == "nf":
                    if isinstance(self.scene().views()[0].parent(), MapPreviewWidget):
                        pw = self.scene().views()[0].parent()
                        if pw._base_heights is not None:
                            pw.update_3d_view(pw._base_heights + (pw._height_overlay if pw._height_overlay is not None else 0))
                        pw.base_moved.emit(
                            "nf", self.x(), self.y()
                        )
                elif self.entity_type == "res":
                    if isinstance(self.scene().views()[0].parent(), MapPreviewWidget):
                        pw = self.scene().views()[0].parent()
                        old_res_list = list(pw.resources)
                        new_res_list = list(pw.resources)
                        if self.index is not None and 0 <= self.index < len(
                            new_res_list
                        ):
                            new_res_list[self.index] = (self.x(), self.y())
                        pw.record_action("set_res", (old_res_list, new_res_list))
                        pw.resources = new_res_list
                        if pw._base_heights is not None:
                            pw.update_3d_view(pw._base_heights + (pw._height_overlay if pw._height_overlay is not None else 0))
                        pw.resource_moved.emit(self.index, self.x(), self.y())

            def paint(self, painter, option, widget):
                painter.save()
                painter.scale(1, -1)
                rect = QRectF(-84, -84, 168, 168)

                if self.entity_type == "res":
                    SVG_RENDERERS["res"].render(painter, rect)
                elif self.entity_type == "imp":
                    SVG_RENDERERS["imp"].render(painter, rect)
                elif self.entity_type == "nf":
                    SVG_RENDERERS["nf"].render(painter, rect)

                if self.invalid:
                    painter.setPen(QPen(QColor(255, 50, 50), 3))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(rect.adjusted(-4, -4, 4, 4))
                    painter.setPen(QColor(255, 50, 50))
                    painter.drawText(-6, 100, "⚠")

                # Draw clearance radius
                if self.clear_radius > 0:
                    painter.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.DashLine))
                    painter.setBrush(QBrush(QColor(255, 255, 255, 5)))
                    r_clear = self.clear_radius
                    painter.drawEllipse(
                        QRectF(-r_clear, -r_clear, r_clear * 2, r_clear * 2)
                    )

                painter.restore()

        if (
            self.imp_base
            and self.imp_base[0] is not None
            and self.imp_base[1] is not None
        ):
            invalid = "imp" in self.invalid_entities
            self.scene.addItem(
                FixedEntityItem(
                    self.imp_base[0],
                    self.imp_base[1],
                    "imp",
                    clear_radius=self.base_clear_radius,
                    lane_radius=self.lane_node_radius,
                    invalid=invalid,
                )
            )

        if self.nf_base and self.nf_base[0] is not None and self.nf_base[1] is not None:
            invalid = "nf" in self.invalid_entities
            self.scene.addItem(
                FixedEntityItem(
                    self.nf_base[0],
                    self.nf_base[1],
                    "nf",
                    clear_radius=self.base_clear_radius,
                    lane_radius=self.lane_node_radius,
                    invalid=invalid,
                )
            )

        for i, res in enumerate(self.resources):
            invalid = str(i) in self.invalid_entities
            self.scene.addItem(
                FixedEntityItem(
                    res[0],
                    res[1],
                    "res",
                    clear_radius=self.resource_clear_radius,
                    index=i,
                    invalid=invalid,
                )
            )

        if self._base_heights is not None:
            self.update_3d_view(self._base_heights + (self._height_overlay if self._height_overlay is not None else 0))

    def update_pixmap(self):
        if self.map_image:
            pixmap = QPixmap.fromImage(self.map_image)
            self.map_pixmap_item.setPixmap(pixmap)

            # Scale pixmap to fill the map bounds using a non-uniform transform.
            # Do NOT also call setScale() — it compounds with setTransform(),
            # which would make the image ~scale² too large (showing <1 pixel).
            scale_x = self.map_size_x / max(1, pixmap.width())
            scale_y = self.map_size_y / max(1, pixmap.height())

            from PySide6.QtGui import QTransform

            self.map_pixmap_item.setTransform(QTransform.fromScale(scale_x, scale_y))

            self.map_pixmap_item.setPos(self.origin_x, self.origin_y)
        else:
            self.map_pixmap_item.setPixmap(QPixmap())

    def _tile_color(self, tile_id: int, alpha: int = 145) -> QColor:
        if tile_id <= 0:
            return QColor(255, 255, 255, alpha)
        hue = (tile_id * 137) % 360
        return QColor.fromHsv(hue, 135, 230, alpha)

    def _tile_material_name(self, tile_id: int) -> str:
        if tile_id <= 0:
            return "Default"
        for idx in range(self.combo_texture.count()):
            if self._texture_mapping.get(self.combo_texture.itemData(idx)) == tile_id:
                return self.combo_texture.itemText(idx)
        return f"Material {tile_id}"

    def _current_tile_material_id(self) -> Optional[int]:
        material_str = self.combo_texture.currentData()
        if material_str is None:
            return None
        if material_str not in self._texture_mapping:
            self._texture_mapping[material_str] = self._next_texture_id
            self._next_texture_id += 1
        return self._texture_mapping[material_str]

    def _scene_to_tile(self, scene_x: float, scene_y: float) -> Tuple[Optional[int], Optional[int]]:
        if self.map_size_x <= 0 or self.map_size_y <= 0:
            return None, None

        tiles_x = max(1, int(getattr(self, "_tiles_x", 1)))
        tiles_y = max(1, int(getattr(self, "_tiles_y", 1)))
        rel_x = (scene_x - self.origin_x) / self.map_size_x
        rel_y = (scene_y - self.origin_y) / self.map_size_y

        if rel_x < 0.0 or rel_x >= 1.0 or rel_y < 0.0 or rel_y >= 1.0:
            return None, None

        tx = min(tiles_x - 1, int(rel_x * tiles_x))
        ty = min(tiles_y - 1, int(rel_y * tiles_y))
        return tx, ty

    def _tile_rect(self, tx: int, ty: int) -> QRectF:
        tile_w = self.map_size_x / max(1, int(getattr(self, "_tiles_x", 1)))
        tile_h = self.map_size_y / max(1, int(getattr(self, "_tiles_y", 1)))
        return QRectF(
            self.origin_x + tx * tile_w,
            self.origin_y + ty * tile_h,
            tile_w,
            tile_h,
        )

    def _set_tile_hover(self, tx: Optional[int], ty: Optional[int]):
        self._tile_hover = (tx, ty)
        if self.current_mode != 13 or tx is None or ty is None:
            self._tile_hover_item.setVisible(False)
            return
        self._tile_hover_item.setRect(self._tile_rect(tx, ty))
        self._tile_hover_item.setVisible(True)

    def _begin_tile_paint(self):
        if self._tile_overlay is None or self._tile_painting:
            return
        self._tile_painting = True
        self._tile_paint_snapshot = self._tile_overlay.copy()

    def _end_tile_paint(self):
        if not self._tile_painting:
            return

        changed = (
            self._tile_paint_snapshot is not None
            and self._tile_overlay is not None
            and not np.array_equal(self._tile_paint_snapshot, self._tile_overlay)
        )
        if changed:
            self.history.append(("tile_texture_change", self._tile_paint_snapshot))
            self.redo_history.clear()
            self.layout_changed.emit()

        self._tile_painting = False
        self._tile_paint_snapshot = None

    def _paint_tile_at_scene(self, scene_x: float, scene_y: float, erase: bool = False):
        tx, ty = self._scene_to_tile(scene_x, scene_y)
        if tx is None or ty is None:
            self._set_tile_hover(None, None)
            return
        self._set_tile_hover(tx, ty)
        self._paint_tile(tx, ty, erase=erase)

    def _paint_tile(self, tx: int, ty: int, erase: bool = False):
        if self._tile_overlay is None:
            return
        if not (0 <= ty < self._tile_overlay.shape[0] and 0 <= tx < self._tile_overlay.shape[1]):
            return

        mat_id = 0 if erase else self._current_tile_material_id()
        if mat_id is None:
            return
        if int(self._tile_overlay[ty, tx]) == mat_id:
            return

        self._tile_overlay[ty, tx] = mat_id
        self._rerender_heightmap(update_3d=False)
        self._update_3d_tile_overlay()

        mat_name = self._tile_material_name(mat_id)
        color = self._tile_color(mat_id, alpha=255)
        status_msg = (
            f"Tile ({tx + 1}, {ty + 1})/{self._tiles_x}x{self._tiles_y}: "
            f"<span style='color:{color.name()}; font-size: 16px;'>■</span> {mat_name}"
        )
        if hasattr(self.parent(), "statusBar") and self.parent().statusBar():
            self.parent().statusBar().showMessage(status_msg)

    def _camera_from_2d_view(self):
        viewport_rect = self.view.viewport().rect()
        center_scene = self.view.mapToScene(viewport_rect.center())
        top_left = self.view.mapToScene(viewport_rect.topLeft())
        bottom_right = self.view.mapToScene(viewport_rect.bottomRight())

        visible_w = max(1.0, abs(bottom_right.x() - top_left.x()))
        visible_h = max(1.0, abs(bottom_right.y() - top_left.y()))

        center_x = center_scene.x() - self.origin_x - (self.map_size_x / 2.0)
        center_y = center_scene.y() - self.origin_y - (self.map_size_y / 2.0)

        visible_extent = max(visible_w, visible_h)
        distance = max(512.0, visible_extent * 0.9)

        return {
            "pos": QVector3D(float(center_x), float(center_y), 0.0),
            "distance": float(distance),
            "elevation": 90.0,
            "azimuth": -90.0,
        }

    def _update_3d_view(self, camera_override=None):
        if self._base_heights is None:
            self._render_markers_only()
            if camera_override is not None:
                self.view_3d.setCameraPosition(**camera_override)
            return

        heights = self._base_heights
        if self._height_overlay is not None:
            heights = heights + self._height_overlay

        self.update_3d_view(heights, camera_override=camera_override)

    def _render_markers_only(self):
        self.view_3d.clear()

        marker_positions = []
        marker_colors = []

        def add_marker_fallback(world_x, world_y, r, g, b, a=1.0):
            if world_x is None or world_y is None:
                return
            sx = world_x - self.origin_x - (self.map_size_x / 2.0)
            sy = (world_y - self.origin_y) - (self.map_size_y / 2.0)
            marker_positions.append([sx, sy, 100.0])
            marker_colors.append([r, g, b, a])

        if self.imp_base and self.imp_base[0] is not None:
            add_marker_fallback(self.imp_base[0], self.imp_base[1], 0.0, 0.4, 1.0)
        if self.nf_base and self.nf_base[0] is not None:
            add_marker_fallback(self.nf_base[0], self.nf_base[1], 1.0, 0.2, 0.2)
        for res in self.resources:
            add_marker_fallback(res[0], res[1], 0.2, 1.0, 0.2)

        if marker_positions:
            scatter = gl.GLScatterPlotItem(
                pos=np.array(marker_positions),
                color=np.array(marker_colors),
                size=15,
                pxMode=True
            )
            self.view_3d.addItem(scatter)

        cam_dist = max(self.map_size_x, self.map_size_y) * 1.2
        self.view_3d.setCameraPosition(distance=cam_dist, elevation=45, azimuth=-45)

    def set_raw_heights(self, heights: np.ndarray, mask: Optional[np.ndarray] = None):

        self._base_heights = heights.astype(np.float64).copy()
        valid_heights = self._base_heights[self._base_heights > 0.1]
        if len(valid_heights) > 0:
            self._base_min = float(valid_heights.min())
        else:
            self._base_min = float(self._base_heights.min())
        self._base_max = float(self._base_heights.max())
        if self._height_overlay is None or self._height_overlay.shape != heights.shape:
            self._height_overlay = np.zeros_like(self._base_heights)

        if self._texture_overlay is None or self._texture_overlay.shape != heights.shape:
            self._texture_overlay = np.zeros(heights.shape, dtype=np.int32)

        # Only reset mask if explicitly None (not just shape mismatch)
        # Preserve existing mask when new heights arrive from pipeline
        if mask is not None:
            self._global_selection_mask = mask.copy()
        elif self._global_selection_mask is None:
            self._global_selection_mask = np.ones(heights.shape, dtype=bool)
        elif self._global_selection_mask.shape != heights.shape:
            # Resize existing mask to match new shape
            from src.compat_utils import scipy_zoom_equivalent
            scale_y = heights.shape[0] / self._global_selection_mask.shape[0]
            scale_x = heights.shape[1] / self._global_selection_mask.shape[1]
            self._global_selection_mask = scipy_zoom_equivalent(
                self._global_selection_mask.astype(np.float32), (scale_y, scale_x)
            ) > 0.5

        # Always re-render to ensure consistent normalization (e.g. neutral gray for flat maps)
        self._rerender_heightmap()
        self._update_3d_view()

    def reset_mask(self):
        if self._global_selection_mask is not None:
            self.record_action("mask_change", self._global_selection_mask.copy())
            self._global_selection_mask[:] = True
            self._rerender_heightmap()

    def clear_mask(self):
        if self._global_selection_mask is not None:
            self.record_action("mask_change", self._global_selection_mask.copy())
            self._global_selection_mask[:] = False
            self._rerender_heightmap()

    def invert_terrain(self):
        if self._base_heights is None or self._height_overlay is None:
            return
            
        if self._base_heights.shape != self._height_overlay.shape:
            return

        self.record_action("heights", self._height_overlay.copy())
        
        combined = self._base_heights + self._height_overlay
        mid_h = (np.max(combined) + np.min(combined)) / 2.0
        
        delta = 2 * mid_h - 2 * self._base_heights - 2 * self._height_overlay
        
        if self._global_selection_mask is not None:
            self._height_overlay[self._global_selection_mask] += delta[self._global_selection_mask]
        else:
            self._height_overlay += delta
            
        self._rerender_heightmap()

    def invert_mask(self):
        if self._global_selection_mask is not None:
            self.record_action("mask_change", self._global_selection_mask.copy())
            self._global_selection_mask = ~self._global_selection_mask
            self._rerender_heightmap()

    def _apply_brush(self, scene_x: float, scene_y: float, mode: int):
        if self._base_heights is None:
            return

        if self._height_overlay is not None and self._base_heights.shape != self._height_overlay.shape:
            return

        h, w = self._base_heights.shape
        brush_radius = self.brush_size_slider.value()
        strength = self.brush_strength_slider.value()

        # Convert scene coords to grid indices
        gx = (scene_x - self.origin_x) / self.map_size_x * w
        gy = (scene_y - self.origin_y) / self.map_size_y * h

        # Brush radius in grid units
        brush_r_px = brush_radius / self.map_size_x * w

        # Grid bounds for the brush
        r_min = max(0, int(gy - brush_r_px))
        r_max = min(h, int(gy + brush_r_px) + 1)
        c_min = max(0, int(gx - brush_r_px))
        c_max = min(w, int(gx + brush_r_px) + 1)

        if r_min >= r_max or c_min >= c_max:
            return

        # Build gaussian falloff
        rows = np.arange(r_min, r_max)
        cols = np.arange(c_min, c_max)
        cc, rr = np.meshgrid(cols, rows)
        dist_sq = (cc - gx) ** 2 + (rr - gy) ** 2
        radius_sq = brush_r_px**2
        mask = dist_sq < radius_sq
        falloff = np.exp(-dist_sq / (radius_sq * 0.3)) * mask

        if mode == 11 and self._global_selection_mask is not None:
            # Mask brush mode:
            # Left-click (True) paints the editable selection.
            # Right-click (False) paints the protected area.
            paint_value = True
            if self._active_mouse_button == Qt.RightButton:
                paint_value = False

            # If the user is starting to paint an editable area (True) and the map is
            # currently entirely editable (True everywhere), assume they want to start a
            # fresh selection. Set the map to protected (False) first.
            if paint_value and np.all(self._global_selection_mask):
                self._global_selection_mask[:] = False

            # Only paint where mask is > threshold (like a hard brush)
            paint_area = mask > 0.5
            self._global_selection_mask[r_min:r_max, c_min:c_max][paint_area] = paint_value
        elif mode == 12 and self._texture_overlay is not None:
            # Texture brush mode:
            material_str = self.combo_texture.currentData()
            if material_str is None:
                return

            if material_str not in self._texture_mapping:
                self._texture_mapping[material_str] = self._next_texture_id
                self._next_texture_id += 1

            mat_id = self._texture_mapping[material_str]

            if self._active_mouse_button == Qt.RightButton:
                mat_id = 0 # Erase custom texture

            # Calculate number of tiles
            tiles_x = self.map_size_x // self.grid_size
            tiles_y = self.map_size_y // self.grid_size

            tile_h_px = max(1, h / tiles_y)
            tile_w_px = max(1, w / tiles_x)

            # Find intersecting tiles
            t_r_min = max(0, int(r_min / tile_h_px))
            t_r_max = min(tiles_y - 1, int(r_max / tile_h_px))
            t_c_min = max(0, int(c_min / tile_w_px))
            t_c_max = min(tiles_x - 1, int(c_max / tile_w_px))

            for ty in range(t_r_min, t_r_max + 1):
                for tx in range(t_c_min, t_c_max + 1):
                    # For each tile, check if its center is within the brush
                    cy = (ty + 0.5) * tile_h_px
                    cx = (tx + 0.5) * tile_w_px
                    if (cx - gx) ** 2 + (cy - gy) ** 2 <= brush_r_px ** 2:
                        py_min = int(ty * tile_h_px)
                        py_max = int((ty + 1) * tile_h_px)
                        px_min = int(tx * tile_w_px)
                        px_max = int((tx + 1) * tile_w_px)

                        py_max = min(h, py_max)
                        px_max = min(w, px_max)

                        self._texture_overlay[py_min:py_max, px_min:px_max] = mat_id

        elif mode == 13 and self._tile_overlay is not None:
            erase = self._active_mouse_button == Qt.RightButton
            self._paint_tile_at_scene(scene_x, scene_y, erase=erase)
            return

        elif mode in (8, 9):
            raise_terrain = (mode == 8)
            delta = falloff * strength * (1.0 if raise_terrain else -1.0)
            if self._global_selection_mask is not None:
                delta *= self._global_selection_mask[r_min:r_max, c_min:c_max]
            self._height_overlay[r_min:r_max, c_min:c_max] += delta
        elif mode == 10:
            if self._flatten_target_height is None:
                cx = max(0, min(w - 1, int(round(gx))))
                cy = max(0, min(h - 1, int(round(gy))))
                self._flatten_target_height = float(
                    self._base_heights[cy, cx] + self._height_overlay[cy, cx]
                )
            current_heights = self._base_heights[r_min:r_max, c_min:c_max] + self._height_overlay[r_min:r_max, c_min:c_max]
            # Flatten should blend smoothly to avoid hard contour rings at brush edges.
            strength_scale = np.clip(strength / 25.0, 0.1, 6.0)
            blend_factor = np.clip((falloff ** 0.8) * strength_scale, 0.0, 1.0)
            diff = self._flatten_target_height - current_heights
            delta = diff * blend_factor
            if self._global_selection_mask is not None:
                delta *= self._global_selection_mask[r_min:r_max, c_min:c_max]
            self._height_overlay[r_min:r_max, c_min:c_max] += delta

        self._rerender_heightmap()

    def _rerender_heightmap(self, update_3d: bool = True):
        if self._base_heights is None:
            return

        if self._height_overlay is not None and self._base_heights.shape != self._height_overlay.shape:
            return

        combined = self._base_heights + self._height_overlay

        # Keep preview exposure anchored to the original terrain so sculpt strokes
        # don't globally brighten/darken the map while still avoiding hard clipping.
        min_h = float(self._base_min)
        max_h = float(self._base_max)

        # Stabilize very flat maps to avoid flicker and preserve usable contrast.
        if max_h - min_h < 512.0:
            mid_h = (min_h + max_h) * 0.5
            min_h = mid_h - 256.0
            max_h = mid_h + 256.0

        mid_h = (min_h + max_h) * 0.5
        half_range = max((max_h - min_h) * 0.5, 1.0)

        # Soft tone mapping: linear near the center, compresses extreme edits smoothly.
        normalized = (combined - min_h) / max(max_h - min_h, 1.0)
        normalized_heights = (np.clip(normalized, 0, 1) * 255).astype(np.uint8)

        h, w = normalized_heights.shape

        rgba_array = np.zeros((h, w, 4), dtype=np.uint8)
        rgba_array[..., 0] = normalized_heights # R
        rgba_array[..., 1] = normalized_heights # G
        rgba_array[..., 2] = normalized_heights # B
        rgba_array[..., 3] = 255                # Alpha

        if (
            self.current_mode in (8, 9, 10, 11)
            and self._global_selection_mask is not None
            and np.any(~self._global_selection_mask)
        ):
            # Show a subtle mask preview only while Mask tool is active.
            # The user wants the selected (editable) area to be tinted blue.
            editable = self._global_selection_mask
            rgba_array[editable, 2] = np.clip(rgba_array[editable, 2] + 25, 0, 255)
            rgba_array[editable, 1] = np.clip(rgba_array[editable, 1] * 0.9, 0, 255)

        if self._texture_overlay is not None:
            # Show a subtle tint for painted textures
            painted = self._texture_overlay > 0
            # Generate pseudo-random colors for different mat IDs to distinguish them
            mat_colors = (self._texture_overlay[painted] * 50) % 255
            rgba_array[painted, 0] = np.clip(rgba_array[painted, 0] * 0.7 + mat_colors * 0.3, 0, 255).astype(np.uint8)
            rgba_array[painted, 1] = np.clip(rgba_array[painted, 1] * 0.7 + (255 - mat_colors) * 0.3, 0, 255).astype(np.uint8)

        # Tile paint is 3D-only. Don't draw its coarse tile overlay or grid in 2D.
        if (
            getattr(self, "current_mode", None) == 13
            and self._tile_overlay is not None
            and self.view_stack.currentIndex() == 1
        ):
            tiles_y = getattr(self, "_tiles_y", 16)
            tiles_x = getattr(self, "_tiles_x", 16)
            img_h = h
            img_w = w

            for ty in range(tiles_y):
                for tx in range(tiles_x):
                    tile_id = int(self._tile_overlay[ty, tx])
                    if tile_id <= 0:
                        continue

                    y0 = ty * img_h // tiles_y
                    y1 = (ty + 1) * img_h // tiles_y
                    x0 = tx * img_w // tiles_x
                    x1 = (tx + 1) * img_w // tiles_x
                    color = self._tile_color(tile_id, alpha=120)
                    tint = np.array(
                        [color.red(), color.green(), color.blue()],
                        dtype=np.float32,
                    )
                    region = rgba_array[y0:y1, x0:x1, :3].astype(np.float32)
                    rgba_array[y0:y1, x0:x1, :3] = np.clip(
                        region * 0.55 + tint * 0.45,
                        0,
                        255,
                    ).astype(np.uint8)

            # a) Thin grid lines (1px, white, alpha 80) at tile boundaries:
            for tx in range(1, tiles_x):
                col = tx * img_w // tiles_x
                rgba_array[:, col, :3] = [230, 235, 245]
            for ty in range(1, tiles_y):
                row = ty * img_h // tiles_y
                rgba_array[row, :, :3] = [230, 235, 245]

        self._preview_img_data = rgba_array
        bytes_per_line = 4 * w
        qimg = QImage(
            self._preview_img_data.data,
            w,
            h,
            bytes_per_line,
            QImage.Format_RGBA8888,
        ).copy()
        self.map_image = qimg
        self.update_pixmap()
        if update_3d:
            self.update_3d_view(combined)

    def update_3d_view(self, heights, camera_override=None):
        if heights is None:
            return

        BE_BARRACKS_SIZE = (512.0, 512.0, 256.0)
        NF_BARRACKS_SIZE = (384.0, 384.0, 384.0)
        CV_SIZE = (192.0, 256.0, 128.0)
        REFINERY_SIZE = (256.0, 256.0, 384.0)

        # Downsample and transpose to keep world axes consistent:
        # heights is [row(y), col(x)] -> GLSurface expects z[x, y].
        orig_h, orig_w = heights.shape
        DS_SIZE = 128
        self._ds_size = DS_SIZE
        step_h = max(1, orig_h // DS_SIZE)
        step_w = max(1, orig_w // DS_SIZE)
        z_data = heights[::step_h, ::step_w][:DS_SIZE, :DS_SIZE].T

        # Center terrain around zero for camera stability/visibility.
        mean_h = float(np.mean(heights))
        self._terrain_mean_z = mean_h
        z_data = z_data - mean_h

        # Material-style preview: emulate blend alpha behavior used for VMF terrain.
        # This is slope-based (grass<->rock), with subtle height tinting for readability.
        height_min = float(np.min(heights))
        height_max = float(np.max(heights))
        height_range = max(1e-6, height_max - height_min)
        height_norm_full = (heights - height_min) / height_range

        cell_w = self.map_size_x / max(1, orig_w - 1)
        cell_h = self.map_size_y / max(1, orig_h - 1)
        dz_dy, dz_dx = np.gradient(heights, cell_h, cell_w)
        slope_full = np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy)

        slope_ds = slope_full[::step_h, ::step_w][:DS_SIZE, :DS_SIZE].T
        height_norm = height_norm_full[::step_h, ::step_w][:DS_SIZE, :DS_SIZE].T

        # Match pipeline defaults from terrain_pipeline.slope_to_alpha
        flat_threshold = 0.005
        steep_threshold = 0.03
        slope_t = np.clip(
            (slope_ds - flat_threshold) / (steep_threshold - flat_threshold),
            0.0,
            1.0,
        )
        slope_t = slope_t * slope_t * (3.0 - 2.0 * slope_t)  # smoothstep

        grass = np.array([0.22, 0.60, 0.24], dtype=np.float32)
        rock = np.array([0.57, 0.51, 0.43], dtype=np.float32)
        dirt = np.array([0.38, 0.30, 0.22], dtype=np.float32)
        peak = np.array([0.70, 0.67, 0.60], dtype=np.float32)

        rgb = (
            grass[np.newaxis, np.newaxis, :] * (1.0 - slope_t)[..., np.newaxis]
            + rock[np.newaxis, np.newaxis, :] * slope_t[..., np.newaxis]
        )

        low_blend = np.clip((0.18 - height_norm) / 0.18, 0.0, 1.0)
        rgb = (
            rgb * (1.0 - low_blend[..., np.newaxis])
            + dirt[np.newaxis, np.newaxis, :] * low_blend[..., np.newaxis]
        )

        high_blend = np.clip((height_norm - 0.75) / 0.25, 0.0, 1.0)
        rgb = (
            rgb * (1.0 - high_blend[..., np.newaxis])
            + peak[np.newaxis, np.newaxis, :] * high_blend[..., np.newaxis]
        )

        if getattr(self, "_texture_overlay", None) is not None:
            # Downsample texture overlay to match 3D vertices
            # _texture_overlay is same shape as original heights
            texture_ds = self._texture_overlay[::step_h, ::step_w][:DS_SIZE, :DS_SIZE].T
            painted = texture_ds > 0

            # Apply deterministic debug color tinting in 3D for painted tiles
            # We use the same deterministic pseudo-random math as 2D: (ID * 50) % 255
            mat_colors = (texture_ds[painted] * 50) % 255

            # Blend the tinted color over the base terrain colors (RGB space 0..1)
            # 2D does: R = R*0.7 + mat*0.3, G = G*0.7 + (255-mat)*0.3, B unchanged
            tint_r = mat_colors / 255.0
            tint_g = (255 - mat_colors) / 255.0

            rgb[painted, 0] = rgb[painted, 0] * 0.7 + tint_r * 0.3
            rgb[painted, 1] = rgb[painted, 1] * 0.7 + tint_g * 0.3
            # Blue remains at 70% of base to match 2D math exactly, but in 3D let's just scale it:
            rgb[painted, 2] = rgb[painted, 2] * 0.7

        colors = np.empty((rgb.shape[0], rgb.shape[1], 4), dtype=np.float32)
        colors[..., :3] = np.clip(rgb, 0.0, 1.0)
        colors[..., 3] = 1.0

        x_count, y_count = z_data.shape
        map_w = getattr(self, "map_size_x", orig_w)
        map_h = getattr(self, "map_size_y", orig_h)
        x = np.linspace(-map_w / 2, map_w / 2, x_count)
        y = np.linspace(-map_h / 2, map_h / 2, y_count)

        self._last_z_array = z_data
        self._last_x_array = x
        self._last_y_array = y

        # Build terrain mesh with vectorized NumPy — avoids GLSurfacePlotItem color crash.
        verts = np.empty((x_count * y_count, 3), dtype=np.float32)
        xx, yy = np.meshgrid(x.astype(np.float32), y.astype(np.float32), indexing="ij")
        verts[:, 0] = xx.reshape(-1)
        verts[:, 1] = yy.reshape(-1)
        verts[:, 2] = z_data.astype(np.float32).reshape(-1)

        # Vectorized face generation (two triangles per grid cell)
        ix = np.arange(x_count - 1, dtype=np.uint32)
        iy = np.arange(y_count - 1, dtype=np.uint32)
        ix, iy = np.meshgrid(ix, iy, indexing="ij")
        ix = ix.reshape(-1)
        iy = iy.reshape(-1)
        a = ix * y_count + iy
        b = a + 1
        c = (ix + 1) * y_count + iy
        d = c + 1
        tri0 = np.stack([a, b, d], axis=1)
        tri1 = np.stack([a, d, c], axis=1)
        faces = np.concatenate([tri0, tri1], axis=0).astype(np.uint32)

        # Per-vertex colors — flatten (x_count, y_count, 4) → (N, 4)
        vert_colors = colors.reshape(-1, 4).astype(np.float32)

        mesh = gl.MeshData(vertexes=verts, faces=faces)
        self._surface_item = gl.GLMeshItem(
            meshdata=mesh,
            smooth=False,
            drawFaces=True,
            drawEdges=False,
            shader='balloon',
            glOptions='opaque',
        )
        # 'balloon' shader reads per-vertex colors set on the MeshData
        self._surface_item.opts['meshdata'].setVertexColors(vert_colors)

        self.view_3d.clear()
        self.view_3d.addItem(self._surface_item)

        # Update view_3d properties so _pick_tile works correctly
        self.view_3d._tiles_x = getattr(self, "_tiles_x", 16)
        self.view_3d._tiles_y = getattr(self, "_tiles_y", 16)
        self.view_3d._map_size_x = map_w
        self.view_3d._map_size_y = map_h
        self.view_3d._terrain_mean_z = mean_h

        box_faces = np.array(
            [
                [0, 1, 2],
                [0, 2, 3],
                [4, 5, 6],
                [4, 6, 7],
                [0, 1, 5],
                [0, 5, 4],
                [1, 2, 6],
                [1, 6, 5],
                [2, 3, 7],
                [2, 7, 6],
                [3, 0, 4],
                [3, 4, 7],
            ],
            dtype=np.uint32,
        )

        def sample_terrain_height(world_x, world_y):
            if world_x is None or world_y is None:
                return None
            if self.map_size_x <= 0 or self.map_size_y <= 0:
                return None

            gx_ratio = (world_x - self.origin_x) / float(self.map_size_x)
            gy_ratio = (world_y - self.origin_y) / float(self.map_size_y)

            gx = int(round(gx_ratio * (heights.shape[1] - 1)))
            gy = int(round(gy_ratio * (heights.shape[0] - 1)))
            gx = max(0, min(heights.shape[1] - 1, gx))
            gy = max(0, min(heights.shape[0] - 1, gy))
            return float(heights[gy, gx])

        def to_preview_xy(world_x, world_y):
            sx = (world_x - self.origin_x) - (self.map_size_x / 2.0)
            sy = (world_y - self.origin_y) - (self.map_size_y / 2.0)
            return sx, sy

        def add_box(world_x, world_y, size_xyz, color_rgba, z_offset=0.0):
            terrain_z = sample_terrain_height(world_x, world_y)
            if terrain_z is None:
                return

            sx, sy = to_preview_xy(world_x, world_y)
            size_x, size_y, size_z = size_xyz

            verts = np.array(
                [
                    [0.0, 0.0, 0.0],
                    [size_x, 0.0, 0.0],
                    [size_x, size_y, 0.0],
                    [0.0, size_y, 0.0],
                    [0.0, 0.0, size_z],
                    [size_x, 0.0, size_z],
                    [size_x, size_y, size_z],
                    [0.0, size_y, size_z],
                ],
                dtype=np.float32,
            )
            mesh = gl.MeshData(vertexes=verts, faces=box_faces)
            box = gl.GLMeshItem(
                meshdata=mesh,
                smooth=False,
                drawFaces=True,
                drawEdges=True,
                color=color_rgba,
                edgeColor=(1.0, 1.0, 1.0, 0.35),
            )
            box.setGLOptions("translucent")
            box.translate(
                sx - (size_x / 2.0),
                sy - (size_y / 2.0),
                (terrain_z - mean_h) + z_offset,
            )
            self.view_3d.addItem(box)

        def add_mesh(world_x, world_y, classname, color_rgba, z_offset=0.0):
            terrain_z = sample_terrain_height(world_x, world_y)
            if terrain_z is None:
                return False

            model_path = MODELS_DIR / f"{classname}.obj"
            loaded = load_obj_mesh(model_path)
            if loaded is None:
                return False

            model_vertices, model_faces = loaded
            # Convert OBJ coordinates (Y-up) to preview coordinates (Z-up).
            # Keep right-handed orientation: x' = x, y' = -z, z' = y.
            vertices = np.empty_like(model_vertices)
            vertices[:, 0] = model_vertices[:, 0]
            vertices[:, 1] = -model_vertices[:, 2]
            vertices[:, 2] = model_vertices[:, 1]

            min_vals = vertices.min(axis=0)
            max_vals = vertices.max(axis=0)
            center_x = (min_vals[0] + max_vals[0]) * 0.5
            center_y = (min_vals[1] + max_vals[1]) * 0.5
            min_z = min_vals[2]

            vertices[:, 0] -= center_x
            vertices[:, 1] -= center_y
            vertices[:, 2] -= min_z

            mesh = gl.MeshData(vertexes=vertices, faces=model_faces)
            mesh_item = gl.GLMeshItem(
                meshdata=mesh,
                smooth=True,
                drawFaces=True,
                drawEdges=False,
                computeNormals=True,
                color=color_rgba,
            )
            mesh_item.setGLOptions("translucent")

            sx, sy = to_preview_xy(world_x, world_y)
            mesh_item.translate(sx, sy, (terrain_z - mean_h) + z_offset)
            self.view_3d.addItem(mesh_item)
            return True

        def add_entity(
            world_x,
            world_y,
            size_xyz,
            color_rgba,
            classname=None,
            allow_fallback=True,
            z_offset=0.0,
        ):
            if classname and add_mesh(
                world_x, world_y, classname, color_rgba, z_offset=z_offset
            ):
                return
            if allow_fallback:
                add_box(world_x, world_y, size_xyz, color_rgba, z_offset=z_offset)

        be_color = (0.0, 0.5, 1.0, 0.5)
        nf_color = (1.0, 0.0, 0.0, 0.5)
        res_color = (0.8, 0.8, 0.0, 0.5)

        has_imp_base = (
            self.imp_base
            and len(self.imp_base) == 2
            and self.imp_base[0] is not None
            and self.imp_base[1] is not None
        )
        if has_imp_base:
            imp_x, imp_y = self.imp_base

        has_nf_base = (
            self.nf_base
            and len(self.nf_base) == 2
            and self.nf_base[0] is not None
            and self.nf_base[1] is not None
        )
        if has_nf_base:
            nf_x, nf_y = self.nf_base

        if has_imp_base:
            add_entity(imp_x, imp_y, CV_SIZE, be_color, allow_fallback=False)
            add_entity(
                imp_x + 400.0,
                imp_y,
                BE_BARRACKS_SIZE,
                be_color,
                classname="emp_building_imp_barracks",
                allow_fallback=False,
                z_offset=16.0,
            )

        if has_nf_base:
            add_entity(nf_x, nf_y, CV_SIZE, nf_color, allow_fallback=False)
            add_entity(
                nf_x + 400.0,
                nf_y,
                NF_BARRACKS_SIZE,
                nf_color,
                classname="emp_building_nf_barracks",
                allow_fallback=False,
                z_offset=16.0,
            )

        for res in self.resources:
            if res and len(res) == 2:
                add_entity(
                    res[0],
                    res[1],
                    REFINERY_SIZE,
                    res_color,
                    classname="emp_resource_point",
                )

        if self.current_mode == 13:
            self._update_3d_tile_overlay()

        if camera_override is not None:
            self.view_3d.setCameraPosition(**camera_override)
        elif self.view_stack.currentIndex() != 1:
            cam_dist = max(self.map_size_x, self.map_size_y) * 1.2
            self.view_3d.setCameraPosition(
                distance=cam_dist,
                elevation=45,
                azimuth=-45,
            )

    def _3d_reset_camera(self):
        cam_dist = max(self.map_size_x, self.map_size_y) * 1.2
        self.view_3d.setCameraPosition(distance=cam_dist, elevation=45, azimuth=-45)

    def _3d_view_top(self):
        cam_dist = max(self.map_size_x, self.map_size_y) * 1.1
        self.view_3d.setCameraPosition(distance=cam_dist, elevation=89.9, azimuth=0)

    def _3d_view_iso(self):
        cam_dist = max(self.map_size_x, self.map_size_y) * 1.4
        self.view_3d.setCameraPosition(distance=cam_dist, elevation=35, azimuth=-45)

    def _3d_view_side(self):
        cam_dist = max(self.map_size_x, self.map_size_y) * 1.4
        self.view_3d.setCameraPosition(distance=cam_dist, elevation=0, azimuth=0)

    def _3d_zoom(self, factor: float):
        cur = self.view_3d.opts.get('distance', 10000)
        self.view_3d.setCameraPosition(distance=cur * factor)

    def _3d_toggle_wireframe(self, enabled: bool):
        if self._surface_item is not None:
            self._surface_item.setData(
                drawEdges=enabled,
                edgeColor=(0.6, 0.7, 0.9, 0.2),
            )
            self.view_3d.update()

    def _update_3d_tile_overlay(self):
        if getattr(self, "_last_z_array", None) is None or self._tile_overlay is None:
            return

        # Remove all existing tile overlay items
        for item in self._tile_mesh_items:
            if item in self.view_3d.items:
                self.view_3d.removeItem(item)
        self._tile_mesh_items.clear()

        z = self._last_z_array   # shape (ds_w, ds_h) — transposed heightmap
        ds_w, ds_h = z.shape
        x_arr = self._last_x_array   # shape (ds_w,)
        y_arr = self._last_y_array   # shape (ds_h,)
        tiles_x = self._tiles_x
        tiles_y = self._tiles_y
        Z_OFFSET = 8.0   # units above terrain so overlay sits on top

        for ty in range(tiles_y):
            for tx in range(tiles_x):
                tile_id = int(self._tile_overlay[ty, tx])
                if tile_id == 0:
                    continue

                # Pixel ranges in the (ds_w, ds_h) downsampled grid
                px0 = tx * ds_w // tiles_x
                px1 = min((tx + 1) * ds_w // tiles_x + 1, ds_w)
                py0 = ty * ds_h // tiles_y
                py1 = min((ty + 1) * ds_h // tiles_y + 1, ds_h)

                x_sub = x_arr[px0:px1]
                y_sub = y_arr[py0:py1]
                z_sub = z[px0:px1, py0:py1]
                nx, ny = z_sub.shape
                if nx < 2 or ny < 2:
                    continue

                # Vertices follow the terrain surface + Z_OFFSET
                xx, yy = np.meshgrid(x_sub, y_sub, indexing="ij")
                zz = z_sub + Z_OFFSET
                verts = np.stack([
                    xx.reshape(-1).astype(np.float32),
                    yy.reshape(-1).astype(np.float32),
                    zz.reshape(-1).astype(np.float32),
                ], axis=1)

                # Vectorised face generation
                iix = np.arange(nx - 1, dtype=np.uint32)
                iiy = np.arange(ny - 1, dtype=np.uint32)
                iix, iiy = np.meshgrid(iix, iiy, indexing="ij")
                iix = iix.reshape(-1)
                iiy = iiy.reshape(-1)
                a = iix * ny + iiy
                b = a + 1
                c = (iix + 1) * ny + iiy
                d = c + 1
                target = self.get_tile_paint_target()
                if target != "all":
                    dx = float(abs(x_sub[1] - x_sub[0])) if nx > 1 else 1.0
                    dy = float(abs(y_sub[1] - y_sub[0])) if ny > 1 else 1.0
                    dz_dx, dz_dy = np.gradient(z_sub, dx, dy)
                    slope = np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy)
                    quad_slope = (
                        slope[:-1, :-1]
                        + slope[1:, :-1]
                        + slope[:-1, 1:]
                        + slope[1:, 1:]
                    ) * 0.25
                    if target == "floor":
                        keep_quads = quad_slope.reshape(-1) < 0.55
                    else:
                        keep_quads = quad_slope.reshape(-1) > 0.2
                    if not np.any(keep_quads):
                        continue
                    a = a[keep_quads]
                    b = b[keep_quads]
                    c = c[keep_quads]
                    d = d[keep_quads]
                faces = np.concatenate([
                    np.stack([a, b, d], axis=1),
                    np.stack([a, d, c], axis=1),
                ], axis=0).astype(np.uint32)

                # Identify if this is a blend material to provide a visual hint
                id_to_material = {v: k for k, v in self._texture_mapping.items()}
                mat_name = id_to_material.get(tile_id, "").lower()
                is_blend = "blend" in mat_name

                hue = (tile_id * 137) % 360
                color = QColor.fromHsv(hue, 200, 220)
                face_color = (color.redF(), color.greenF(), color.blueF(), 0.65)

                # Cyan border for blend materials (smart alpha), black/gray for standard
                edge_color = (0.0, 1.0, 1.0, 1.0) if is_blend else (0.0, 0.0, 0.0, 0.6)

                mesh = gl.MeshData(vertexes=verts, faces=faces)
                item = gl.GLMeshItem(
                    meshdata=mesh,
                    color=face_color,
                    smooth=False,
                    drawFaces=True,
                    drawEdges=True,
                    edgeColor=edge_color,
                )
                item.setGLOptions('translucent')
                self.view_3d.addItem(item)
                self._tile_mesh_items.append(item)

        # Remove stale grid lines — tile edges from mesh above are sufficient
        for item in getattr(self, '_tile_grid_lines', []):
            if item in self.view_3d.items:
                self.view_3d.removeItem(item)
        self._tile_grid_lines = []

        self.view_3d.update()

    def set_material_theme(self, theme_name: str) -> None:
        """Fill paint-material combo from the active theme (mirrors sidebar Global Theme)."""
        if not theme_name or theme_name not in self._all_themes:
            return
        self.combo_texture.blockSignals(True)
        self.combo_texture.clear()
        theme_obj = self._all_themes[theme_name]
        mats_list = theme_obj.get("materials", []) if isinstance(theme_obj, dict) else theme_obj
        for mat in mats_list:
            path = mat["path"]
            if not is_blend_floor_material(path):
                continue
            name = mat.get("name", Path(path).name)
            self.combo_texture.addItem(name, path)
            idx = self.combo_texture.count() - 1
            self.combo_texture.setItemData(idx, f"{name}\n{path}", Qt.ItemDataRole.ToolTipRole)
        self.combo_texture.blockSignals(False)

    def set_themes(self, themes_data: dict, active_theme: Optional[str] = None) -> None:
        """Store theme definitions; paint list follows ``active_theme`` or first theme."""
        self._all_themes = themes_data
        names = sorted(self._all_themes.keys())
        chosen = active_theme if active_theme and active_theme in self._all_themes else (
            names[0] if names else ""
        )
        if chosen:
            self.set_material_theme(chosen)

    def _on_tile_clicked(self, tx, ty, erase=False):
        self._begin_tile_paint()
        self._paint_tile(tx, ty, erase=erase)
        self._end_tile_paint()

    def _on_thickness_slider_changed(self, value):
        self.thickness_label.setText(f"Width: {value}")
        self.current_base_width = float(value)
        # Note: We do NOT update existing lanes here, as requested.
        # This slider only affects NEWLY drawn lanes.

    def set_lane_scale(self, scale: float):
        """External entry point to sync from main GUI slider."""
        self.global_lane_scale = scale
        self._refresh_all_lane_visuals()

    def _refresh_all_lane_visuals(self):
        # Update existing edges visual representation based on global scale
        for item in self.scene.items():
            if hasattr(item, "_update_pen"):
                item._update_pen()

    def on_tab_changed(self, index):
        self.stacked_tools.setCurrentIndex(index)

        # Auto-select default tool for the new tab
        if index == 0:
            self.btn_raise.setChecked(True)
            self.on_tool_changed(8)
        elif index == 1:
            self.btn_move_ent.setChecked(True)
            self.on_tool_changed(200)
        elif index == 2:
            self.btn_move_lay.setChecked(True)
            self.on_tool_changed(300)

    def on_tool_changed(self, tid):
        previous_mode = getattr(self, "current_mode", 0)
        # Map duplicate virtual IDs to standard internal modes
        mode_mapping = {
            200: 0, # Entities Move -> Move
            300: 0, # Layout Move -> Move
            201: 5, # Entities Remove -> Remove
            301: 5  # Layout Remove -> Remove
        }

        actual_mode = mode_mapping.get(tid, tid)
        self.current_mode = actual_mode

        if actual_mode != 10:
            self._flatten_target_height = None

        if actual_mode == 13:
            self.combo_texture.setVisible(True)
        else:
            self.combo_texture.setVisible(False)
        self.combo_paint_target.setVisible(actual_mode == 13)

        if actual_mode == 13:
            self.lbl_mode_info.setText("TILE PAINT (WIP) – painting materials on 16x16 grid")
        else:
            self.lbl_mode_info.setText("")

        if actual_mode == 13 and self.view_stack.currentIndex() != 1:
            self.view_stack.setCurrentIndex(1)
            self.btn_toggle_3d.setText("2D View")
            self._update_3d_view(camera_override=self._camera_from_2d_view())
            
        # Trigger rerender to show/hide tile grid overlays correctly
        if actual_mode == 13 or previous_mode == 13:
            if actual_mode == 13:
                self._update_3d_tile_overlay()
            else:
                self._set_tile_hover(None, None)
                for item in getattr(self, '_tile_mesh_items', []):
                    if item in self.view_3d.items:
                        self.view_3d.removeItem(item)
                self._tile_mesh_items.clear()
                for item in getattr(self, '_tile_grid_lines', []):
                    if item in self.view_3d.items:
                        self.view_3d.removeItem(item)
                self._tile_grid_lines.clear()
                self.view_3d.update()
            self._rerender_heightmap()

        if actual_mode == 0:
            for item in self.scene.items():
                if isinstance(item, VisualNode) or hasattr(item, "is_fixed_entity"):
                    item.setFlag(QGraphicsItem.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        else:
            for item in self.scene.items():
                if isinstance(item, VisualNode) or hasattr(item, "is_fixed_entity"):
                    item.setFlag(QGraphicsItem.ItemIsMovable, False)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def get_tile_paint_target(self) -> str:
        if hasattr(self, "combo_paint_target"):
            target = self.combo_paint_target.currentData()
            if target in {"floor", "walls", "all"}:
                return target
        return getattr(self, "_tile_paint_target", "floor")

    def set_tile_paint_target(self, target: str):
        if target not in {"floor", "walls", "all"}:
            target = "floor"
        self._tile_paint_target = target
        if hasattr(self, "combo_paint_target"):
            idx = self.combo_paint_target.findData(target)
            if idx >= 0:
                old_block = self.combo_paint_target.blockSignals(True)
                self.combo_paint_target.setCurrentIndex(idx)
                self.combo_paint_target.blockSignals(old_block)

    def _on_tile_paint_target_changed(self):
        self._tile_paint_target = self.get_tile_paint_target()
        if getattr(self, "current_mode", None) == 13:
            self._update_3d_tile_overlay()
        self.layout_changed.emit()

    def clear_lanes(self):
        """Removes all lane-related items (nodes and edges) from the scene."""
        items_to_remove = []
        for item in self.scene.items():
            if isinstance(item, (VisualEdge, VisualFreehandEdge)):
                items_to_remove.append(item)
            elif isinstance(item, VisualNode):
                if item.node_type not in (ZoneType.BASE, ZoneType.RESOURCE):
                    items_to_remove.append(item)

        if items_to_remove:
            self.record_action("remove_multiple", list(items_to_remove))
            for item in items_to_remove:
                if isinstance(item, VisualNode):
                    item.edges.clear()
                self.scene.removeItem(item)

            self.drawing_lane = False
            self.current_freehand_path = []
            self.current_freehand_item = None
            self.lanes_changed.emit()
            self.layout_changed.emit()

    def clear_scene_nodes(self):
        # 1. Collect all layout items (Nodes, Edges, Paths)
        items_to_remove = []
        for item in self.scene.items():
            # If it's the map background, skip
            if item == self.map_pixmap_item:
                continue
            # If it's a grid line (usually QGraphicsLineItem but not VisualEdge)
            if hasattr(self, "grid_items") and item in self.grid_items:
                continue

            if isinstance(
                item, (VisualNode, VisualEdge, VisualFreehandEdge)
            ) or hasattr(item, "is_fixed_entity"):
                items_to_remove.append(item)
            elif type(item).__name__ in [
                "VisualNode",
                "VisualEdge",
                "VisualFreehandEdge",
                "FixedEntityItem",
            ]:
                items_to_remove.append(item)

        old_state = {
            "imp": self.imp_base,
            "nf": self.nf_base,
            "res": list(self.resources),
            "scene_items": list(items_to_remove),
            "overlay": self._height_overlay.copy()
            if self._height_overlay is not None
            else None,
            "mask": self._global_selection_mask.copy() if self._global_selection_mask is not None else None,
            "texture": self._texture_overlay.copy() if self._texture_overlay is not None else None,
            "tile_overlay": self._tile_overlay.copy() if self._tile_overlay is not None else None,
            "texture_mapping": dict(self._texture_mapping),
            "next_texture_id": self._next_texture_id,
        }

        self.history.append(("clear_all", old_state))
        self.redo_history.clear()

        if items_to_remove:
            for item in items_to_remove:
                # Disconnect edges from nodes to avoid dangling references
                if isinstance(item, VisualNode):
                    item.edges.clear()
                self.scene.removeItem(item)

        # 2. Reset internal state
        self.drawing_lane = False
        self.current_freehand_path = []
        self.current_freehand_item = None

        self.imp_base = (None, None)
        self.nf_base = (None, None)
        self.resources = []
        if self._height_overlay is not None:
            self._height_overlay[:] = 0
        if self._global_selection_mask is not None:
            self._global_selection_mask[:] = True
        if self._texture_overlay is not None:
            self._texture_overlay[:] = 0
        if self._tile_overlay is not None:
            self._tile_overlay[:] = 0
        self._texture_mapping = {}
        self._next_texture_id = 1
        self._rerender_heightmap()
        self.redraw_fixed_entities()
        self.base_moved.emit("imp", 0.0, 0.0)
        self.base_moved.emit("nf", 0.0, 0.0)
        self.lanes_changed.emit()
        self.layout_changed.emit()

    def record_action(self, action_type, item):
        self.history.append((action_type, item))
        self.redo_history.clear()
        self.lanes_changed.emit()
        self.layout_changed.emit()

    def undo(self):
        if not self.history:
            return
        action, item = self.history.pop()

        if action == "sculpt":
            current = (
                self._height_overlay.copy()
                if self._height_overlay is not None
                else None
            )
            self.redo_history.append(("sculpt", current))
            if self._height_overlay is not None and item is not None:
                self._height_overlay[:] = item
            elif self._height_overlay is not None:
                self._height_overlay[:] = 0
            self._rerender_heightmap()
            return
        elif action == "mask_change":
            current = (
                self._global_selection_mask.copy()
                if self._global_selection_mask is not None
                else None
            )
            self.redo_history.append(("mask_change", current))
            if self._global_selection_mask is not None and item is not None:
                self._global_selection_mask[:] = item
            elif self._global_selection_mask is not None:
                self._global_selection_mask[:] = True
            self._rerender_heightmap()
            return
        elif action == "texture_change":
            current = (
                self._texture_overlay.copy()
                if self._texture_overlay is not None
                else None
            )
            self.redo_history.append(("texture_change", current))
            if self._texture_overlay is not None and item is not None:
                self._texture_overlay[:] = item
            elif self._texture_overlay is not None:
                self._texture_overlay[:] = 0
            self._rerender_heightmap()
            return
        elif action == "tile_texture_change":
            current = (
                self._tile_overlay.copy()
                if self._tile_overlay is not None
                else None
            )
            self.redo_history.append(("tile_texture_change", current))
            if self._tile_overlay is not None and item is not None:
                self._tile_overlay[:] = item
            elif self._tile_overlay is not None:
                self._tile_overlay[:] = 0
            self._rerender_heightmap()
            return
        elif action == "add":
            self.scene.removeItem(item)
            self.redo_history.append(("add", item))
        elif action == "remove":
            self.scene.addItem(item)
            self.redo_history.append(("remove", item))
        elif action == "remove_multiple":
            for i in item:
                self.scene.addItem(i)
            self.redo_history.append(("remove_multiple", item))
        elif action == "set_imp":
            old_val, new_val = item
            self.imp_base = old_val
            self.redo_history.append(("set_imp", item))
            self.redraw_fixed_entities()
            val_to_emit = old_val if old_val and old_val[0] is not None else (0.0, 0.0)
            self.base_moved.emit("imp", val_to_emit[0], val_to_emit[1])
        elif action == "set_nf":
            old_val, new_val = item
            self.nf_base = old_val
            self.redo_history.append(("set_nf", item))
            self.redraw_fixed_entities()
            val_to_emit = old_val if old_val and old_val[0] is not None else (0.0, 0.0)
            self.base_moved.emit("nf", val_to_emit[0], val_to_emit[1])
        elif action == "set_res":
            old_val, new_val = item
            self.resources = old_val
            self.redo_history.append(("set_res", item))
            self.redraw_fixed_entities()
        elif action == "clear_all":
            old_state = item
            self.imp_base = old_state["imp"]
            self.nf_base = old_state["nf"]
            self.resources = old_state["res"]
            for scene_item in old_state["scene_items"]:
                self.scene.addItem(scene_item)
            if old_state["overlay"] is not None:
                self._height_overlay[:] = old_state["overlay"]
            if old_state.get("mask") is not None:
                self._global_selection_mask[:] = old_state["mask"]
            if old_state.get("texture") is not None:
                self._texture_overlay[:] = old_state["texture"]
            if old_state.get("tile_overlay") is not None:
                self._tile_overlay[:] = old_state["tile_overlay"]
            self._rerender_heightmap()
            self.redo_history.append(("clear_all", old_state))
            self.redraw_fixed_entities()
            imp_emit = (
                self.imp_base
                if self.imp_base and self.imp_base[0] is not None
                else (0.0, 0.0)
            )
            nf_emit = (
                self.nf_base
                if self.nf_base and self.nf_base[0] is not None
                else (0.0, 0.0)
            )
            self.base_moved.emit("imp", imp_emit[0], imp_emit[1])
            self.base_moved.emit("nf", nf_emit[0], nf_emit[1])
        self.layout_changed.emit()

    def redo(self):
        if not self.redo_history:
            return
        action, item = self.redo_history.pop()

        if action == "sculpt":
            current = (
                self._height_overlay.copy()
                if self._height_overlay is not None
                else None
            )
            self.history.append(("sculpt", current))
            if self._height_overlay is not None and item is not None:
                self._height_overlay[:] = item
            elif self._height_overlay is not None:
                self._height_overlay[:] = 0
            self._rerender_heightmap()
            return
        elif action == "mask_change":
            current = (
                self._global_selection_mask.copy()
                if self._global_selection_mask is not None
                else None
            )
            self.history.append(("mask_change", current))
            if self._global_selection_mask is not None and item is not None:
                self._global_selection_mask[:] = item
            elif self._global_selection_mask is not None:
                self._global_selection_mask[:] = True
            self._rerender_heightmap()
            return
        elif action == "texture_change":
            current = (
                self._texture_overlay.copy()
                if self._texture_overlay is not None
                else None
            )
            self.history.append(("texture_change", current))
            if self._texture_overlay is not None and item is not None:
                self._texture_overlay[:] = item
            elif self._texture_overlay is not None:
                self._texture_overlay[:] = 0
            self._rerender_heightmap()
            return
        elif action == "tile_texture_change":
            current = (
                self._tile_overlay.copy()
                if self._tile_overlay is not None
                else None
            )
            self.history.append(("tile_texture_change", current))
            if self._tile_overlay is not None and item is not None:
                self._tile_overlay[:] = item
            elif self._tile_overlay is not None:
                self._tile_overlay[:] = 0
            self._rerender_heightmap()
            return
        elif action == "add":
            self.scene.addItem(item)
            self.history.append(("add", item))
        elif action == "remove":
            self.scene.removeItem(item)
            self.history.append(("remove", item))
        elif action == "remove_multiple":
            for i in item:
                self.scene.removeItem(i)
            self.history.append(("remove_multiple", item))
        elif action == "set_imp":
            old_val, new_val = item
            self.imp_base = new_val
            self.history.append(("set_imp", item))
            self.redraw_fixed_entities()
            val_to_emit = new_val if new_val and new_val[0] is not None else (0.0, 0.0)
            self.base_moved.emit("imp", val_to_emit[0], val_to_emit[1])
        elif action == "set_nf":
            old_val, new_val = item
            self.nf_base = new_val
            self.history.append(("set_nf", item))
            self.redraw_fixed_entities()
            val_to_emit = new_val if new_val and new_val[0] is not None else (0.0, 0.0)
            self.base_moved.emit("nf", val_to_emit[0], val_to_emit[1])
        elif action == "set_res":
            old_val, new_val = item
            self.resources = new_val
            self.history.append(("set_res", item))
            self.redraw_fixed_entities()
        elif action == "clear_all":
            old_state = item
            self.imp_base = (None, None)
            self.nf_base = (None, None)
            self.resources = []
            for scene_item in old_state["scene_items"]:
                self.scene.removeItem(scene_item)
            if self._height_overlay is not None:
                self._height_overlay[:] = 0
            if self._global_selection_mask is not None:
                self._global_selection_mask[:] = True
            if self._texture_overlay is not None:
                self._texture_overlay[:] = 0
            if self._tile_overlay is not None:
                self._tile_overlay[:] = 0
            self._rerender_heightmap()
            self.history.append(("clear_all", old_state))
            self.redraw_fixed_entities()
            self.base_moved.emit("imp", 0.0, 0.0)
            self.base_moved.emit("nf", 0.0, 0.0)
        self.layout_changed.emit()

    def on_wheel_event(self, event):
        zoom_factor = 1.15
        if event.angleDelta().y() < 0:
            zoom_factor = 1.0 / zoom_factor
        self.view.scale(zoom_factor, zoom_factor)

    def on_mouse_press(self, event):
        self._active_mouse_button = event.button()

        if event.button() == Qt.MiddleButton:
            self.panning = True
            self.pan_start_pos = event.position()
            self.view.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        scene_pos = self.view.mapToScene(event.pos())

        if self.current_mode == 2:  # BE Base
            old_val = self.imp_base
            new_val = (scene_pos.x(), scene_pos.y())
            self.record_action("set_imp", (old_val, new_val))
            self.imp_base = new_val
            self.redraw_fixed_entities()
            self.base_moved.emit("imp", scene_pos.x(), scene_pos.y())
        elif self.current_mode == 7:  # NF Base
            old_val = self.nf_base
            new_val = (scene_pos.x(), scene_pos.y())
            self.record_action("set_nf", (old_val, new_val))
            self.nf_base = new_val
            self.redraw_fixed_entities()
            self.base_moved.emit("nf", scene_pos.x(), scene_pos.y())
        elif self.current_mode == 5:  # Remove
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if isinstance(item, (VisualNode, VisualEdge, VisualFreehandEdge)) or type(
                item
            ).__name__ in ["VisualNode", "VisualEdge", "VisualFreehandEdge"]:
                items_to_remove = [item]
                if isinstance(item, VisualNode) or type(item).__name__ == "VisualNode":
                    for edge in getattr(item, "edges", []):
                        if edge in self.scene.items() and edge not in items_to_remove:
                            items_to_remove.append(edge)

                self.record_action("remove_multiple", items_to_remove)
                for i in items_to_remove:
                    self.scene.removeItem(i)
            elif hasattr(item, "is_fixed_entity"):
                if item.entity_type == "imp":
                    old_val = self.imp_base
                    self.record_action("set_imp", (old_val, (None, None)))
                    self.imp_base = (None, None)
                    self.redraw_fixed_entities()
                    self.base_moved.emit("imp", 0.0, 0.0)
                elif item.entity_type == "nf":
                    old_val = self.nf_base
                    self.record_action("set_nf", (old_val, (None, None)))
                    self.nf_base = (None, None)
                    self.redraw_fixed_entities()
                    self.base_moved.emit("nf", 0.0, 0.0)
                elif item.entity_type == "res":
                    old_val = list(self.resources)
                    new_val = list(self.resources)
                    if 0 <= item.index < len(new_val):
                        new_val.pop(item.index)
                    self.record_action("set_res", (old_val, new_val))
                    self.resources = new_val
                    self.redraw_fixed_entities()
                    # Trigger an update by emitting something generic, or just rely on layout_changed
                    self.layout_changed.emit()
        elif self.current_mode == 3:  # Add Resource
            old_res_list = list(self.resources)
            new_res_list = list(self.resources)
            new_res_list.append((scene_pos.x(), scene_pos.y()))
            self.record_action("set_res", (old_res_list, new_res_list))
            self.resources = new_res_list
            self.redraw_fixed_entities()
            self.resource_added.emit(scene_pos.x(), scene_pos.y())
        elif self.current_mode in (8, 9, 10, 11, 12, 13):
            self._sculpting = True
            if self.current_mode == 10 and self._base_heights is not None:
                # Sample target height for flatten tool at initial click
                h, w = self._base_heights.shape
                gx = int((scene_pos.x() - self.origin_x) / self.map_size_x * w)
                gy = int((scene_pos.y() - self.origin_y) / self.map_size_y * h)
                gx = max(0, min(w - 1, gx))
                gy = max(0, min(h - 1, gy))
                self._flatten_target_height = float(self._base_heights[gy, gx] + (self._height_overlay[gy, gx] if self._height_overlay is not None else 0))

            if self.current_mode == 13:
                self._begin_tile_paint()
            elif self.current_mode == 11:
                snapshot = (
                    self._global_selection_mask.copy()
                    if self._global_selection_mask is not None
                    else None
                )
                self.history.append(("mask_change", snapshot))
                self.history.append(("texture_change", snapshot))
            else:
                # Save overlay snapshot for undo
                snapshot = (
                    self._height_overlay.copy()
                    if self._height_overlay is not None
                    else None
                )
                self.history.append(("sculpt", snapshot))
            self.redo_history.clear()
            self._apply_brush(scene_pos.x(), scene_pos.y(), self.current_mode)
        elif self.current_mode == 6:  # Draw Lane
            self.drawing_lane = True
            self.current_freehand_path = [scene_pos]
            item = self.scene.itemAt(scene_pos, self.view.transform())
            self.freehand_start_node = item if isinstance(item, VisualNode) else None

            # Temporary item to draw while dragging
            self.current_freehand_item = VisualFreehandEdge(
                self.current_freehand_path, self.current_base_width
            )
            self.scene.addItem(self.current_freehand_item)

        # Do not block standard view events
        pass

    def on_mouse_move(self, event):
        if self.drawing_lane and self.current_freehand_item:
            scene_pos = self.view.mapToScene(event.pos())
            # only add points if we moved far enough (smoothness)
            if (scene_pos - self.current_freehand_path[-1]).manhattanLength() > 10:
                self.current_freehand_path.append(scene_pos)
                self.current_freehand_item.points = self.current_freehand_path
                self.current_freehand_item.update()
            return

        if self._sculpting and self.current_mode in (8, 9, 10, 11, 12, 13):
            scene_pos = self.view.mapToScene(event.pos())
            self._apply_brush(scene_pos.x(), scene_pos.y(), self.current_mode)
            return

        if self.panning:
            delta = event.position() - self.pan_start_pos
            self.view.horizontalScrollBar().setValue(
                self.view.horizontalScrollBar().value() - delta.x()
            )
            self.view.verticalScrollBar().setValue(
                self.view.verticalScrollBar().value() - delta.y()
            )
            self.pan_start_pos = event.position()
            event.accept()
            return

        if self.current_mode == 13:
            scene_pos = self.view.mapToScene(event.pos())
            tx, ty = self._scene_to_tile(scene_pos.x(), scene_pos.y())
            self._set_tile_hover(tx, ty)
            return
        pass

    def on_mouse_release(self, event):
        self._active_mouse_button = None

        if self._sculpting:
            self._sculpting = False
            if self.current_mode == 13:
                self._end_tile_paint()
            self._flatten_target_height = None
            return

        if self.drawing_lane:
            self.drawing_lane = False
            if len(self.current_freehand_path) > 1:
                scene_pos = self.view.mapToScene(event.pos())
                item = self.scene.itemAt(scene_pos, self.view.transform())
                end_node = item if isinstance(item, VisualNode) else None

                # Replace temp item with final item
                self.scene.removeItem(self.current_freehand_item)

                final_edge = VisualFreehandEdge(
                    list(self.current_freehand_path),
                    self.current_base_width,
                    start_node=self.freehand_start_node,
                    end_node=end_node,
                )
                self.scene.addItem(final_edge)
                self.record_action("add", final_edge)

                if self.freehand_start_node:
                    self.freehand_start_node.edges.append(final_edge)
                if end_node:
                    end_node.edges.append(final_edge)
            else:
                if self.current_freehand_item:
                    self.scene.removeItem(self.current_freehand_item)

            self.current_freehand_item = None
            self.current_freehand_path = []
            return

        if event.button() == Qt.MiddleButton:
            self.panning = False
            self.view.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        pass

    def get_layout_from_editor(self):
        nodes = []
        connections = []
        node_map = {}

        # Pull visual nodes
        for item in self.scene.items():
            if isinstance(item, VisualNode):
                ln = LayoutNode(
                    item.scenePos().x(),
                    item.scenePos().y(),
                    item.clear_radius,
                    item.node_type,
                )
                nodes.append(ln)
                node_map[item] = ln

        # Pull visual edges
        for item in self.scene.items():
            if isinstance(item, VisualEdge):
                conn = LayoutConnection(
                    start_node=node_map[item.start_node],
                    end_node=node_map[item.end_node],
                    width=item.logical_width,
                    type=ZoneType.MAIN_LANE,
                )
                connections.append(conn)
            elif isinstance(item, VisualFreehandEdge):
                # We need fake nodes if start/end nodes are None to support standalone paths
                sn = node_map.get(item.start_node)
                en = node_map.get(item.end_node)

                if not sn and item.points:
                    sn = LayoutNode(
                        item.points[0].x(), item.points[0].y(), 100, ZoneType.MAIN_LANE
                    )
                    nodes.append(sn)
                if not en and item.points:
                    en = LayoutNode(
                        item.points[-1].x(),
                        item.points[-1].y(),
                        100,
                        ZoneType.MAIN_LANE,
                    )
                    nodes.append(en)

                path_points = [(p.x(), p.y()) for p in item.points]
                conn = LayoutConnection(
                    start_node=sn,
                    end_node=en,
                    width=item.logical_width,
                    type=ZoneType.MAIN_LANE,
                    path_points=path_points,
                )
                connections.append(conn)

        # Resources are now exclusively tracked by self.resources, not VisualNodes
        return (
            nodes,
            connections,
            list(self.resources),
            self._height_overlay.copy() if getattr(self, "_height_overlay", None) is not None else None,
            self._global_selection_mask.copy() if getattr(self, "_global_selection_mask", None) is not None else None,
            self._texture_overlay.copy() if getattr(self, "_texture_overlay", None) is not None else None,
            dict(getattr(self, "_texture_mapping", {})),
            getattr(self, "_next_texture_id", 1),
            self._tile_overlay.copy() if getattr(self, "_tile_overlay", None) is not None else None
        )

    def set_layout_to_editor(self, nodes, connections, resources, imp_base, nf_base, height_overlay, global_mask, texture_overlay=None, texture_mapping=None, next_texture_id=1, tile_overlay=None, tile_paint_target="floor"):
        """Restore the editor state from a saved project."""
        # 1. Clear current state (without adding to history)
        items_to_remove = []
        for item in self.scene.items():
            if item == self.map_pixmap_item:
                continue
            if hasattr(self, "grid_items") and item in self.grid_items:
                continue
            if isinstance(item, (VisualNode, VisualEdge, VisualFreehandEdge)) or hasattr(item, "is_fixed_entity"):
                items_to_remove.append(item)

        for item in items_to_remove:
            if isinstance(item, VisualNode):
                item.edges.clear()
            self.scene.removeItem(item)

        # 2. Reset internal data
        self.imp_base = imp_base if imp_base else (None, None)
        self.nf_base = nf_base if nf_base else (None, None)
        self.resources = resources if resources else []
        
        # Ensure arrays are correct
        if height_overlay is not None:
            self._height_overlay = height_overlay
        if global_mask is not None:
            self._global_selection_mask = global_mask
        if texture_overlay is not None:
            self._texture_overlay = texture_overlay
        if texture_mapping is not None:
            self._texture_mapping = texture_mapping
            self._next_texture_id = next_texture_id
            
        self.history.clear()
        self.redo_history.clear()

        # 3. Reconstruct VisualNodes
        node_to_vis = {}
        for node in nodes:
            vis_node = VisualNode(node.x, node.y, node.radius, node.type, self.scene)
            node_to_vis[node] = vis_node

        # 4. Reconstruct VisualEdges
        for conn in connections:
            start_vis = node_to_vis.get(conn.start_node)
            end_vis = node_to_vis.get(conn.end_node)
            
            if conn.path_points:
                points = [QPointF(p[0], p[1]) for p in conn.path_points]
                vis_edge = VisualFreehandEdge(points, conn.width, start_vis, end_vis)
                self.scene.addItem(vis_edge)
                if start_vis:
                    start_vis.edges.append(vis_edge)
                if end_vis:
                    end_vis.edges.append(vis_edge)
            else:
                if start_vis and end_vis:
                    vis_edge = VisualEdge(start_vis, end_vis)
                    vis_edge.base_width = conn.width
                    vis_edge._update_pen()
                    self.scene.addItem(vis_edge)
                    start_vis.edges.append(vis_edge)
                    end_vis.edges.append(vis_edge)

        if tile_overlay is not None:
            self._tile_overlay = tile_overlay.copy()
        elif hasattr(self, "_tiles_x") and hasattr(self, "_tiles_y"):
            self._tile_overlay = np.zeros((self._tiles_y, self._tiles_x), dtype=np.int32)
        self.set_tile_paint_target(tile_paint_target)

        # 5. Refresh UI
        self._rerender_heightmap()
        self.redraw_fixed_entities()
        self.layout_changed.emit()

    def toggle_3d_view(self):
        current_idx = self.view_stack.currentIndex()
        if current_idx == 0:
            self.view_stack.setCurrentIndex(1)
            self.btn_toggle_3d.setText("2D View")
            self._update_3d_view(camera_override=self._camera_from_2d_view())
        else:
            if self.current_mode == 13:
                if hasattr(self, "btn_tile_paint") and self.btn_tile_paint is not None:
                    self.btn_tile_paint.setChecked(True)
                self.on_tool_changed(13)
            self.view_stack.setCurrentIndex(0)
            self.btn_toggle_3d.setText("3D View")

    def update_clear_radii(self, base_radius, resource_radius, lane_radius=None):
        """Update clear_radius on all VisualNode and FixedEntityItem items."""
        if lane_radius is not None:
            self.lane_node_radius = lane_radius
            
        for item in self.scene.items():
            if isinstance(item, VisualNode):
                if item.node_type == ZoneType.BASE:
                    if item.clear_radius != base_radius or getattr(item, 'lane_radius', -1) != lane_radius:
                        item.prepareGeometryChange()
                        item.clear_radius = base_radius
                        if lane_radius is not None:
                            item.lane_radius = lane_radius
                        item.update()
                elif item.node_type in (ZoneType.RESOURCE, ZoneType.WILDERNESS):
                    if item.clear_radius != resource_radius:
                        item.prepareGeometryChange()
                        item.clear_radius = resource_radius
                        item.update()
            elif hasattr(item, "is_fixed_entity") and hasattr(item, "clear_radius"):
                # FixedEntityItem: update based on entity_type
                if item.entity_type in ("imp", "nf"):
                    if item.clear_radius != base_radius or getattr(item, 'lane_radius', -1) != lane_radius:
                        item.prepareGeometryChange()
                        item.clear_radius = base_radius
                        if lane_radius is not None:
                            item.lane_radius = lane_radius
                        item.update()
                elif item.entity_type == "res":
                    if item.clear_radius != resource_radius:
                        item.prepareGeometryChange()
                        item.clear_radius = resource_radius
                        item.update()
