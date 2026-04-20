## 2024-04-20 - PySide6 Accessibility Enhancements
**Learning:** For PySide6 GUI accessibility and UX, associate `QLabel` widgets with their inputs using `.setBuddy()`, set `.setAccessibleName()` on icon-only buttons for screen readers, and provide explanatory tooltips on disabled buttons to improve the user experience.
**Action:** When implementing new UI elements or reviewing existing ones in PySide6, always add `.setBuddy()` to labels, `.setAccessibleName()` to icon-only controls, and tooltips to disabled buttons.
