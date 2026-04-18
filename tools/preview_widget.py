import math
from pathlib import Path
from typing import List, Optional, Tuple, Set

import numpy as np

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
)
from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap, QPolygon
from PySide6.QtSvg import QSvgRenderer

from src.terrain_spec import ZoneType, LayoutNode, LayoutConnection


# Global SVG Renderers
ICONS_DIR = Path(__file__).parent.parent / "icons"
SVG_RENDERERS = {
    "imp": QSvgRenderer(str(ICONS_DIR / "be base.svg")),
    "nf": QSvgRenderer(str(ICONS_DIR / "nf base.svg")),
    "res": QSvgRenderer(str(ICONS_DIR / "resource_node.svg")),
}


class VisualFreehandEdge(QGraphicsItem):
    def __init__(self, points, width, start_node=None, end_node=None, parent=None):
        super().__init__(parent)
        self.points = points  # List of QPointF (in scene coords)
        self.base_points = [p for p in points] # Keep original points for offset calculation
        self.logical_width = width
        self.start_node = start_node
        self.end_node = end_node
        self.setZValue(1)
        self.setFlags(QGraphicsItem.ItemIsSelectable)

        pen_w = max(4, width / 25.0)
        self.pen = QPen(QColor(255, 255, 255, 90), pen_w)
        self.pen.setCapStyle(Qt.RoundCap)
        self.pen.setJoinStyle(Qt.RoundJoin)

        self.outline_pen = QPen(QColor(200, 200, 255, 120), 2)
        self.outline_pen.setCapStyle(Qt.RoundCap)
        self.outline_pen.setJoinStyle(Qt.RoundJoin)

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
                        new_x = start_pos.x() + t * dx + (bp.x() - (orig_start.x() + t * orig_dx))
                        new_y = start_pos.y() + t * dy + (bp.y() - (orig_start.y() + t * orig_dy))
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
        return QRectF(min(xs) - margin, min(ys) - margin, max(xs) - min(xs) + 2*margin, max(ys) - min(ys) + 2*margin)

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
        self.logical_width = 600.0
        self.setZValue(1)
        pen = QPen(QColor(255, 255, 255, 90), 12) # Thick but translucent base
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self.update_position()

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
        
        if self.node_type == ZoneType.BASE:
            SVG_RENDERERS["imp"].render(painter, rect)
        else:
            SVG_RENDERERS["res"].render(painter, rect)
            
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1, Qt.DashLine))
        painter.setBrush(QBrush(QColor(255, 255, 255, 10)))
        r_clear = self.clear_radius
        painter.drawEllipse(QRectF(-r_clear, -r_clear, r_clear * 2, r_clear * 2))

    def boundingRect(self):
        r = max(84, self.clear_radius)
        return QRectF(-r - 10, -r - 10, r * 2 + 20, r * 2 + 20)

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
        toolbar_scroll.setFixedHeight(40) # Keep it compact
        
        toolbar_widget = QWidget()
        self.tools_row = QHBoxLayout(toolbar_widget)
        self.tools_row.setSpacing(6)
        self.tools_row.setContentsMargins(4, 0, 4, 0)

        self.tool_group = QButtonGroup(self)
        self.modes = {}

        # Helper to add section labels
        def add_separator(text):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #888; font-weight: bold; font-size: 9px; margin-left: 4px; margin-right: 2px;")
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

        # 2. Layout
        add_separator("LAYOUT")

        btn_node = QPushButton("Add Node")
        btn_node.setCheckable(True)
        btn_node.setObjectName("ToolButton")
        self.tool_group.addButton(btn_node, 1)
        self.tools_row.addWidget(btn_node)

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
        self.thickness_slider.setRange(100, 1500)
        self.thickness_slider.setValue(600)
        self.thickness_slider.setFixedWidth(80)
        self.thickness_slider.valueChanged.connect(lambda v: self.thickness_label.setText(f"Width: {v}"))

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
        btn_nf.setObjectName("ToolButtonRed") # NF is typically red in this UI
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
        self.brush_size_slider.valueChanged.connect(lambda v: self.brush_size_label.setText(f"Size: {v}"))

        self.brush_strength_label = QLabel("Str: 50")
        self.brush_strength_label.setStyleSheet("color: #ccc; font-size: 11px;")
        self.brush_strength_slider = QSlider(Qt.Horizontal)
        self.brush_strength_slider.setRange(5, 200)
        self.brush_strength_slider.setValue(50)
        self.brush_strength_slider.setFixedWidth(60)
        self.brush_strength_slider.valueChanged.connect(lambda v: self.brush_strength_label.setText(f"Str: {v}"))

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

        layout.addWidget(self.view)

        # State
        self.map_image = None
        self.map_pixmap_item = QGraphicsPixmapItem()
        self.map_pixmap_item.setZValue(-10)
        self.scene.addItem(self.map_pixmap_item)

        self.map_size_x = 8192
        self.map_size_y = 8192
        self.origin_x = -4096
        self.origin_y = -4096

        self.scene.setSceneRect(self.origin_x, self.origin_y, self.map_size_x, self.map_size_y)

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

        # Sculpting state
        self._base_heights = None      # numpy float64 from pipeline
        self._height_overlay = None    # numpy float64 additive delta
        self._sculpting = False

    def draw_grid(self):
        for item in self.grid_items:
            self.scene.removeItem(item)
        self.grid_items.clear()

        grid_pen = QPen(QColor(50, 50, 60, 100)) # Semi-transparent grid
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

    def set_map_image(self, image: QImage, origin_x, origin_y, size_x, size_y):
        self.map_image = image
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.map_size_x = size_x
        self.map_size_y = size_y

        self.scene.setSceneRect(self.origin_x, self.origin_y, self.map_size_x, self.map_size_y)
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

        # A helper class for non-node bases/resources that MapPreviewWidget used to draw natively
        class FixedEntityItem(QGraphicsItem):
            def __init__(self, x, y, entity_type, index=None, invalid=False, parent=None):
                super().__init__(parent)
                self.x_coord = x
                self.y_coord = y
                self.entity_type = entity_type
                self.index = index
                self.invalid = invalid
                self.setPos(x, y)
                self.setZValue(3)
                self.is_fixed_entity = True
                self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)

            def boundingRect(self):
                return QRectF(-90, -90, 180, 180)

            def itemChange(self, change, value):
                return super().itemChange(change, value)

            def mouseReleaseEvent(self, event):
                super().mouseReleaseEvent(event)
                # Emit only on release to prevent constant synchronous rebuilds while dragging
                if self.entity_type == "imp":
                    if isinstance(self.scene().views()[0].parent(), MapPreviewWidget):
                        self.scene().views()[0].parent().base_moved.emit("imp", self.x(), self.y())
                elif self.entity_type == "nf":
                    if isinstance(self.scene().views()[0].parent(), MapPreviewWidget):
                        self.scene().views()[0].parent().base_moved.emit("nf", self.x(), self.y())
                elif self.entity_type == "res":
                    if isinstance(self.scene().views()[0].parent(), MapPreviewWidget):
                        self.scene().views()[0].parent().resource_moved.emit(self.index, self.x(), self.y())

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

        if self.imp_base and self.imp_base[0] is not None and self.imp_base[1] is not None:
            invalid = "imp" in self.invalid_entities
            self.scene.addItem(FixedEntityItem(self.imp_base[0], self.imp_base[1], "imp", invalid=invalid))

        if self.nf_base and self.nf_base[0] is not None and self.nf_base[1] is not None:
            invalid = "nf" in self.invalid_entities
            self.scene.addItem(FixedEntityItem(self.nf_base[0], self.nf_base[1], "nf", invalid=invalid))

        for i, res in enumerate(self.resources):
            invalid = str(i) in self.invalid_entities
            self.scene.addItem(FixedEntityItem(res[0], res[1], "res", index=i, invalid=invalid))


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

    def set_raw_heights(self, heights: np.ndarray):
        self._base_heights = heights.astype(np.float64).copy()
        self._base_min = float(self._base_heights.min())
        self._base_max = float(self._base_heights.max())
        if self._height_overlay is None or self._height_overlay.shape != heights.shape:
            self._height_overlay = np.zeros_like(self._base_heights)

        # Re-render with overlay if sculpt edits exist
        if self._height_overlay.any():
            self._rerender_heightmap()

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
        radius_sq = brush_r_px ** 2
        mask = dist_sq < radius_sq
        falloff = np.exp(-dist_sq / (radius_sq * 0.3)) * mask

        delta = falloff * strength * (1.0 if raise_terrain else -1.0)
        self._height_overlay[r_min:r_max, c_min:c_max] += delta

        self._rerender_heightmap()

    def _rerender_heightmap(self):
        if self._base_heights is None:
            return

        combined = self._base_heights + self._height_overlay

        # Use the exact same min/max as the original preview rendering
        # so unsculpted areas stay pixel-identical. Sculpted areas clamp.
        min_h = self._base_min
        max_h = self._base_max

        if max_h > min_h:
            normalized = (combined - min_h) / (max_h - min_h)
        else:
            normalized = np.zeros_like(combined)

        img_data = (np.clip(normalized, 0, 1) * 255).astype(np.uint8)
        h, w = img_data.shape

        self._preview_img_data = img_data
        qimg = QImage(
            self._preview_img_data.data,
            w, h, w,
            QImage.Format_Grayscale8,
        )
        self.map_image = qimg
        self.update_pixmap()

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
        items_to_remove = []
        for item in self.scene.items():
            if isinstance(item, VisualNode) or isinstance(item, VisualEdge) or isinstance(item, VisualFreehandEdge):
                items_to_remove.append(item)
        if items_to_remove:
            self.history.append(("remove_multiple", items_to_remove))
            self.redo_history.clear()
            for item in items_to_remove:
                self.scene.removeItem(item)
        self.link_start_node = None

        self.imp_base = None
        self.nf_base = None
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
        if not self.history: return
        action, item = self.history.pop()

        if action == "sculpt":
            current = self._height_overlay.copy() if self._height_overlay is not None else None
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
        self.layout_changed.emit()

    def redo(self):
        if not self.redo_history: return
        action, item = self.redo_history.pop()

        if action == "sculpt":
            current = self._height_overlay.copy() if self._height_overlay is not None else None
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

        if self.current_mode == 1:
            node = VisualNode(scene_pos.x(), scene_pos.y(), 256, ZoneType.WILDERNESS, self.scene)
            self.record_action("add", node)
        elif self.current_mode == 2: # BE Base
            self.imp_base = (scene_pos.x(), scene_pos.y())
            self.redraw_fixed_entities()
            self.base_moved.emit("imp", scene_pos.x(), scene_pos.y())
        elif self.current_mode == 7: # NF Base
            self.nf_base = (scene_pos.x(), scene_pos.y())
            self.redraw_fixed_entities()
            self.base_moved.emit("nf", scene_pos.x(), scene_pos.y())
        elif self.current_mode == 5: # Remove
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if isinstance(item, VisualNode) or isinstance(item, VisualEdge) or isinstance(item, VisualFreehandEdge):
                items_to_remove = [item]
                if isinstance(item, VisualNode):
                    for edge in item.edges:
                        if edge in self.scene.items() and edge not in items_to_remove:
                            items_to_remove.append(edge)

                self.record_action("remove_multiple", items_to_remove)
                for i in items_to_remove:
                    self.scene.removeItem(i)
            elif hasattr(item, "is_fixed_entity"):
                if item.entity_type == "imp":
                    self.imp_base = (0.0, 0.0)
                    self.redraw_fixed_entities()
                    self.base_moved.emit("imp", 0.0, 0.0)
                elif item.entity_type == "nf":
                    self.nf_base = (0.0, 0.0)
                    self.redraw_fixed_entities()
                    self.base_moved.emit("nf", 0.0, 0.0)
        elif self.current_mode == 3: # Add Resource
            # Deduplicate: don't add if a resource already exists at this exact spot
            for rx, ry in self.resources:
                if abs(rx - scene_pos.x()) < 1.0 and abs(ry - scene_pos.y()) < 1.0:
                    return
            self.resources.append((scene_pos.x(), scene_pos.y()))
            self.redraw_fixed_entities()
            self.resource_added.emit(scene_pos.x(), scene_pos.y())
        elif self.current_mode in (8, 9):  # Raise / Lower
            self._sculpting = True
            # Save overlay snapshot for undo
            snapshot = self._height_overlay.copy() if self._height_overlay is not None else None
            self.history.append(("sculpt", snapshot))
            self.redo_history.clear()
            self._apply_brush(scene_pos.x(), scene_pos.y(), self.current_mode == 8)
        elif self.current_mode == 6: # Draw Lane
            self.drawing_lane = True
            self.current_freehand_path = [scene_pos]
            item = self.scene.itemAt(scene_pos, self.view.transform())
            self.freehand_start_node = item if isinstance(item, VisualNode) else None

            # Temporary item to draw while dragging
            self.current_freehand_item = VisualFreehandEdge(self.current_freehand_path, self.thickness_slider.value())
            self.scene.addItem(self.current_freehand_item)

        elif self.current_mode == 4:
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if isinstance(item, VisualNode):
                if not self.link_start_node:
                    self.link_start_node = item
                else:
                    if item != self.link_start_node:
                        existing = any(
                            (e.start_node == self.link_start_node and e.end_node == item)
                            or (e.start_node == item and e.end_node == self.link_start_node)
                            for e in self.link_start_node.edges
                        )
                        if not existing:
                            edge = VisualEdge(self.link_start_node, item)
                            # Set explicit width based on slider
                            # Visual mapping from logical to pixels roughly
                            pen_w = max(4, self.thickness_slider.value() / 25.0)
                            p = QPen(QColor(255, 255, 255, 90), pen_w)
                            p.setCapStyle(Qt.RoundCap)
                            edge.setPen(p)
                            edge.logical_width = self.thickness_slider.value()
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
                    self.thickness_slider.value(),
                    start_node=self.freehand_start_node,
                    end_node=end_node
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
                    sn = LayoutNode(item.points[0].x(), item.points[0].y(), 100, ZoneType.MAIN_LANE)
                    nodes.append(sn)
                if not en and item.points:
                    en = LayoutNode(item.points[-1].x(), item.points[-1].y(), 100, ZoneType.MAIN_LANE)
                    nodes.append(en)

                path_points = [(p.x(), p.y()) for p in item.points]
                conn = LayoutConnection(
                    start_node=sn,
                    end_node=en,
                    width=item.logical_width,
                    type=ZoneType.MAIN_LANE,
                    path_points=path_points
                )
                connections.append(conn)

        return nodes, connections
