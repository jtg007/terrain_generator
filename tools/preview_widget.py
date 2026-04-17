import math
from typing import List, Optional, Tuple, Set

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
)
from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap, QPolygon

from src.terrain_spec import ZoneType, LayoutNode, LayoutConnection


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
        self.pen = QPen(QColor(200, 200, 200, 150), max(3, width / 50))
        self.pen.setCapStyle(Qt.RoundCap)
        self.pen.setJoinStyle(Qt.RoundJoin)

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
        painter.setPen(self.pen)
        painter.setBrush(Qt.NoBrush)
        from PySide6.QtGui import QPainterPath
        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        painter.drawPath(path)

class VisualEdge(QGraphicsLineItem):
    def __init__(self, start_node, end_node, parent=None):
        super().__init__(parent)
        self.start_node = start_node
        self.end_node = end_node
        self.logical_width = 600.0
        self.setZValue(1)
        self.setPen(QPen(QColor(200, 200, 200, 150), 3))
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

        if node_type == ZoneType.BASE:
            self.setBrush(QBrush(QColor(52, 152, 219)))
            self.setPen(QPen(QColor(41, 128, 185), 2))
        else:
            self.setBrush(QBrush(QColor(46, 204, 113)))
            self.setPen(QPen(QColor(39, 174, 96), 2))

        scene.addItem(self)

    def boundingRect(self):
        r = self.clear_radius
        return QRectF(-r - 10, -r - 10, r * 2 + 20, r * 2 + 20)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1, Qt.DashLine))
        painter.setBrush(QBrush(QColor(255, 255, 255, 10)))
        r = self.clear_radius
        painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

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

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Toolbar ──
        self.tools_row = QHBoxLayout()
        self.tool_group = QButtonGroup(self)

        tool_names = [
            ("Move", "ToolButton", 0),
            ("Add Node", "ToolButton", 1),
            ("Add Base", "ToolButtonBlue", 2),
            ("Add Resource", "ToolButtonGreen", 3),
            ("Link Nodes", "ToolButton", 4),
        ]
        self.modes = {}
        for label, obj_name, tid in tool_names:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName(obj_name)
            self.tool_group.addButton(btn, tid)
            self.tools_row.addWidget(btn)
            self.modes[tid] = label

        self.tool_group.button(0).setChecked(True)
        self.current_mode = 0  # 0: Move, 1: Add Node, 2: Add Base, 3: Add Resource, 4: Link Nodes
        self.tool_group.idClicked.connect(self.on_tool_changed)

        # Mode: Remove (5) and Freehand Lane (6)
        tool_names.append(("Remove", "ToolButtonRed", 5))
        tool_names.append(("Draw Lane", "ToolButton", 6))

        btn_remove = QPushButton("Remove")
        btn_remove.setCheckable(True)
        btn_remove.setObjectName("ToolButtonRed")
        self.tool_group.addButton(btn_remove, 5)
        self.tools_row.addWidget(btn_remove)
        self.modes[5] = "Remove"

        btn_draw = QPushButton("Draw Lane")
        btn_draw.setCheckable(True)
        btn_draw.setObjectName("ToolButton")
        self.tool_group.addButton(btn_draw, 6)
        self.tools_row.addWidget(btn_draw)
        self.modes[6] = "Draw Lane"

        # Thickness selector for drawing lanes
        self.thickness_slider = QSlider(Qt.Horizontal)
        self.thickness_slider.setRange(100, 1500)
        self.thickness_slider.setValue(600)
        self.thickness_slider.setToolTip("Lane Width")
        self.thickness_slider.setFixedWidth(100)
        self.thickness_label = QLabel("Width: 600")
        self.thickness_slider.valueChanged.connect(lambda v: self.thickness_label.setText(f"Width: {v}"))

        # Hide them initially
        self.thickness_slider.setVisible(False)
        self.thickness_label.setVisible(False)

        self.tools_row.addWidget(self.thickness_label)
        self.tools_row.addWidget(self.thickness_slider)

        self.tools_row.addStretch()

        # Undo / Redo
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

        layout.addLayout(self.tools_row)

        # ── Graphics View ──
        class CustomGraphicsView(QGraphicsView):
            def __init__(self, scene, parent_widget):
                super().__init__(scene)
                self.parent_widget = parent_widget

            def wheelEvent(self, event):
                self.parent_widget.on_wheel_event(event)

            def mousePressEvent(self, event):
                super().mousePressEvent(event)
                self.parent_widget.on_mouse_press(event)

            def mouseMoveEvent(self, event):
                super().mouseMoveEvent(event)
                self.parent_widget.on_mouse_move(event)

            def mouseReleaseEvent(self, event):
                super().mouseReleaseEvent(event)
                self.parent_widget.on_mouse_release(event)

        self.scene = QGraphicsScene()
        self.view = CustomGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
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
                return QRectF(-15, -15, 30, 30)

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
                error_pen = QPen(QColor(255, 50, 50), 3)

                if self.entity_type == "res":
                    painter.setBrush(QBrush(QColor(46, 204, 113, 200)))
                    painter.setPen(error_pen if self.invalid else QPen(QColor(39, 174, 96), 2))
                    poly = QPolygon([QPoint(0, -10), QPoint(10, 0), QPoint(0, 10), QPoint(-10, 0)])
                    painter.drawPolygon(poly)
                    painter.setBrush(QBrush(QColor(110, 235, 150, 200)))
                    painter.setPen(Qt.NoPen)
                    inner = QPolygon([QPoint(0, -5), QPoint(5, 0), QPoint(0, 5), QPoint(-5, 0)])
                    painter.drawPolygon(inner)
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(-10, -14, "Res")
                    if self.invalid:
                        painter.setPen(QColor(255, 50, 50))
                        painter.drawText(-5, -25, "⚠")

                elif self.entity_type == "imp":
                    painter.setBrush(QBrush(QColor(41, 128, 185, 220)))
                    painter.setPen(error_pen if self.invalid else QPen(QColor(52, 152, 219), 2))
                    painter.drawRoundedRect(-12, -12, 24, 24, 4, 4)
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(-3, -9, 6, 18)
                    painter.drawRect(-9, -3, 18, 6)
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(-12, -16, "BE")
                    if self.invalid:
                        painter.setPen(QColor(255, 50, 50))
                        painter.drawText(-5, -28, "⚠")

                elif self.entity_type == "nf":
                    painter.setBrush(QBrush(QColor(192, 57, 43, 220)))
                    painter.setPen(error_pen if self.invalid else QPen(QColor(231, 76, 60), 2))
                    poly = QPolygon()
                    for i in range(6):
                        angle_deg = 60 * i - 30
                        angle_rad = math.pi / 180 * angle_deg
                        poly.append(QPoint(int(14 * math.cos(angle_rad)), int(14 * math.sin(angle_rad))))
                    painter.drawPolygon(poly)
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.setPen(Qt.NoPen)
                    tri = QPolygon([QPoint(0, -7), QPoint(7, 5), QPoint(-7, 5)])
                    painter.drawPolygon(tri)
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(-10, -16, "NF")
                    if self.invalid:
                        painter.setPen(QColor(255, 50, 50))
                        painter.drawText(-5, -28, "⚠")

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

            # Scale item to map bounds rather than making a gigantic pixmap
            scale_x = self.map_size_x / max(1, pixmap.width())
            scale_y = self.map_size_y / max(1, pixmap.height())

            self.map_pixmap_item.setScale(scale_x)
            # Y scaling should also be scale_y but Qt scale acts uniformly or uses transform.
            # QGraphicsItem setScale is uniform. We use setTransform for non-uniform.
            from PySide6.QtGui import QTransform
            self.map_pixmap_item.setTransform(QTransform.fromScale(scale_x, scale_y))

            self.map_pixmap_item.setPos(self.origin_x, self.origin_y)
        else:
            self.map_pixmap_item.setPixmap(QPixmap())

    def on_tool_changed(self, tid):
        self.current_mode = tid
        self.link_start_node = None

        # Show thickness slider only for Draw Lane mode (6) or Link Nodes (4)
        show_thickness = tid in [4, 6]
        self.thickness_slider.setVisible(show_thickness)
        self.thickness_label.setVisible(show_thickness)

        if tid == 0:
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            for item in self.scene.items():
                if isinstance(item, VisualNode) or hasattr(item, "is_fixed_entity"):
                    item.setFlag(QGraphicsItem.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        else:
            self.view.setDragMode(QGraphicsView.NoDrag)
            for item in self.scene.items():
                if isinstance(item, VisualNode) or hasattr(item, "is_fixed_entity"):
                    item.setFlag(QGraphicsItem.ItemIsMovable, False)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def clear_scene_nodes(self):
        # Create an action for clear all
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

    def record_action(self, action_type, item):
        self.history.append((action_type, item))
        self.redo_history.clear()

    def undo(self):
        if not self.history: return
        action, item = self.history.pop()

        if action == "add":
            self.scene.removeItem(item)
            self.redo_history.append(("add", item))
        elif action == "remove":
            self.scene.addItem(item)
            self.redo_history.append(("remove", item))
        elif action == "remove_multiple":
            for i in item:
                self.scene.addItem(i)
            self.redo_history.append(("remove_multiple", item))

    def redo(self):
        if not self.redo_history: return
        action, item = self.redo_history.pop()

        if action == "add":
            self.scene.addItem(item)
            self.history.append(("add", item))
        elif action == "remove":
            self.scene.removeItem(item)
            self.history.append(("remove", item))
        elif action == "remove_multiple":
            for i in item:
                self.scene.removeItem(i)
            self.history.append(("remove_multiple", item))

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
        elif self.current_mode == 2:
            node = VisualNode(scene_pos.x(), scene_pos.y(), 512, ZoneType.BASE, self.scene)
            self.record_action("add", node)
        elif self.current_mode == 5: # Remove
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if isinstance(item, VisualNode) or isinstance(item, VisualEdge) or isinstance(item, VisualFreehandEdge):
                # If we remove a node, we should remove its edges too
                items_to_remove = [item]
                if isinstance(item, VisualNode):
                    for edge in item.edges:
                        if edge in self.scene.items() and edge not in items_to_remove:
                            items_to_remove.append(edge)

                self.record_action("remove_multiple", items_to_remove)
                for i in items_to_remove:
                    self.scene.removeItem(i)
            elif hasattr(item, "is_fixed_entity"):
                # Handle base/resource removal via signals or state updates
                # Fixed entities are tied to config state, so we update the parent state directly
                # However, they might want to just move them out of bounds or clear them.
                # Let's emit signals to clear them if clicked with remove tool.
                # Just hide it for now visually, we can't emit None to float
                if item.entity_type == "imp":
                    self.imp_base = (0.0, 0.0) # Move to corner
                    if isinstance(self.scene.views()[0].parent(), MapPreviewWidget):
                        self.scene.views()[0].parent().base_moved.emit("imp", 0.0, 0.0)
                elif item.entity_type == "nf":
                    self.nf_base = (0.0, 0.0)
                    if isinstance(self.scene.views()[0].parent(), MapPreviewWidget):
                        self.scene.views()[0].parent().base_moved.emit("nf", 0.0, 0.0)
                # Note: 'res' removal is not straightforward without passing the index correctly and modifying the list.
                # It's better left handled by "Clear Resources" in the config panel for now, or we can send a None signal.
        elif self.current_mode == 3:
            # Emit resource added instead of VisualNode if they clicked on the preview
            self.resource_added.emit(scene_pos.x(), scene_pos.y())
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
                            edge.setPen(QPen(QColor(200, 200, 200, 150), max(3, self.thickness_slider.value() / 50)))
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
