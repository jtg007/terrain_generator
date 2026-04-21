import sys
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PySide6.QtCore import QRectF, Qt, QPoint

app = QApplication(sys.argv)
scene = QGraphicsScene()
origin_x, origin_y = -4096, -4096
scene.setSceneRect(origin_x, origin_y, 8192, 8192)
view = QGraphicsView(scene)
view.scale(1, -1)
view.resize(800, 800)
view.show()
# Wait for view to initialize properly
view.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)

# Simulate click Top-Right of the view
# Top-Right of view is (width, 0)
print("Top-Right (Width, 0):", view.mapToScene(QPoint(view.viewport().width(), 0)))
# Top-Left of view is (0, 0)
print("Top-Left (0, 0):", view.mapToScene(QPoint(0, 0)))

