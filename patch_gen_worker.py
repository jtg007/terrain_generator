import sys


def patch():
    with open("tools/terrain_generator.py", "r") as f:
        content = f.read()

    search = """                minimal_map=self.config_model.minimal_map,
                terrain_only=self.config_model.terrain_only,
            )"""

    replace = """                minimal_map=self.config_model.minimal_map,
                terrain_only=self.config_model.terrain_only,
                custom_imp_base_x=self.config_model.custom_imp_base_x,
                custom_imp_base_y=self.config_model.custom_imp_base_y,
                custom_nf_base_x=self.config_model.custom_nf_base_x,
                custom_nf_base_y=self.config_model.custom_nf_base_y,
                custom_resources=self.config_model.custom_resources,
            )"""

    content = content.replace(search, replace)

    with open("tools/terrain_generator.py", "w") as f:
        f.write(content)


patch()
