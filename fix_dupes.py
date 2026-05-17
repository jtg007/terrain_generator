import re
with open('src/urban_generator.py', 'r') as f:
    content = f.read()

# I accidentally prepended these functions instead of replacing them. Let's find and remove the dupes.
# Wait, let's just restore src/urban_generator.py from git and re-apply cleanly.
