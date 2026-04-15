with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# We accidentally added create_connection_path twice. Let's find the first one and delete it.
# The first one seems to start at line 83 and end at line 134.
lines = content.split('\n')
idx_first = -1
for i, line in enumerate(lines):
    if line.startswith("def create_connection_path("):
        idx_first = i
        break

if idx_first != -1:
    idx_end = -1
    for i in range(idx_first + 1, len(lines)):
        if lines[i].startswith("def create_connection_path("):
            idx_end = i
            break

    if idx_end != -1:
        # remove the first one
        lines = lines[:idx_first] + lines[idx_end:]

with open('src/terrain_pipeline.py', 'w') as f:
    f.write('\n'.join(lines))
