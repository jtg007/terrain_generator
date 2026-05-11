from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtCore import QTimer
import sys

app = QApplication(sys.argv)
scene = QGraphicsScene(0, 0, 100, 100)
img = QImage(100, 100, QImage.Format_RGB32)
img.fill(QColor("red"))
for x in range(100):
    for y in range(50):
        img.setPixelColor(x, y, QColor("blue")) # Top half is blue

pixmap = QPixmap.fromImage(img)
item = QGraphicsPixmapItem(pixmap)
scene.addItem(item)

view = QGraphicsView(scene)
view.scale(1, -1)
view.show()
QTimer.singleShot(1000, app.quit) # just to test it compiles
app.exec()
