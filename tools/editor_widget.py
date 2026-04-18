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
)
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QBrush, QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from pathlib import Path
import sys

from src.terrain_spec import ZoneType, LayoutNode, LayoutConnection


# Global SVG Renderers
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).parent.parent

ICONS_DIR = PROJECT_ROOT / "icons"
SVG_RENDERERS = {
    "imp": QSvgRenderer(str(ICONS_DIR / "be base.svg")),
    "nf": QSvgRenderer(str(ICONS_DIR / "nf base.svg")),
    "res": QSvgRenderer(str(ICONS_DIR / "resource_node.svg")),
}


class VisualEdge(QGraphicsLineItem):
    def __init__(self, start_node, end_node, parent=None):
        super().__init__(parent)
        self.start_node = start_node
        self.end_node = end_node
        self.setZValue(0)
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
        
    def boundingRect(self):
        r = max(84, self.clear_radius)
        return QRectF(-r - 10, -r - 10, r * 2 + 20, r * 2 + 20)

        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)

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

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
        return super().itemChange(change, value)


class MapEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.tools_row = QHBoxLayout()
        self.tool_group = QButtonGroup(self)

        tool_names = [
            ("Move", "ToolButton", 0),
            ("Add Base", "ToolButtonBlue", 1),
            ("Add Resource", "ToolButtonGreen", 2),
            ("Link Nodes", "ToolButton", 3),
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
        self.current_mode = 0  # 0: Move, 1: Base, 2: Res, 3: Link
        self.tool_group.idClicked.connect(self.on_tool_changed)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("SmallButton")
        self.btn_clear.clicked.connect(self.clear_scene)
        self.tools_row.addStretch()
        self.tools_row.addWidget(self.btn_clear)

        layout.addLayout(self.tools_row)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setStyleSheet("background-color: #0d0d10; border: 1px solid #2e2e36;")

        layout.addWidget(self.view)

        self.grid_size = 512
        self.scene.setSceneRect(-4096, -4096, 8192, 8192)

        self.draw_grid()

        self.link_start_node = None

        self.view.wheelEvent = self.on_wheel_event
        self.view.mousePressEvent = self.on_mouse_press
        self.view.mouseMoveEvent = self.on_mouse_move
        self.view.mouseReleaseEvent = self.on_mouse_release

        self.panning = False
        self.pan_start_pos = QPointF()

    def draw_grid(self):
        grid_pen = QPen(QColor(50, 50, 60))
        grid_pen.setWidth(0)
        left = int(self.scene.sceneRect().left())
        right = int(self.scene.sceneRect().right())
        top = int(self.scene.sceneRect().top())
        bottom = int(self.scene.sceneRect().bottom())

        for x in range(left, right, self.grid_size):
            line = QGraphicsLineItem(x, top, x, bottom)
            line.setPen(grid_pen)
            line.setZValue(-1)
            self.scene.addItem(line)

        for y in range(top, bottom, self.grid_size):
            line = QGraphicsLineItem(left, y, right, y)
            line.setPen(grid_pen)
            line.setZValue(-1)
            self.scene.addItem(line)

    def on_tool_changed(self, tid):
        self.current_mode = tid
        self.link_start_node = None

        if tid == 0:
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            for item in self.scene.items():
                if isinstance(item, VisualNode):
                    item.setFlag(QGraphicsItem.ItemIsMovable, True)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        else:
            self.view.setDragMode(QGraphicsView.NoDrag)
            for item in self.scene.items():
                if isinstance(item, VisualNode):
                    item.setFlag(QGraphicsItem.ItemIsMovable, False)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def clear_scene(self):
        self.scene.clear()
        self.draw_grid()
        self.link_start_node = None

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
            VisualNode(scene_pos.x(), scene_pos.y(), 512, ZoneType.BASE, self.scene)
        elif self.current_mode == 2:
            VisualNode(
                scene_pos.x(), scene_pos.y(), 256, ZoneType.WILDERNESS, self.scene
            )
        elif self.current_mode == 3:
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
                            self.scene.addItem(edge)
                            self.link_start_node.edges.append(edge)
                            item.edges.append(edge)
                    self.link_start_node = None

        super(QGraphicsView, self.view).mousePressEvent(event)

    def on_mouse_move(self, event):
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
        super(QGraphicsView, self.view).mouseMoveEvent(event)

    def on_mouse_release(self, event):
        if event.button() == Qt.MiddleButton:
            self.panning = False
            self.view.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super(QGraphicsView, self.view).mouseReleaseEvent(event)

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
                    width=600.0,  # Default explicit width
                    type=ZoneType.MAIN_LANE,
                )
                connections.append(conn)

        return nodes, connections
