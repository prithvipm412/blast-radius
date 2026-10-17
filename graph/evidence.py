"""Keep graph identity and edge direction when serializing query evidence."""

from falkordb.edge import Edge
from falkordb.node import Node
from falkordb.path import Path


def node_dict(node):
    out = {
        "id": node.properties["id"],
        "label": node.labels[0],
        "name": node.properties["name"],
        "synthetic": node.properties["synthetic"],
    }
    # Optional: only present once critical_services() has scored this Service node.
    # The frontend uses it to size nodes by structural importance (PageRank).
    criticality = node.properties.get("criticality")
    if criticality is not None:
        out["criticality"] = criticality
    return out


class Evidence:
    def __init__(self):
        self.nodes = {}
        self.edges = {}

    def add(self, value):
        if isinstance(value, Node):
            if not value.properties.get("operational", False):
                self.nodes[value.id] = value
        elif isinstance(value, Edge):
            if not value.properties.get("operational", False):
                self.edges[value.id] = value
        elif isinstance(value, Path):
            self.add(value.nodes())
            self.add(value.edges())
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.add(item)

    def render(self):
        nodes = {n.properties["id"]: node_dict(n) for n in self.nodes.values()}
        edges = {}
        for e in self.edges.values():
            src = e.src_node.id if isinstance(e.src_node, Node) else e.src_node
            dst = e.dest_node.id if isinstance(e.dest_node, Node) else e.dest_node
            if src not in self.nodes or dst not in self.nodes:
                continue
            source, target = self.nodes[src].properties["id"], self.nodes[dst].properties["id"]
            key = (source, target, e.relation)
            edges[key] = {
                "source": source,
                "target": target,
                "type": e.relation,
                "synthetic": e.properties["synthetic"],
            }
        return {
            "nodes": [nodes[k] for k in sorted(nodes)],
            "edges": [edges[k] for k in sorted(edges)],
        }
