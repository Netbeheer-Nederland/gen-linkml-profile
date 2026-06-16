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
                    incoming.setdefault(value['@id'], []).append((source_id, key))
                elif isinstance(value, list):
                    for item in value:
                        target = None
                        if isinstance(item, dict) and '@id' in item:
                            target = item['@id']
                        elif isinstance(item, str):
                            target = item
                        if target:
                            incoming.setdefault(target, []).append((source_id, key))
        return incoming

    def _build_outgoing_index(self):
        outgoing = {}
        for source_id, node in self.nodes.items():
            for key, value in node.items():
                if key.startswith('@'):
                    continue
                if isinstance(value, dict) and '@id' in value:
                    outgoing.setdefault(source_id, []).append((value['@id'], key))
                elif isinstance(value, list):
                    for item in value:
                        target = None
                        if isinstance(item, dict) and '@id' in item:
                            target = item['@id']
                        elif isinstance(item, str):
                            target = item
                        if target:
                            outgoing.setdefault(source_id, []).append((target, key))
        return outgoing

    def label(self, node_id: str, id_only: bool = False) -> str:
        node = self.nodes.get(node_id, {})
        name = node_id if id_only else (
            node.get('cim:IdentifiedObject.name')
            or node.get('name')
            or node_id[-12:]
        )
        node_type = node.get('@type', '')
        if isinstance(node_type, list):
            node_type = node_type[0]
        node_type = str(node_type).replace('cim:', '')
        return f'{name} [{node_type}]'

    def build_tree(self, start_id: str, max_depth: int = 3,
                   id_only: bool= False) -> Tree:
        if start_id not in self.nodes:
            raise ValueError(f'Unknown start_id: {start_id}')
        tree = Tree()
        root_id = str(uuid4())
        tree.create_node(self.label(start_id), root_id)

        path = set()

        def walk(cim_id: str, parent: str, depth: int):
            if depth >= max_depth:
                return

            if cim_id in path:
                # ref_id = str(uuid4())
                # tree.create_node(
                #     f'↩ {self.label(cim_id)} (cycle)',
                #     ref_id,
                #     parent=parent,
                # )
                return

            path.add(cim_id)

            # incoming
            in_id = str(uuid4())
            tree.create_node('IN', in_id, parent=parent)
            for src, rel in self.incoming.get(cim_id, []):
                if src not in self.nodes:
                    continue
                # rel_id = str(uuid4())
                # tree.create_node(rel.replace('cim:', ''), rel_id, parent=in_id)
                child_id = str(uuid4())
                # tree.create_node(self.label(src, id_only), child_id, parent=rel_id)
                tree.create_node(self.label(src, id_only), child_id, parent=in_id)
                walk(src, child_id, depth + 1)

            # outgoing
            out_id = str(uuid4())
            tree.create_node('OUT', out_id, parent=parent)
            for tgt, rel in self.outgoing.get(cim_id, []):
                if tgt not in self.nodes:
                    continue
                # rel_id = str(uuid4())
                # tree.create_node(rel.replace('cim:', ''), rel_id, parent=out_id)
                child_id = str(uuid4())
                # tree.create_node(self.label(tgt, id_only), child_id, parent=rel_id)
                tree.create_node(self.label(tgt, id_only), child_id, parent=out_id)
                walk(tgt, child_id, depth + 1)
            path.remove(cim_id)

        walk(start_id, root_id, 0)
        return tree

    def show(self, start_id: str, max_depth: int = 3, id_only: bool = False):
        if start_id is None:
            start_id = next(iter(self.nodes))
        self.build_tree(start_id, max_depth, id_only).show()
