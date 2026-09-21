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

    def label(self, node_id: str, full_id: bool = False) -> str:
        """
            cim:TransformerEnd.endNumber
            cim:AnalogValue.value
            cim:Measurement.unitSymbol
            cim:Measurement.unitSymbol
            cim:Measurement.unitMultiplier
        """
        node = self.nodes.get(node_id, {})
        name = (
            node.get('cim:IdentifiedObject.name')
            or node.get('name')
            or node_id[-8:]
        )
        value = (
            node.get('cim:TransformerEnd.endNumber')
            or node.get('cim:AnalogValue.value')
            or node.get('cim:ActivePower.value')
            or None
        )
        name = f'{name} |{value}|' if value else name
        node_type = node.get('@type', '')
        if isinstance(node_type, list):
            node_type = node_type[0]
        node_type = str(node_type).replace('cim:', '')
        node_code = node_id[-8:] if not full_id else node_id
        return f'[{node_type}] {name} ({node_code})'

    def show(
        self,
        start_id: str,
        max_depth: int = 3,
        max_children: int = 5,
        full_id: bool = False,
        recursive: bool = False,
        exclude_types=None,
    ):
        if start_id is None:
            start_id = next(iter(self.nodes))
        start_id = next(
            (k for k in self.nodes if start_id in k),
            None
        )
        self.build_tree(
            start_id=start_id,
            max_depth=max_depth,
            max_children=max_children,
            full_id=full_id,
            recursive=recursive,
            exclude_types=exclude_types,
        ).show()

    def build_tree(
        self,
        start_id: str,
        max_depth: int = 3,
        max_children: int = 5,
        full_id: bool = False,
        recursive: bool = False,
        exclude_types=None
    ) -> Tree:
        if start_id not in self.nodes:
            raise ValueError(f"Unknown start_id: {start_id}")

        exclude_types = set(exclude_types or [])

        tree = Tree()

        root_id = str(uuid4())
        tree.create_node(
            self.label(start_id, full_id),
            root_id,
        )

        # BFS queue:
        # (node_id, tree_parent_id, depth)
        queue = deque([
            (start_id, root_id, 0)
        ])

        # Nodes whose tree representation has already been created.
        # This prevents the same subtree from being expanded more than once.
        expanded_subtrees = {start_id}

        # Nodes currently being processed on the current path.
        # Protects against cycles in the graph.
        path = set()

        def is_excluded(node_id: str) -> bool:
            node = self.nodes.get(node_id, {})
            node_type = node.get("@type", "")

            if isinstance(node_type, list):
                node_type = node_type[0] if node_type else ""

            return node_type in exclude_types

        def is_eligible(node_id: str) -> bool:
            """
            Return whether a node is allowed to appear in the tree.
            """
            return (
                node_id in self.nodes
                and not is_excluded(node_id)
            )

        def can_expand(node_id: str) -> bool:
            """
            Return whether a node can be added to the tree and expanded.

            A node may be eligible but already have its subtree represented
            elsewhere in the tree. In that case it is not added again.
            """
            return (
                is_eligible(node_id)
                and node_id not in expanded_subtrees
            )

        def expand(
            target_id: str,
            parent: str,
            next_depth: int,
            rel: str = None,
        ) -> bool:
            """
            Add a target node to the tree and queue it for expansion.

            Returns True when the node was actually added.
            """
            if not can_expand(target_id):
                return False

            child_id = str(uuid4())

            tree.create_node(
                self.label(target_id, full_id),
                child_id,
                parent=parent,
            )

            # Mark it immediately, rather than when it is dequeued.
            # This prevents multiple references in the same level from
            # queuing the same subtree.
            expanded_subtrees.add(target_id)

            queue.append((
                target_id,
                child_id,
                next_depth,
            ))

            return True

        def add_relationship_group(
            relationships,
            label: str,
            parent_id: str,
            depth: int,
        ):
            """
            Add an IN or OUT group.

            Only nodes that can actually be added are considered.
            At most max_children nodes are added. If more eligible
            children exist, the group label indicates truncation.
            """

            # Filter before truncating. This is important: excluded nodes
            # and nodes whose subtree has already been expanded should not
            # count towards the limit.
            candidates = [
                (node_id, rel)
                for node_id, rel in relationships
                if can_expand(node_id)
            ]

            if not candidates:
                return

            total = len(candidates)
            truncated = total > max_children

            # The actual children are limited to max_children.
            selected = candidates[:max_children]

            if truncated:
                group_label = f"{label} (showing {max_children} of {total})"
            else:
                group_label = label

            group_id = str(uuid4())

            tree.create_node(
                group_label,
                group_id,
                parent=parent_id,
            )

            for target_id, rel in selected:
                expand(
                    target_id,
                    group_id,
                    depth + 1,
                    rel,
                )

        while queue:
            node_id, parent_id, depth = queue.popleft()

            # The node itself is still shown at max_depth, but its children
            # are not expanded.
            # if depth >= max_depth:
            #     continue

            # The node itself is still shown at max_depth, but its children
            # are not expanded. Add an explicit end marker so that it is
            # visible that this is the end of the recursive expansion.
            if depth >= max_depth:
                if not recursive:
                    continue
                relationships = (
                    self.outgoing.get(node_id, [])
                    + self.incoming.get(node_id, [])
                )

                for target_id, rel in relationships:
                    if target_id in self.nodes and not is_excluded(target_id):
                        end_id = str(uuid4())
                        tree.create_node(
                            f"↩ {self.label(target_id, full_id)}",
                            end_id,
                            parent=parent_id,
                        )
                        break

                continue

            # Additional cycle protection.
            if node_id in path:
                continue

            path.add(node_id)

            try:
                add_relationship_group(
                    self.incoming.get(node_id, []),
                    "IN",
                    parent_id,
                    depth,
                )

                add_relationship_group(
                    self.outgoing.get(node_id, []),
                    "OUT",
                    parent_id,
                    depth,
                )

            finally:
                path.remove(node_id)

        return tree
