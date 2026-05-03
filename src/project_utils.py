import json
import zlib
import base64
import numpy as np
from dataclasses import asdict, is_dataclass
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from src.config_model import GUIConfigModel
from src.terrain_spec import LayoutNode, LayoutConnection, ZoneType

CURRENT_PROJECT_VERSION = 1

def array_to_b64(arr: np.ndarray) -> str:
    """Compress and encode a numpy array to a base64 string."""
    if arr is None:
        return None
    compressed = zlib.compress(arr.tobytes())
    return base64.b64encode(compressed).decode('utf-8')

def b64_to_array(b64: str, dtype: Any, shape: Tuple[int, ...]) -> np.ndarray:
    """Decode and decompress a base64 string back to a numpy array."""
    if b64 is None:
        return None
    try:
        decompressed = zlib.decompress(base64.b64decode(b64))
        return np.frombuffer(decompressed, dtype=dtype).reshape(shape).copy()
    except Exception as e:
        print(f"Error decompressing array: {e}")
        return None

def save_project(path: str, config: GUIConfigModel, layout_data: Dict[str, Any]):
    """
    Save the project to a .terrain file.
    layout_data should contain: nodes, connections, resources, imp_base, nf_base, height_overlay, global_mask, map_name
    """
    # 1. Prepare Nodes with unique IDs
    nodes = layout_data.get("nodes", [])
    node_to_id = {node: i for i, node in enumerate(nodes)}
    
    serialized_nodes = []
    for node in nodes:
        serialized_nodes.append(asdict(node))

    # 2. Prepare Connections using Node IDs
    connections = layout_data.get("connections", [])
    serialized_connections = []
    for conn in connections:
        conn_dict = asdict(conn)
        # Replace node objects with IDs
        conn_dict["start_node_id"] = node_to_id.get(conn.start_node)
        conn_dict["end_node_id"] = node_to_id.get(conn.end_node)
        # Remove the nested full node dicts to save space and avoid recursion issues
        conn_dict.pop("start_node", None)
        conn_dict.pop("end_node", None)
        serialized_connections.append(conn_dict)

    # 3. Prepare sculpting data
    height_overlay = layout_data.get("height_overlay")
    global_mask = layout_data.get("global_mask")
    
    sculpt_data = {}
    if height_overlay is not None:
        sculpt_data["height_overlay"] = array_to_b64(height_overlay)
        sculpt_data["height_overlay_shape"] = height_overlay.shape
        sculpt_data["height_overlay_dtype"] = str(height_overlay.dtype)
    
    if global_mask is not None:
        sculpt_data["global_mask"] = array_to_b64(global_mask)
        sculpt_data["global_mask_shape"] = global_mask.shape
        sculpt_data["global_mask_dtype"] = str(global_mask.dtype)

    # 4. Final project structure
    project = {
        "version": CURRENT_PROJECT_VERSION,
        "map_name": layout_data.get("map_name", "gui_terrain"),
        "config": asdict(config),
        "layout": {
            "nodes": serialized_nodes,
            "connections": serialized_connections,
            "resources": layout_data.get("resources", []),
            "imp_base": layout_data.get("imp_base"),
            "nf_base": layout_data.get("nf_base"),
        },
        "sculpt": sculpt_data
    }

    with open(path, 'w') as f:
        json.dump(project, f, indent=2)

def load_project(path: str) -> Dict[str, Any]:
    """
    Load a project from a .terrain file.
    Returns a dict with reconstructed objects.
    """
    with open(path, 'r') as f:
        project = json.load(f)

    version = project.get("version", 0)
    if version < 1:
        # We could implement migrations here in the future
        pass

    # 1. Reconstruct Config
    config_dict = project.get("config", {})
    config = GUIConfigModel(**{k: v for k, v in config_dict.items() if k in GUIConfigModel.__dataclass_fields__})

    # 2. Reconstruct Layout
    layout_data = project.get("layout", {})
    
    # Reconstruct Nodes
    nodes_list = []
    id_to_node = {}
    for i, node_dict in enumerate(layout_data.get("nodes", [])):
        node = LayoutNode(**node_dict)
        nodes_list.append(node)
        id_to_node[i] = node

    # Reconstruct Connections
    connections_list = []
    for conn_dict in layout_data.get("connections", []):
        start_node_id = conn_dict.pop("start_node_id", None)
        end_node_id = conn_dict.pop("end_node_id", None)
        
        # Re-attach node objects
        if start_node_id is not None:
            conn_dict["start_node"] = id_to_node.get(start_node_id)
        if end_node_id is not None:
            conn_dict["end_node"] = id_to_node.get(end_node_id)
            
        conn = LayoutConnection(**{k: v for k, v in conn_dict.items() if k in LayoutConnection.__dataclass_fields__})
        connections_list.append(conn)

    # 3. Reconstruct Sculpting Data
    sculpt_data = project.get("sculpt", {})
    height_overlay = None
    if "height_overlay" in sculpt_data:
        height_overlay = b64_to_array(
            sculpt_data["height_overlay"],
            np.dtype(sculpt_data["height_overlay_dtype"]),
            tuple(sculpt_data["height_overlay_shape"])
        )
    
    global_mask = None
    if "global_mask" in sculpt_data:
        global_mask = b64_to_array(
            sculpt_data["global_mask"],
            np.dtype(sculpt_data["global_mask_dtype"]),
            tuple(sculpt_data["global_mask_shape"])
        )

    return {
        "config": config,
        "map_name": project.get("map_name", "gui_terrain"),
        "nodes": nodes_list,
        "connections": connections_list,
        "resources": layout_data.get("resources", []),
        "imp_base": layout_data.get("imp_base"),
        "nf_base": layout_data.get("nf_base"),
        "height_overlay": height_overlay,
        "global_mask": global_mask
    }
