from PySide6.QtWidgets import QApplication
import sys


# Just verify it parses and runs basic init without crashing
def verify():
    from tools.terrain_generator import TerrainGeneratorGUI

    return True


if __name__ == "__main__":
    app = QApplication(sys.argv)
    verify()
    sys.exit(0)
