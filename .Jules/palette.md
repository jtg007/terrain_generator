## 2023-10-24 - Prevent accidental data loss on delete actions
**Learning:** Destructive actions without confirmation (like clearing all placed resources) can lead to frustrating data loss, especially when the clear button is placed right next to frequently used tool buttons.
**Action:** Always add a confirmation dialog (like `QMessageBox.question`) before executing bulk delete or clear operations.
