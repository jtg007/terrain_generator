with open('tools/terrain_generator.py', 'r') as f:
    content = f.read()

content = content.replace('preview_timer.start(500)', 'preview_timer.start(150)')

with open('tools/terrain_generator.py', 'w') as f:
    f.write(content)
