import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtWidgets import QStackedWidget


from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QButtonGroup,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QLabel,
    QSlider,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
)
import pyqtgraph.opengl as gl
from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QPointF
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QImage,
    QPixmap,
    QPolygon,
    QVector3D,
)
from PySide6.QtSvg import QSvgRenderer

from src.terrain_spec import ZoneType, LayoutNode, LayoutConnection


# Global SVG Renderers
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent.parent

ICONS_DIR = PROJECT_ROOT / "icons"
from PySide6.QtCore import QByteArray


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
    lane_width_changed = Signal(float)  # Emits absolute width in units

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Toolbar (Scrollable) ──
        toolbar_scroll = QScrollArea()
        toolbar_scroll.setWidgetResizable(True)
        toolbar_scroll.setFrameShape(QScrollArea.NoFrame)
        toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        toolbar_scroll.setFixedHeight(40)  # Keep it compact

        toolbar_widget = QWidget()
        self.tools_row = QHBoxLayout(toolbar_widget)
        self.tools_row.setSpacing(6)
        self.tools_row.setContentsMargins(4, 0, 4, 0)

        self.tool_group = QButtonGroup(self)
        self.modes = {}

        # Helper to add section labels
        def add_separator(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #888; font-weight: bold; font-size: 9px; margin-left: 4px; margin-right: 2px;"
            )
            self.tools_row.addWidget(lbl)

        # 1. Selection & Manipulation
        add_separator("TOOLS")

        btn_move = QPushButton("Move")
        btn_move.setCheckable(True)
        btn_move.setObjectName("ToolButton")
        self.tool_group.addButton(btn_move, 0)
        self.tools_row.addWidget(btn_move)

        btn_remove = QPushButton("Remove")
        btn_remove.setCheckable(True)
        btn_remove.setObjectName("ToolButtonRed")
        self.tool_group.addButton(btn_remove, 5)
        self.tools_row.addWidget(btn_remove)

        # 1. Layout
        add_separator("LAYOUT")

        btn_link = QPushButton("Link")
        btn_link.setCheckable(True)
        btn_link.setObjectName("ToolButton")
        self.tool_group.addButton(btn_link, 4)
        self.tools_row.addWidget(btn_link)

        btn_draw = QPushButton("Lane")
        btn_draw.setCheckable(True)
        btn_draw.setObjectName("ToolButton")
        self.tool_group.addButton(btn_draw, 6)
        self.tools_row.addWidget(btn_draw)

        # Thickness selector for drawing lanes
        # Wrapped in a sub-layout for tighter grouping
        self.thickness_widget = QWidget()
        thick_layout = QHBoxLayout(self.thickness_widget)
        thick_layout.setContentsMargins(0, 0, 0, 0)
        thick_layout.setSpacing(2)

        self.thickness_label = QLabel("Width: 600")
        self.thickness_label.setStyleSheet("color: #ccc; font-size: 11px;")

        self.thickness_slider = QSlider(Qt.Horizontal)
        self.thickness_slider.setRange(0, 800)
        self.thickness_slider.setValue(600)
        self.thickness_slider.setFixedWidth(80)
        self.thickness_slider.valueChanged.connect(self._on_thickness_slider_changed)

        thick_layout.addWidget(self.thickness_label)
        thick_layout.addWidget(self.thickness_slider)

        # Hide them initially
        self.thickness_widget.setVisible(False)
        self.tools_row.addWidget(self.thickness_widget)

        # 3. Entities
        add_separator("ENTITIES")

        btn_be = QPushButton("Set BE")
        btn_be.setCheckable(True)
        btn_be.setObjectName("ToolButtonBlue")
        self.tool_group.addButton(btn_be, 2)
        self.tools_row.addWidget(btn_be)

        # We need a new ID for NF Base since previous code overwrote it or merged it incorrectly
        # Old map: 1: Add Node, 2: Add Base, 3: Add Resource
        # Let's use 7 for Set NF Base
        btn_nf = QPushButton("Set NF")
        btn_nf.setCheckable(True)
        btn_nf.setObjectName("ToolButtonRed")  # NF is typically red in this UI
        self.tool_group.addButton(btn_nf, 7)
        self.tools_row.addWidget(btn_nf)

        btn_res = QPushButton("Add Res")
        btn_res.setCheckable(True)
        btn_res.setObjectName("ToolButtonGreen")
        self.tool_group.addButton(btn_res, 3)
        self.tools_row.addWidget(btn_res)

        # 4. Sculpting
        add_separator("SCULPT")

        btn_raise = QPushButton("Raise ▲")
        btn_raise.setCheckable(True)
        btn_raise.setObjectName("ToolButtonGreen")
        self.tool_group.addButton(btn_raise, 8)
        self.tools_row.addWidget(btn_raise)

        btn_lower = QPushButton("Lower ▼")
        btn_lower.setCheckable(True)
        btn_lower.setObjectName("ToolButtonRed")
        self.tool_group.addButton(btn_lower, 9)
        self.tools_row.addWidget(btn_lower)

        # Brush controls (shown for sculpt tools)
        self.brush_widget = QWidget()
        brush_layout = QHBoxLayout(self.brush_widget)
        brush_layout.setContentsMargins(0, 0, 0, 0)
        brush_layout.setSpacing(2)

        self.brush_size_label = QLabel("Size: 512")
        self.brush_size_label.setStyleSheet("color: #ccc; font-size: 11px;")
        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_slider.setRange(64, 4096)
        self.brush_size_slider.setValue(512)
        self.brush_size_slider.setFixedWidth(80)
        self.brush_size_slider.valueChanged.connect(
            lambda v: self.brush_size_label.setText(f"Size: {v}")
        )

        self.brush_strength_label = QLabel("Str: 50")
        self.brush_strength_label.setStyleSheet("color: #ccc; font-size: 11px;")
        self.brush_strength_slider = QSlider(Qt.Horizontal)
        self.brush_strength_slider.setRange(5, 200)
        self.brush_strength_slider.setValue(50)
        self.brush_strength_slider.setFixedWidth(60)
        self.brush_strength_slider.valueChanged.connect(
            lambda v: self.brush_strength_label.setText(f"Str: {v}")
        )

        brush_layout.addWidget(self.brush_size_label)
        brush_layout.addWidget(self.brush_size_slider)
        brush_layout.addWidget(self.brush_strength_label)
        brush_layout.addWidget(self.brush_strength_slider)
        self.brush_widget.setVisible(False)
        self.tools_row.addWidget(self.brush_widget)

        self.tool_group.button(0).setChecked(True)
        self.current_mode = 0
        self.tool_group.idClicked.connect(self.on_tool_changed)

        self.tools_row.addStretch()

        # 4. Actions
        add_separator("ACTIONS")

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setObjectName("SmallButton")
        self.btn_undo.clicked.connect(self.undo)
        self.tools_row.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setObjectName("SmallButton")
        self.btn_redo.clicked.connect(self.redo)
        self.tools_row.addWidget(self.btn_redo)

        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.setObjectName("SmallButton")
        self.btn_clear.clicked.connect(self.clear_scene_nodes)
        self.tools_row.addWidget(self.btn_clear)

        self.btn_toggle_3d = QPushButton("3D View")
        self.btn_toggle_3d.setObjectName("SmallButton")
        self.btn_toggle_3d.clicked.connect(self.toggle_3d_view)
        self.tools_row.addWidget(self.btn_toggle_3d)

        # Action history for Undo/Redo
        self.history = []
        self.redo_history = []

        toolbar_scroll.setWidget(toolbar_widget)
        layout.addWidget(toolbar_scroll)

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

        self.scene = QGraphicsScene()
        self.view = CustomGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.setStyleSheet("background-color: #0d0d10; border: 1px solid #2e2e36;")

        self.view_3d = gl.GLViewWidget()

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.view)
        self.view_stack.addWidget(self.view_3d)

        layout.addWidget(self.view_stack)

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
        self.draw_grid()

        self.link_start_node = None

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
        self._sculpting = False

        # Clear radii for entity zones
        self.base_clear_radius = 512
        self.resource_clear_radius = 256
        self.lane_node_radius = 512


    def draw_grid(self):
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
    ):
        self.map_image = image
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.map_size_x = size_x
        self.map_size_y = size_y
        self.grid_size = max(1, int(tile_size))

        self.scene.setSceneRect(
            self.origin_x, self.origin_y, self.map_size_x, self.map_size_y
        )
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
        base_r = getattr(self, "base_clear_radius", 512)
        res_r = getattr(self, "resource_clear_radius", 256)
        lane_r = getattr(self, "lane_node_radius", 512)

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
                    painter.drawText(0, -95, "⚠")

                # Draw clearance radius
                if self.clear_radius > 0:
                    painter.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.DashLine))
                    painter.setBrush(QBrush(QColor(255, 255, 255, 5)))
                    r_clear = self.clear_radius
                    painter.drawEllipse(
                        QRectF(-r_clear, -r_clear, r_clear * 2, r_clear * 2)
                    )

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
            sy = world_y - self.origin_y - (self.map_size_y / 2.0)
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

    def set_raw_heights(self, heights: np.ndarray):

        self._base_heights = heights.astype(np.float64).copy()
        self._base_min = float(self._base_heights.min())
        self._base_max = float(self._base_heights.max())
        if self._height_overlay is None or self._height_overlay.shape != heights.shape:
            self._height_overlay = np.zeros_like(self._base_heights)

        # Always re-render to ensure consistent normalization (e.g. neutral gray for flat maps)
        self._rerender_heightmap()
        self._update_3d_view()

    def _apply_brush(self, scene_x: float, scene_y: float, raise_terrain: bool):
        if self._base_heights is None:
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

        delta = falloff * strength * (1.0 if raise_terrain else -1.0)
        self._height_overlay[r_min:r_max, c_min:c_max] += delta

        self._rerender_heightmap()

    def _rerender_heightmap(self):
        if self._base_heights is None:
            return

        combined = self._base_heights + self._height_overlay

        # Keep preview exposure anchored to the original terrain so sculpting does not
        # brighten/darken the whole map as local edits change extreme min/max values.
        min_h = float(self._base_min)
        max_h = float(self._base_max)

        # Stabilize very flat maps to avoid flicker and preserve usable contrast.
        if max_h - min_h < 512.0:
            mid_h = (min_h + max_h) * 0.5
            min_h = mid_h - 256.0
            max_h = mid_h + 256.0

        if max_h > min_h:
            normalized = (combined - min_h) / (max_h - min_h)
        else:
            normalized = np.full_like(combined, 0.5)

        img_data = (np.clip(normalized, 0, 1) * 255).astype(np.uint8)
        h, w = img_data.shape

        self._preview_img_data = img_data
        qimg = QImage(
            self._preview_img_data.data,
            w,
            h,
            w,
            QImage.Format_Grayscale8,
        )
        self.map_image = qimg
        self.update_pixmap()
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
        step_h = max(1, orig_h // 128)
        step_w = max(1, orig_w // 128)
        z_data = heights[::step_h, ::step_w].T

        # Center terrain around zero for camera stability/visibility.
        mean_h = float(np.mean(heights))
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

        slope_ds = slope_full[::step_h, ::step_w].T
        height_norm = height_norm_full[::step_h, ::step_w].T

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

        colors = np.empty((rgb.shape[0], rgb.shape[1], 4), dtype=np.float32)
        colors[..., :3] = np.clip(rgb, 0.0, 1.0)
        colors[..., 3] = 1.0

        x_count, y_count = z_data.shape
        map_w = getattr(self, "map_size_x", orig_w)
        map_h = getattr(self, "map_size_y", orig_h)
        x = np.linspace(-map_w / 2, map_w / 2, x_count)
        # Reverse Y linspace so lower index maps to the top (+y), matching 2D coordinate view
        y = np.linspace(map_h / 2, -map_h / 2, y_count)

        surface = gl.GLSurfacePlotItem(
            x=x, y=y, z=z_data, colors=colors, computeNormals=False, smooth=True
        )

        self.view_3d.clear()
        self.view_3d.addItem(surface)

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

        if camera_override is not None:
            self.view_3d.setCameraPosition(**camera_override)
        elif self.view_stack.currentIndex() != 1:
            cam_dist = max(self.map_size_x, self.map_size_y) * 1.2
            self.view_3d.setCameraPosition(
                distance=cam_dist,
                elevation=45,
                azimuth=-45,
            )

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

    def on_tool_changed(self, tid):
        self.current_mode = tid
        self.link_start_node = None

        # Show thickness slider only for Draw Lane mode (6) or Link Nodes (4)
        show_thickness = tid in [4, 6]
        self.thickness_widget.setVisible(show_thickness)
        self.brush_widget.setVisible(tid in [8, 9])

        if tid == 0:
            for item in self.scene.items():
                if isinstance(item, VisualNode) or hasattr(item, "is_fixed_entity"):
                    item.setFlag(QGraphicsItem.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        else:
            for item in self.scene.items():
                if isinstance(item, VisualNode) or hasattr(item, "is_fixed_entity"):
                    item.setFlag(QGraphicsItem.ItemIsMovable, False)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, False)

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
        self.link_start_node = None
        self.drawing_lane = False
        self.current_freehand_path = []
        self.current_freehand_item = None

        self.imp_base = (None, None)
        self.nf_base = (None, None)
        self.resources = []
        if self._height_overlay is not None:
            self._height_overlay[:] = 0
            self._rerender_heightmap()
        self.redraw_fixed_entities()
        self.base_moved.emit("imp", 0.0, 0.0)
        self.base_moved.emit("nf", 0.0, 0.0)
        self.layout_changed.emit()

    def record_action(self, action_type, item):
        self.history.append((action_type, item))
        self.redo_history.clear()
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
        elif self.current_mode in (8, 9):  # Raise / Lower
            self._sculpting = True
            # Save overlay snapshot for undo
            snapshot = (
                self._height_overlay.copy()
                if self._height_overlay is not None
                else None
            )
            self.history.append(("sculpt", snapshot))
            self.redo_history.clear()
            self._apply_brush(scene_pos.x(), scene_pos.y(), self.current_mode == 8)
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

        elif self.current_mode == 4:
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if isinstance(item, VisualNode):
                if not self.link_start_node:
                    self.link_start_node = item
                else:
                    if item != self.link_start_node:
                        existing = any(
                            (
                                e.start_node == self.link_start_node
                                and e.end_node == item
                            )
                            or (
                                e.start_node == item
                                and e.end_node == self.link_start_node
                            )
                            for e in self.link_start_node.edges
                        )
                        if not existing:
                            edge = VisualEdge(self.link_start_node, item)
                            edge.base_width = self.current_base_width
                            edge._update_pen()
                            self.scene.addItem(edge)
                            self.link_start_node.edges.append(edge)
                            item.edges.append(edge)
                            self.record_action("add", edge)
                    self.link_start_node = None

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

        if self._sculpting and self.current_mode in (8, 9):
            scene_pos = self.view.mapToScene(event.pos())
            self._apply_brush(scene_pos.x(), scene_pos.y(), self.current_mode == 8)
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
        pass

    def on_mouse_release(self, event):
        if self._sculpting:
            self._sculpting = False
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
        return nodes, connections, list(self.resources), self._height_overlay.copy() if self._height_overlay is not None else None

    def toggle_3d_view(self):
        current_idx = self.view_stack.currentIndex()
        if current_idx == 0:
            self.view_stack.setCurrentIndex(1)
            self.btn_toggle_3d.setText("2D View")
            self._update_3d_view(camera_override=self._camera_from_2d_view())
        else:
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
