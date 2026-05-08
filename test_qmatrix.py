import sys
from PySide6.QtGui import QMatrix4x4, QVector3D
m = QMatrix4x4()
m.perspective(45.0, 1.0, 0.1, 100.0)
inv, ok = m.inverted()
v = inv.map(QVector3D(0, 0, 1))
print("ok:", ok, "v:", v)
