import re

with open('tools/terrain_generator.py', 'r') as f:
    content = f.read()

# Replace css section carefully with f-string curly braces
search_css = """        /* ── QTabWidget ── */
        QTabWidget::pane {
            border: none;
            background: transparent;
        }
        QTabBar::tab {
            background: transparent;
            color: #888888;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 11px;
            border-bottom: 2px solid transparent;
        }
        QTabBar::tab:hover {
            color: #ffffff;
            background: #2a2a34;
        }
        QTabBar::tab:selected {
            color: #4a90e2;
            border-bottom: 2px solid #4a90e2;
            background: #1a2332;
        }"""

replace_css = """        /* ── QTabWidget ── */
        QTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        QTabBar::tab {{
            background: transparent;
            color: #888888;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 11px;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:hover {{
            color: #ffffff;
            background: #2a2a34;
        }}
        QTabBar::tab:selected {{
            color: #4a90e2;
            border-bottom: 2px solid #4a90e2;
            background: #1a2332;
        }}"""

content = content.replace(search_css, replace_css)

with open('tools/terrain_generator.py', 'w') as f:
    f.write(content)
