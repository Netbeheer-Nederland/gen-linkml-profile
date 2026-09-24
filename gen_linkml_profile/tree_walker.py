# -*- coding: utf-8 -*-

from collections.abc import Iterable
import logging

log = logging.getLogger(__name__)


class TreeWalker:
    def __init__(
        self,
        objects: dict[str, dict],
        stop_properties: Iterable[str] | None = None,
    ):
        self.objects = objects
        self.stop_properties = set(stop_properties or [])

        # Reverse index:
        # referenced @id -> objects that reference it
        self._incoming = self._build_incoming_index()

    def _build_incoming_index(self) -> dict[str, set[str]]:
        incoming: dict[str, set[str]] = {}

        for object_id, obj in self.objects.items():
            for predicate, value in obj.items():
                if predicate == "@id":
                    continue

                for referenced_id in self._referenced_ids(value):
                    incoming.setdefault(referenced_id, set()).add(object_id)

        return incoming

    @staticmethod
    def _referenced_ids(value) -> set[str]:
        """Return all @id references contained in a JSON-LD value."""

        if isinstance(value, dict):
            if "@id" in value:
                return {value["@id"]}

            return {
                referenced_id
                for nested_value in value.values()
                for referenced_id in TreeWalker._referenced_ids(nested_value)
            }

        if isinstance(value, list):
            return {
                referenced_id
                for item in value
                for referenced_id in TreeWalker._referenced_ids(item)
            }

        return set()

    def related_objects(self, root_id: str) -> dict[str, dict]:
        """
        Return all objects related to root_id.

        Both outgoing and incoming relationships are followed.

        Properties in stop_properties are not traversed. The referenced
        object therefore remains outside the result unless it is reached
        through another traversable relationship.
        """

        if root_id not in self.objects:
            raise KeyError(f"Unknown root_id: {root_id}")

        result: dict[str, dict] = {}
        visited: set[str] = set()

        def visit(object_id: str):
            if object_id in visited:
                return

            if object_id not in self.objects:
                return

            visited.add(object_id)
            obj = self.objects[object_id]
            result[object_id] = obj

            # Outgoing relationships
            for predicate, value in obj.items():
                if predicate == "@id":
                    continue

                if predicate in self.stop_properties:
                    continue

                for referenced_id in self._referenced_ids(value):
                    visit(referenced_id)

            # Incoming relationships
            for referencing_id in self._incoming.get(object_id, ()):
                referencing_obj = self.objects[referencing_id]

                # Only follow the incoming relationship if the property
                # pointing to object_id is not a stop property.
                if self._has_traversable_reference(
                    referencing_obj,
                    object_id,
                ):
                    visit(referencing_id)

        visit(root_id)

        return result

    def _has_traversable_reference(
        self,
        obj: dict,
        target_id: str,
    ) -> bool:
        """Check whether obj references target_id through a non-stop property."""

        for predicate, value in obj.items():
            if predicate == "@id":
                continue

            if predicate in self.stop_properties:
                continue

            if target_id in self._referenced_ids(value):
                return True

        return False
