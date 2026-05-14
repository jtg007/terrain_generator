with open('tools/terrain_generator.py', 'r') as f:
    content = f.read()

# Since we can't easily move these imports due to the sys.path manipulation
# Let's add noqa for E402
content = content.replace('from src.terrain_pipeline import (', 'from src.terrain_pipeline import (  # noqa: E402')
content = content.replace('from src.export_utils import export_vmf, get_versioned_path', 'from src.export_utils import export_vmf, get_versioned_path  # noqa: E402')
content = content.replace('from src.vmf_gen import (', 'from src.vmf_gen import (  # noqa: E402')
content = content.replace('from src.steam_paths import validate_empires_path', 'from src.steam_paths import validate_empires_path  # noqa: E402')
content = content.replace('from config import Config', 'from config import Config  # noqa: E402')
content = content.replace('from src import project_utils', 'from src import project_utils  # noqa: E402')
content = content.replace('from src.qt_widgets import WidePopupComboBox', 'from src.qt_widgets import WidePopupComboBox  # noqa: E402')

with open('tools/terrain_generator.py', 'w') as f:
    f.write(content)
