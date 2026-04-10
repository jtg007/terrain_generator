import sys


def patch():
    with open("tools/terrain_generator.py", "r") as f:
        content = f.read()

    search1 = """    def clear_resources(self):
        self.config_model.custom_resources = []
        self.sync_to_model()

    def on_tool_changed(self, id):
        tools = {0: "none", 1: "imp_base", 2: "nf_base", 3: "add_res"}
        self.preview_widget.current_tool = tools.get(id, "none")

    def on_base_moved(self, faction, x, y):
        if faction == "imp":
            self.config_model.custom_imp_base_x = x
            self.config_model.custom_imp_base_y = y
        else:
            self.config_model.custom_nf_base_x = x
            self.config_model.custom_nf_base_y = y
        self.sync_to_model()

    def on_resource_moved(self, index, x, y):
        if self.config_model.custom_resources and 0 <= index < len(
            self.config_model.custom_resources
        ):
            self.config_model.custom_resources[index] = (x, y)
        self.sync_to_model()

    def on_resource_added(self, x, y):
        if self.config_model.custom_resources is None:
            self.config_model.custom_resources = []
        self.config_model.custom_resources.append((x, y))
        self.sync_to_model()"""

    replace1 = """    def clear_resources(self):
        self.config_model.custom_resources = []
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            []
        )
        self.preview_timer.start(500)

    def on_tool_changed(self, id):
        tools = {0: "none", 1: "imp_base", 2: "nf_base", 3: "add_res"}
        self.preview_widget.current_tool = tools.get(id, "none")

    def on_base_moved(self, faction, x, y):
        if faction == "imp":
            self.config_model.custom_imp_base_x = x
            self.config_model.custom_imp_base_y = y
        else:
            self.config_model.custom_nf_base_x = x
            self.config_model.custom_nf_base_y = y
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            self.config_model.custom_resources
        )
        self.preview_timer.start(500)

    def on_resource_moved(self, index, x, y):
        if self.config_model.custom_resources and 0 <= index < len(
            self.config_model.custom_resources
        ):
            self.config_model.custom_resources[index] = (x, y)
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            self.config_model.custom_resources
        )
        # Resource positions do not affect the terrain heightmap itself,
        # so we don't necessarily need to re-run the pipeline on move,
        # but we can do it if desired.
        self.preview_timer.start(500)

    def on_resource_added(self, x, y):
        if self.config_model.custom_resources is None:
            self.config_model.custom_resources = []
        self.config_model.custom_resources.append((x, y))
        self.preview_widget.set_entities(
            (self.config_model.custom_imp_base_x, self.config_model.custom_imp_base_y),
            (self.config_model.custom_nf_base_x, self.config_model.custom_nf_base_y),
            self.config_model.custom_resources
        )
        self.preview_timer.start(500)"""

    content = content.replace(search1, replace1)

    with open("tools/terrain_generator.py", "w") as f:
        f.write(content)


patch()
