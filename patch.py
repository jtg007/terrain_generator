import re

with open('tools/terrain_generator.py', 'r') as f:
    content = f.read()

# 1. Remove CollapsibleBox class completely
content = re.sub(r'class CollapsibleBox\(QWidget\):.*?def setContentLayout\(self, content_layout\):.*?while content_layout\.count\(\):.*?elif item\.spacerItem\(\):.*?self\.content_layout\.addItem\(item\.spacerItem\(\))\n\n', '', content, flags=re.DOTALL)

# 2. Add QTabWidget import
if 'QTabWidget' not in content:
    content = content.replace('QScrollArea,', 'QScrollArea,\n    QTabWidget,')

with open('tools/terrain_generator.py', 'w') as f:
    f.write(content)
