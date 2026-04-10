import sys


def patch():
    with open("tools/terrain_generator.py", "r") as f:
        content = f.read()

    # The user complains about an "ugly bar" at the bottom and lagging.
    # The bar might be a horizontal scrollbar because we added split_layout with fixed/stretch settings.
    # Let's fix the layout of MapPreviewWidget to have a minimum size policy.

    # In MapPreviewWidget:
    w_search = "        self.setMinimumSize(400, 400)"
    w_replace = """        self.setMinimumSize(400, 400)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)"""

    with open("tools/preview_widget.py", "r") as pwf:
        pw_content = pwf.read()

    pw_content = pw_content.replace(w_search, w_replace)

    # Let's make it more beautiful
    b_search = """        # Draw resources
        painter.setBrush(QBrush(QColor(0, 255, 0, 180))) # Green
        painter.setPen(QPen(QColor(0, 200, 0), 2))
        for res in self.resources:
            sp = self.world_to_screen(res[0], res[1])
            if sp:
                painter.drawEllipse(sp, 6, 6)

        # Draw Imp Base
        if self.imp_base:
            sp = self.world_to_screen(self.imp_base[0], self.imp_base[1])
            if sp:
                painter.setBrush(QBrush(QColor(255, 50, 50, 200))) # Red
                painter.setPen(QPen(QColor(200, 0, 0), 2))
                painter.drawRect(sp.x()-8, sp.y()-8, 16, 16)

        # Draw NF Base
        if self.nf_base:
            sp = self.world_to_screen(self.nf_base[0], self.nf_base[1])
            if sp:
                painter.setBrush(QBrush(QColor(50, 50, 255, 200))) # Blue
                painter.setPen(QPen(QColor(0, 0, 200), 2))
                painter.drawRect(sp.x()-8, sp.y()-8, 16, 16)"""

    b_replace = """        # Setup fonts for text
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)

        # Draw resources
        painter.setBrush(QBrush(QColor(46, 204, 113, 200))) # Emerald
        painter.setPen(QPen(QColor(39, 174, 96), 2))
        for i, res in enumerate(self.resources):
            sp = self.world_to_screen(res[0], res[1])
            if sp:
                painter.drawEllipse(sp, 8, 8)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sp.x() - 10, sp.y() - 12, "Res")
                painter.setPen(QPen(QColor(39, 174, 96), 2))

        # Draw Imp Base
        if self.imp_base:
            sp = self.world_to_screen(self.imp_base[0], self.imp_base[1])
            if sp:
                painter.setBrush(QBrush(QColor(231, 76, 60, 200))) # Alizarin red
                painter.setPen(QPen(QColor(192, 57, 43), 2))
                # Draw a nice triangle pointing up
                poly = [QPoint(sp.x(), sp.y() - 10), QPoint(sp.x() - 10, sp.y() + 10), QPoint(sp.x() + 10, sp.y() + 10)]
                from PySide6.QtGui import QPolygon
                painter.drawPolygon(QPolygon(poly))
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sp.x() - 12, sp.y() - 14, "Imp")

        # Draw NF Base
        if self.nf_base:
            sp = self.world_to_screen(self.nf_base[0], self.nf_base[1])
            if sp:
                painter.setBrush(QBrush(QColor(52, 152, 219, 200))) # Peter river blue
                painter.setPen(QPen(QColor(41, 128, 185), 2))
                painter.drawRect(sp.x()-10, sp.y()-10, 20, 20)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sp.x() - 10, sp.y() - 14, "NF")"""

    pw_content = pw_content.replace(b_search, b_replace)

    with open("tools/preview_widget.py", "w") as pwf:
        pwf.write(pw_content)

    # In tools/terrain_generator.py:
    # Ensure no horizontal scrollbar by fixing main_area stretching or QScrollArea

    sc_search = """        # Split main area into settings and preview
        split_layout = QHBoxLayout()
        split_layout.addWidget(scroll, 1)"""

    sc_replace = """        # Ensure scroll area doesn't force a horizontal scrollbar unnecessarily
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Split main area into settings and preview
        split_layout = QHBoxLayout()
        split_layout.addWidget(scroll, 1)"""

    content = content.replace(sc_search, sc_replace)

    # Also adjust the UI style of the tools
    tb_search = """        # Tools layout
        tools_layout = QHBoxLayout()
        self.tool_group = QButtonGroup(self)"""

    tb_replace = """        # Tools layout
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10)
        self.tool_group = QButtonGroup(self)"""

    content = content.replace(tb_search, tb_replace)

    with open("tools/terrain_generator.py", "w") as f:
        f.write(content)


patch()
