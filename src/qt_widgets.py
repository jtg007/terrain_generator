from PySide6.QtWidgets import QComboBox


class WidePopupComboBox(QComboBox):
    """Dropdown uses at least ``popup_min_width`` so long labels stay readable."""

    popup_min_width: int = 312

    def showPopup(self) -> None:
        view = self.view()
        w = max(self.popup_min_width, self.width() + 36)
        view.setMinimumWidth(w)
        super().showPopup()
