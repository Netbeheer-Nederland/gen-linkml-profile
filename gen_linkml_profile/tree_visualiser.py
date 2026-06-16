# -*- coding: utf-8 -*-

from treelib import Tree
from uuid import uuid4
from collections import deque
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
        tree.create_node(self.label(start_id, id_only), root_id)
        # BFS queue: (node_id, tree_parent_id, depth)
        queue = deque([(start_id, root_id, 0)])
        # cycle protection (global path guard)
        path = set()
        # subtree dedup (critical for BaseVoltage etc.)
        expanded_subtrees = set()

        def is_excluded(node_id: str) -> bool:
            node = self.nodes.get(node_id, {})
            node_type = node.get("@type", "")
            if isinstance(node_type, list):
                node_type = node_type[0]
            return node_type in exclude_types

        while queue:
            node_id, parent_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            if node_id in path:
                continue
            path.add(node_id)

            try:
                def expand(target_id: str, parent: str, next_depth: int, rel: str = None):
                    if target_id not in self.nodes:
                        return
                    if is_excluded(target_id):
                        queue.append((target_id, parent, next_depth))
                        return
                    label = self.label(target_id, id_only)
                    # subtree dedup: show reference instead of re-expanding
                    if target_id in expanded_subtrees:
                        ref_id = str(uuid4())
                        tree.create_node(
                            f"↩ {label}",
                            ref_id,
                            parent=parent,
                        )
                        return
                    expanded_subtrees.add(target_id)
                    child_id = str(uuid4())
                    tree.create_node(
                        label,
                        child_id,
                        parent=parent,
                    )
                    queue.append((target_id, child_id, next_depth))

                incoming = [
                    (src, rel)
                    for src, rel in self.incoming.get(node_id, [])
                    if src in self.nodes
                ]
                if incoming:
                    in_id = str(uuid4())
                    tree.create_node("IN", in_id, parent=parent_id)
                    for src, rel in incoming:
                        expand(src, in_id, depth + 1, rel)

                outgoing = [
                    (tgt, rel)
                    for tgt, rel in self.outgoing.get(node_id, [])
                    if tgt in self.nodes
                ]
                if outgoing:
                    out_id = str(uuid4())
                    tree.create_node("OUT", out_id, parent=parent_id)
                    for tgt, rel in outgoing:
                        expand(tgt, out_id, depth + 1, rel)
            finally:
                path.remove(node_id)
        return tree
