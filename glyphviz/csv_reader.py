import pandas as pd
from .node import Node


def load_node_csv(path: str) -> list[Node]:
    df = pd.read_csv(path)
    nodes = []
    for _, row in df.iterrows():
        nodes.append(Node(
            id=int(row['id']),
            type=int(row['type']),
            parent_id=int(row['parent_id']),
            branch_level=int(row['branch_level']),
            translate_x=float(row['translate_x']),
            translate_y=float(row['translate_y']),
            translate_z=float(row['translate_z']),
            rotate_x=float(row['rotate_x']),
            rotate_y=float(row['rotate_y']),
            rotate_z=float(row['rotate_z']),
            scale_x=float(row['scale_x']),
            scale_y=float(row['scale_y']),
            scale_z=float(row['scale_z']),
            color_r=int(row['color_r']),
            color_g=int(row['color_g']),
            color_b=int(row['color_b']),
            color_a=int(row['color_a']),
            geometry=int(row['geometry']),
            hide=int(row['hide']),
            topo=int(row['topo']),
        ))
    return nodes
