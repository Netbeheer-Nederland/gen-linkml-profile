# -*- coding: utf-8 -*-

from treelib import Tree
from uuid import uuid4
import logging

log = logging.getLogger(__name__)


class TreeVisualiser:
    def __init__(self, nodes):
        self.nodes = nodes
        self.incoming = self._build_incoming_index()
        self.outgoing = self._build_outgoing_index()

    def _build_incoming_index(self):
        incoming = {}
        for source_id, node in self.nodes.items():
            for key, value in node.items():
                if key.startswith('@'):
                    continue
                if isinstance(value, dict) and '@id' in value:
                    incoming.setdefault(value['@id'], []).append(
                        (source_id, key)
                    )
                elif isinstance(value, list):
                    for item in value:
                        target = None
                        if isinstance(item, dict) and '@id' in item:
                            target = item['@id']
                        elif isinstance(item, str):
                            target = item
                        if target:
                            incoming.setdefault(target, []).append(
                                (source_id, key)
                            )
        return incoming

    def _build_outgoing_index(self):
        outgoing = {}
        for source_id, node in self.nodes.items():
            for key, value in node.items():
                if key.startswith('@'):
                    continue
                if isinstance(value, dict) and '@id' in value:
                    outgoing.setdefault(source_id, []).append(
                        (value['@id'], key)
                    )
                elif isinstance(value, list):
                    for item in value:
                        target = None
                        if isinstance(item, dict) and '@id' in item:
                            target = item['@id']
                        elif isinstance(item, str):
                            target = item
                        if target:
                            outgoing.setdefault(source_id, []).append(
                                (target, key)
                            )
        return outgoing

    def label(self, node_id: str, id_only: bool = False) -> str:
        node = self.nodes.get(node_id, {})
        name = (
            node_id
            if id_only
            else (
                node.get('cim:IdentifiedObject.name')
                or node.get('name')
                or node_id[-8:]
            )
        )
        node_type = node.get('@type', '')
        if isinstance(node_type, list):
            node_type = node_type[0]
        node_type = str(node_type).replace('cim:', '')
        return f'{name} [{node_type}]'

    def build_tree(
        self,
        start_id: str,
        max_depth: int = 3,
        id_only: bool = False,
        exclude_types=None,
    ) -> Tree:

        if start_id not in self.nodes:
            raise ValueError(f"Unknown start_id: {start_id}")

        exclude_types = set(exclude_types or [])

        tree = Tree()
        root_id = str(uuid4())

        tree.create_node(
            self.label(start_id, id_only),
            root_id,
        )

        path = set()          # cycle protection (current recursion stack)
        visited = {}          # node_id -> set("IN", "OUT")

        def is_excluded(node_id: str) -> bool:
            node = self.nodes.get(node_id, {})
            node_type = node.get("@type", "")
            if isinstance(node_type, list):
                node_type = node_type[0]
            return node_type in exclude_types

        def walk(cim_id: str, parent: str, depth: int):
            if depth >= max_depth:
                return

            if cim_id in path:
                return

            path.add(cim_id)

            def add_child_or_splice(target_id: str, parent_id: str, next_depth: int, direction: str, rel: str = None):
                if target_id not in self.nodes:
                    return

                if is_excluded(target_id):
                    walk(target_id, parent_id, next_depth)
                    return

                label = self.label(target_id, id_only)
                seen_dirs = visited.setdefault(target_id, set())

                # Already expanded in this direction → render as reference
                if direction in seen_dirs:
                    ref_id = str(uuid4())
                    tree.create_node(
                        f"↩ {label}",
                        ref_id,
                        parent=parent_id,
                    )
                    return

                # Mark direction as expanded
                seen_dirs.add(direction)

                node_id = str(uuid4())
                tree.create_node(
                    label,
                    node_id,
                    parent=parent_id,
                )

                walk(target_id, node_id, next_depth)

            incoming = [
                (src, rel)
                for src, rel in self.incoming.get(cim_id, [])
                if src in self.nodes
            ]

            if incoming:
                in_id = str(uuid4())
                tree.create_node("IN", in_id, parent=parent)

                for src, rel in incoming:
                    add_child_or_splice(src, in_id, depth + 1, "IN", rel)

            outgoing = [
                (tgt, rel)
                for tgt, rel in self.outgoing.get(cim_id, [])
                if tgt in self.nodes
            ]

            if outgoing:
                out_id = str(uuid4())
                tree.create_node("OUT", out_id, parent=parent)

                for tgt, rel in outgoing:
                    add_child_or_splice(tgt, out_id, depth + 1, "OUT", rel)

            path.remove(cim_id)

        walk(start_id, root_id, 0)
        return tree

    def show(
        self,
        start_id: str,
        max_depth: int = 3,
        id_only: bool = False,
        exclude_types=None,
    ):
        if start_id is None:
            start_id = next(iter(self.nodes))

        self.build_tree(
            start_id=start_id,
            max_depth=max_depth,
            id_only=id_only,
            exclude_types=exclude_types,
        ).show()
