## 2023-10-24 - Prevent accidental data loss on delete actions
**Learning:** Destructive actions without confirmation (like clearing all placed resources) can lead to frustrating data loss, especially when the clear button is placed right next to frequently used tool buttons.
**Action:** Always add a confirmation dialog (like `QMessageBox.question`) before executing bulk delete or clear operations.
## 2024-05-14 - PySide6 Screen Reader Accessibility
**Learning:** PySide6/Qt UIs require explicit configuration for basic accessibility. Screen readers rely on `QLabel.setBuddy(widget)` to correctly announce what field a label applies to, and icon-only `QPushButton` elements require `setAccessibleName(name)` because they lack text descriptions.
**Action:** Always map labels to input widgets using `setBuddy()` and provide explicit names using `setAccessibleName()` for any visual-only buttons in PySide6 to maintain a11y compliance.
