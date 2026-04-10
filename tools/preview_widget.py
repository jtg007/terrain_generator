import math
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap


class MapPreviewWidget(QLabel):
    # Signals for entity placement updates
    base_moved = Signal(str, float, float)  # (faction, x, y)
    resource_moved = Signal(int, float, float)  # (index, x, y)
    resource_added = Signal(float, float)  # (x, y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        from PySide6.QtWidgets import QSizePolicy

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #0f0f10; border: 1px solid #333338;")

        self.map_image = None
        self.pixmap_rect = QRectF()

        self.map_size_x = 0
        self.map_size_y = 0
        self.origin_x = 0
        self.origin_y = 0

        # In world coordinates
        self.imp_base = None  # (x, y)
        self.nf_base = None  # (x, y)
        self.resources = []  # [(x, y), ...]
        self.invalid_entities = set()

        # Tool modes: 'move_imp', 'move_nf', 'add_res', 'move_res'
        self.current_tool = "none"

        # Dragging state
        self.dragging_entity = None  # 'imp', 'nf', or int (index in resources)

    def set_map_image(self, image: QImage, origin_x, origin_y, size_x, size_y):
        self.map_image = image
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.map_size_x = size_x
        self.map_size_y = size_y
        self.update_pixmap()

    def set_entities(self, imp_base, nf_base, resources, invalid_entities=None):
        self.imp_base = imp_base
        self.nf_base = nf_base
        self.resources = resources if resources else []
        self.invalid_entities = invalid_entities if invalid_entities else set()
        self.update()

    def update_pixmap(self):
        if self.map_image:
            pixmap = QPixmap.fromImage(self.map_image)
            # Scale to fit while preserving aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled_pixmap)

            # Calculate the rect where the pixmap is actually drawn
            x = (self.width() - scaled_pixmap.width()) / 2
            y = (self.height() - scaled_pixmap.height()) / 2
            self.pixmap_rect = QRectF(
                x, y, scaled_pixmap.width(), scaled_pixmap.height()
            )
        else:
            self.setPixmap(QPixmap())
            self.pixmap_rect = QRectF()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_pixmap()

    def world_to_screen(self, wx, wy):
        if self.pixmap_rect.width() <= 0 or self.map_size_x <= 0:
            return None

        rel_x = (wx - self.origin_x) / self.map_size_x
        rel_y = (wy - self.origin_y) / self.map_size_y

        sx = self.pixmap_rect.x() + rel_x * self.pixmap_rect.width()
        sy = self.pixmap_rect.y() + rel_y * self.pixmap_rect.height()
        return QPoint(int(sx), int(sy))

    def screen_to_world(self, sx, sy):
        if self.pixmap_rect.width() <= 0 or self.map_size_x <= 0:
            return None

        rel_x = (sx - self.pixmap_rect.x()) / self.pixmap_rect.width()
        rel_y = (sy - self.pixmap_rect.y()) / self.pixmap_rect.height()

        # Clamp to 0-1
        rel_x = max(0.0, min(1.0, rel_x))
        rel_y = max(0.0, min(1.0, rel_y))

        wx = self.origin_x + rel_x * self.map_size_x
        wy = self.origin_y + rel_y * self.map_size_y
        return (wx, wy)

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.map_image or self.pixmap_rect.width() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint

        # Setup fonts for text
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)

        error_pen = QPen(QColor(255, 50, 50), 3)

        # Draw resources (Green Diamonds)
        painter.setBrush(QBrush(QColor(46, 204, 113, 200))) # Emerald
        for i, res in enumerate(self.resources):
            sp = self.world_to_screen(res[0], res[1])
            if sp:
                is_invalid = str(i) in self.invalid_entities
                painter.setPen(error_pen if is_invalid else QPen(QColor(39, 174, 96), 2))

                # Draw diamond
                poly = QPolygon([
                    QPoint(sp.x(), sp.y() - 10),
                    QPoint(sp.x() + 10, sp.y()),
                    QPoint(sp.x(), sp.y() + 10),
                    QPoint(sp.x() - 10, sp.y())
                ])
                painter.drawPolygon(poly)
                # Small inner diamond
                painter.setBrush(QBrush(QColor(110, 235, 150, 200)))
                painter.setPen(Qt.NoPen)
                inner = QPolygon([
                    QPoint(sp.x(), sp.y() - 5),
                    QPoint(sp.x() + 5, sp.y()),
                    QPoint(sp.x(), sp.y() + 5),
                    QPoint(sp.x() - 5, sp.y())
                ])
                painter.drawPolygon(inner)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sp.x() - 10, sp.y() - 14, "Res")
                if is_invalid:
                    painter.setPen(QColor(255, 50, 50))
                    painter.drawText(sp.x() - 5, sp.y() - 25, "⚠")
                painter.setBrush(QBrush(QColor(46, 204, 113, 200)))

        # Draw Imp Base (Blue Shield/Cross)
        if self.imp_base and self.imp_base[0] is not None and self.imp_base[1] is not None:
            sp = self.world_to_screen(self.imp_base[0], self.imp_base[1])
            if sp:
                is_invalid = "imp" in self.invalid_entities
                # Draw Blue rounded rect background
                painter.setBrush(QBrush(QColor(41, 128, 185, 220))) # Darker blue
                painter.setPen(error_pen if is_invalid else QPen(QColor(52, 152, 219), 2))
                painter.drawRoundedRect(sp.x()-12, sp.y()-12, 24, 24, 4, 4)

                # Draw cross (white)
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.setPen(Qt.NoPen)
                painter.drawRect(sp.x()-3, sp.y()-9, 6, 18)
                painter.drawRect(sp.x()-9, sp.y()-3, 18, 6)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sp.x() - 12, sp.y() - 16, "Imp")
                if is_invalid:
                    painter.setPen(QColor(255, 50, 50))
                    painter.drawText(sp.x() - 5, sp.y() - 28, "⚠")

        # Draw NF Base (Red Star/Triangle)
        if self.nf_base and self.nf_base[0] is not None and self.nf_base[1] is not None:
            sp = self.world_to_screen(self.nf_base[0], self.nf_base[1])
            if sp:
                is_invalid = "nf" in self.invalid_entities
                # Draw Red Hexagon background
                painter.setBrush(QBrush(QColor(192, 57, 43, 220))) # Dark red
                painter.setPen(error_pen if is_invalid else QPen(QColor(231, 76, 60), 2))

                poly = QPolygon()
                for i in range(6):
                    angle_deg = 60 * i - 30
                    angle_rad = math.pi / 180 * angle_deg
                    poly.append(QPoint(int(sp.x() + 14 * math.cos(angle_rad)), int(sp.y() + 14 * math.sin(angle_rad))))
                painter.drawPolygon(poly)

                # Draw inner white triangle
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.setPen(Qt.NoPen)
                tri = QPolygon([
                    QPoint(sp.x(), sp.y() - 7),
                    QPoint(sp.x() + 7, sp.y() + 5),
                    QPoint(sp.x() - 7, sp.y() + 5)
                ])
                painter.drawPolygon(tri)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sp.x() - 10, sp.y() - 16, "NF")
                if is_invalid:
                    painter.setPen(QColor(255, 50, 50))
                    painter.drawText(sp.x() - 5, sp.y() - 28, "⚠")

    def mousePressEvent(self, event):
        if not self.map_image:
            return

        pos = event.pos()
        world_pos = self.screen_to_world(pos.x(), pos.y())
        if not world_pos:
            return

        # Check if clicking existing entity to drag
        hit_dist = 15  # screen pixels

        hit = None
        min_dist = float("inf")

        if self.imp_base:
            sp = self.world_to_screen(self.imp_base[0], self.imp_base[1])
            if sp:
                d = (sp.x() - pos.x()) ** 2 + (sp.y() - pos.y()) ** 2
                if d < hit_dist**2 and d < min_dist:
                    hit = "imp"
                    min_dist = d

        if self.nf_base:
            sp = self.world_to_screen(self.nf_base[0], self.nf_base[1])
            if sp:
                d = (sp.x() - pos.x()) ** 2 + (sp.y() - pos.y()) ** 2
                if d < hit_dist**2 and d < min_dist:
                    hit = "nf"
                    min_dist = d

        for i, res in enumerate(self.resources):
            sp = self.world_to_screen(res[0], res[1])
            if sp:
                d = (sp.x() - pos.x()) ** 2 + (sp.y() - pos.y()) ** 2
                if d < hit_dist**2 and d < min_dist:
                    hit = i
                    min_dist = d

        if hit is not None:
            self.dragging_entity = hit
        elif self.current_tool == "add_res":
            self.resource_added.emit(world_pos[0], world_pos[1])
        elif self.current_tool == "imp_base":
            self.base_moved.emit("imp", world_pos[0], world_pos[1])
        elif self.current_tool == "nf_base":
            self.base_moved.emit("nf", world_pos[0], world_pos[1])

    def mouseMoveEvent(self, event):
        if self.dragging_entity is not None:
            pos = event.pos()
            world_pos = self.screen_to_world(pos.x(), pos.y())
            if world_pos:
                if self.dragging_entity == "imp":
                    self.base_moved.emit("imp", world_pos[0], world_pos[1])
                elif self.dragging_entity == "nf":
                    self.base_moved.emit("nf", world_pos[0], world_pos[1])
                elif isinstance(self.dragging_entity, int):
                    self.resource_moved.emit(
                        self.dragging_entity, world_pos[0], world_pos[1]
                    )

    def mouseReleaseEvent(self, event):
        self.dragging_entity = None
