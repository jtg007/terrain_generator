Ah, in `tools/terrain_generator.py`, when it creates `vmf_spec = PipelineSpec(...)` around line 180, it's missing the custom coordinate arguments that are available in `self.config_model`:
```python
                custom_imp_base_x=self.config_model.custom_imp_base_x,
                custom_imp_base_y=self.config_model.custom_imp_base_y,
                custom_nf_base_x=self.config_model.custom_nf_base_x,
                custom_nf_base_y=self.config_model.custom_nf_base_y,
                custom_resources=self.config_model.custom_resources,
```
That's why the custom positions set in the GUI aren't making it to the map.

Additionally, to fix "it's lagging":
Right now the `self.sync_to_model()` triggers `self.update_validation_status()`, which in turn does `self.preview_timer.start(500)`. If dragging is calling `sync_to_model` on every mouse move, it could be starting/stopping the timer repeatedly and potentially causing heavy UI lags or stutter if things are recreating fast, or maybe we shouldn't run `make_spec()` and the entire `run_pipeline` while dragging. Or maybe the `PreviewWorker` takes a bit and blocks something? No, `run_pipeline` in a QThread shouldn't block the UI, but updating a 16384x16384 grid (or smaller) still takes 0.78s.
Wait, `run_preview` fires after 500ms. But while dragging `sync_to_model()` is called on every `mouseMoveEvent`. That resets the timer but also sets all the other sliders' values to the model.

If the user wants it to look "more beautiful" and not lag:
- Draw standard icons (e.g., small colored flags or better shapes) instead of plain rects/ellipses.
- Use a crosshair or better icons for "tools".
- To fix lagging during dragging:
  - DO NOT run `sync_to_model()` on every drag tick, or at least do not trigger `update_validation_status` and `preview_timer.start` if ONLY the entities moved. Entity position changes don't need a full `run_pipeline` for the preview! The preview image is JUST the terrain heightmap. The entities are drawn ON TOP of it in `paintEvent`.
  - So, in `on_base_moved` and `on_resource_moved`, DO NOT call `sync_to_model()`. Instead, just update the model variables and call `self.preview_widget.update()` to trigger a repaint!
  - Wait, if we change the base coordinates, does the terrain base flattening change? Yes, `flatten_base_areas` flattens the terrain at the base coordinates. So changing base coordinates DOES change the terrain heightmap. BUT doing it on every drag tick is too slow (0.78s).
  - So we *should* just update the base coordinates, call `update()` on the widget to redraw the dragging icon immediately, and let a debounced timer (maybe 500ms or 1s) run the actual terrain preview regeneration.

Let's refine the plan:
1. Fix `PipelineSpec` initialization in `GenerationWorker` to pass the custom entity coordinates.
2. Fix lagging during drag:
   - In `tools/terrain_generator.py`, in `on_base_moved` and `on_resource_moved`, don't call `sync_to_model()`.
   - Instead, update `self.config_model.custom_...` and just call `self.preview_widget.update()`.
   - Also, restart the `preview_timer` directly, so the pipeline regenerates once dragging stops.
3. Make it more beautiful:
   - Use nice colors/shapes for the markers in `paintEvent`.
   - Maybe a small tooltip or text next to the markers ("Imp Base", "NF Base", "Res").
   - Maybe a darker, more modern look for the MapPreviewWidget.
