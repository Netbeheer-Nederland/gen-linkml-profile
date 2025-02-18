# -*- coding: utf-8 -*-

from dataclasses import dataclass
from re import split
from yaml import dump, SafeDumper
from copy import copy, deepcopy
from uuid import uuid4
from datetime import datetime

from linkml.utils.schema_builder import SchemaBuilder
from linkml.utils.helpers import convert_to_snake_case

from networkx import DiGraph, all_shortest_paths, all_simple_paths
from linkml_runtime.utils.schemaview import (SchemaView,
                                             load_schema_wrap,
                                             SLOTS,
                                             CLASSES,
                                             ENUMS,
                                             SUBSETS,
                                             TYPES)
from linkml_runtime.linkml_model.meta import (ClassDefinition,
                                              SlotDefinition,
                                              EnumDefinition,
                                              TypeDefinition,
                                              SchemaDefinition)
import logging
log = logging.getLogger(__name__)


@dataclass
class ProfilingSchemaBuilder(SchemaBuilder):
    """ """
    def stats(self):
        c, t, e = (len(self.schema.classes), len(self.schema.types),
                   len(self.schema.enums))
        log.info(f'Profiling [{c}] classes, [{t}] types and [{e}] enums')

    def has_class(self, c_name):
        return c_name in self.schema.classes

    def has_slot(self, s_name):
        return s_name in self.schema.slots

    def has_type(self, t_name):
        return t_name in self.schema.types

    def has_enum(self, e_name):
        return e_name in self.schema.enums


class IndentDumper(SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(IndentDumper, self).increase_indent(flow, False)


class SchemaProfiler(object):
    """Helper class to profile LinkML schemas."""
    def __init__(self, yamlfile, c_names=None):
        # Load SchemaDefinition from YAML file, to copy from
        self.schema = self._load_schema(yamlfile)
        # Create a SchemaView to use as wrapper for querying the schema
        self.view = SchemaView(deepcopy(self.schema), merge_imports=False)
        self.c_names = []
        c_names = c_names if c_names is not None else []
        for c_name in c_names:
            try:
                # Add the subclass hierarchy to c_names
                for a_name in self.view.class_ancestors(c_name):
                    if a_name in self.c_names:
                        continue
                    self.c_names.append(a_name)
            except ValueError as e:
                log.warning(e)
        c, t, en = (len(self.view.all_classes()), len(self.view.all_types()),
                    len(self.view.all_enums()))
        self._uuid = {}
        log.info(f'Schema contains [{c}] classes, [{t}] types and [{en}] enums')

    def _load_schema(self, yamlfile):
        """Create a SchemaDefinition for the provided YAML file."""
        from linkml_runtime.loaders.yaml_loader import YAMLLoader
        yaml_loader = YAMLLoader()
        schema: SchemaDefinition
        return yaml_loader.load_any(yamlfile, target_class=SchemaDefinition)

    def _create_builder(self):
        """Create a new Builder object based on the provided view."""
        builder = ProfilingSchemaBuilder(id=self.schema.id,
                                         name=self.schema.name)
        builder.schema.title = self.schema.title
        builder.schema.description = self.schema.description
        # Imports & CURI maps
        builder.schema.imports = self.schema.imports
        builder.schema.default_prefix = self.schema.default_prefix
        builder.schema.default_range = self.schema.default_range
        builder.schema.default_curi_maps = self.schema.default_curi_maps
        # Add namespaces for URIs
        for prefix in self.schema.prefixes.values():
            builder.add_prefix(prefix.prefix_prefix, prefix.prefix_reference)
        return builder

    def _range_is_class(self, s_def):
        """ """
        return True if self.view.get_class(s_def.range) else False

    def _profile(self, name, builder):
        """Profile schema elements recursively."""
        elem = self.view.get_element(name, imports=False)
        if elem is None:
            return
        if isinstance(elem, ClassDefinition):
            if builder.has_class(elem.name):
                return
            log.info('{s:-^80}'.format(s=f' {elem.name} '))
            log.debug(f'Adding class "{name}"')
            # Use the class from the SchemaDefinition, _not_ the SchemaView
            elem = self.schema[CLASSES][elem.name]
            builder.add_class(elem)
            # Find all children for this class
            children = self.view.class_children(elem.name)
            if len(children) > 0:
                log.info(f'Class {elem.name} has children: ' + ', '.join(children[:3]) + ' ...')
            # Find all classes that have a slot with range equal to this class
            for c_def in self.view.all_classes().values():
                for s_def in c_def.attributes.values():
                    if s_def.range == elem.name and c_def.name not in self.c_names:
                        log.info(f'Class "{elem.name}" is used as range for slot "{c_def.name}::{s_def.name}"')
            attr = {}
            for s_name, s_def in elem['attributes'].items():
                r_name = s_def.range
                # Range must be a valid schema element
                if not self.view.get_element(r_name):
                    raise ValueError(f'Range "{r_name}" for "{elem.name}::{s_name}" is not in schema')
                # Skip any classes that were not requested
                is_class = True if self.view.get_class(r_name) else False
                if is_class and r_name not in self.c_names:
                    opt = 'REQUIRED' if s_def.required else 'optional'
                    log.warning(f'Skipping {opt} slot "{elem.name}::{s_name}" with range: "{r_name}"')
                    continue
                attr[s_name] = s_def
            elem['attributes'] = attr
            for s_def in attr.values():
                # Process each attribute separately to simplify logging
                self._profile(s_def.range, builder)
        if isinstance(elem, SlotDefinition):
            # Process slots recursively
            pass
        if isinstance(elem, TypeDefinition):
            if builder.has_type(elem.name):
                return
            log.debug(f'Adding type "{name}"')
            builder.add_type(elem)
        if isinstance(elem, EnumDefinition):
            if builder.has_enum(elem.name):
                return
            log.debug(f'Adding enum "{name}"')
            builder.add_enum(elem)

    def profile(self):
        """Create a new LinkML schema based on the provided class name(s) and
        their dependencies.
        """
        builder = self._create_builder()
        log.info(f'Profiling classes: {", ".join(sorted(self.c_names))}')
        for c_name in self.c_names:
            try:
                self._profile(c_name, builder)
            except ValueError as e:
                log.warning(e)
        log.info('{s:-^80}'.format(s=' Statistics '))
        builder.stats()
        return builder.schema

    def _snake_case(self, s):
        # return ''.join('_' + c if c.isupper() else c for c in s).strip()
        return convert_to_snake_case(s)

    def _pluralise(self, s):
        """Create the plural for a singular noun, in English. Ignores edge
        cases"""
        # Apply common rules for regular plurals
        if s.endswith('y') and s[-2] not in 'aeiou':
            return s[:-1] + 'ies'  # e.g., "city" -> "cities"
        elif s.endswith(('s', 'x', 'z', 'ch', 'sh')):
            return s + 'es'  # e.g., "box" -> "boxes"
        else:
            return s + 's'  # e.g., "dog" -> "dogs"

    def iterate_range(self, c_name, skip=False, p_name=None):
        """Process a hierarchy of classes by following the ranges"""
        c_def = self.view.induced_class(c_name)
        if c_def is None:
            return
        for s_name, s_def in c_def.attributes.items():
            log.debug(f'Processing {c_def.name}::{s_name}')
            if not s_def.required and skip:
                continue
            elem = self.view.get_element(s_def.range)
            if elem is None:
                continue
            if isinstance(elem, ClassDefinition):
                # Check for infinite recursion
                if elem.name == p_name:
                    raise RecursionError(f'{p_name} refers to {c_name}')
                yield((c_def.name, elem.name, s_name))
                yield from self.iterate_range(elem.name, skip, c_def.name)

    def pydantic(self, attr, fix_doc):
        """Pre-process the schema for use by gen-pydantic."""
        for c_name, c_def in self.schema[CLASSES].items():
            # Process classes in the schema, not a copy of c_def through SchemaView
            if 'attributes' not in c_def:
                continue
            # Fix documentation
            if fix_doc and c_def.description is not None:
                # Clean up description
                c_def.description = ' '.join(split(r'\s+', c_def.description))
            # Convert attributes to snake_case
            attributes = {}
            for s_name, s_def in c_def['attributes'].items():
                if s_name in attr:
                    snake_case = attr[s_name]
                    log.info(f'Processing "{c_name}::{s_name}" as "{snake_case}"')
                else:
                    snake_case = self._snake_case(s_name)
                    log.debug(f'Processing "{c_name}::{s_name}" as "{snake_case}"')
                if fix_doc and s_def.description is not None:
                    # Clean up description
                    s_def.description = ' '.join(split(r'\s+', s_def.description))
                # Replace reference
                attributes[snake_case] = s_def
            self.schema.classes[c_name]['attributes'] = attributes
        return self.schema

    def leaves(self):
        """Log all leaf classes (classes without parents)."""
        log.info('Schema contains the following leaves: ' +
                 ', '.join(self.view.class_leaves(imports=False)))

    def lint(self):
        """Check the schema for common problems."""
        # Are all used ranges valid?
        for c_name, c_def in self.schema[CLASSES].items():
            for s_name, s_def in c_def['attributes'].items():
                elem = self.view.get_element(s_def.range)
                if elem is None:
                    attr = f'{c_name}::{s_name}'
                    log.error(f'Range "{s_def.range}" for {attr} not found')

    def merge(self, from_schema, clobber=False):
        """Merge the provided schema into this schema."""
        schema = self._load_schema(from_schema)
        # Copied from SchemaView
        dest = self.schema
        for k, v in schema.prefixes.items():
            if clobber or k not in dest.prefixes:
                dest.prefixes[k] = copy(v)
        for k, v in schema.classes.items():
            if clobber or k not in dest.classes:
                dest.classes[k] = copy(v)
            for a_k, a_v in v.attributes.items():
                # Copy attributes as well
                if clobber or a_k not in dest.classes[k]['attributes']:
                    dest.classes[k]['attributes'][a_k] = copy(a_v)
        for k, v in schema.slots.items():
            if clobber or k not in dest.slots:
                dest.slots[k] = copy(v)
        for k, v in schema.types.items():
            if clobber or k not in dest.types:
                dest.types[k] = copy(v)
        for k, v in schema.enums.items():
            if clobber or k not in dest.enums:
                dest.enums[k] = copy(v)
        for k, v in schema.subsets.items():
            if clobber or k not in dest.subsets:
                dest.subsets[k] = copy(v)
        return self.schema

    def _get_uuid(self, identifier):
        """Get a uuid4 for an identifier."""
        if identifier not in self._uuid:
            log.debug(f'Generating uuid for "{identifier}"')
            self._uuid[identifier] = str(uuid4())
        return self._uuid[identifier]

    def _class_instance(self, c_name, skip=False, populate=False, prev=None):
        """Generate a class instance. Supports inlining of classes."""
        c_def = self.view.induced_class(c_name)
        # Find ancestors for encapsulating class
        if prev is not None:
            ancestors = self.view.class_ancestors(prev)
        else:
            ancestors = []
        # Process attributes
        obj = {}
        for s_name, s_def in c_def.attributes.items():
            if not s_def.required and skip:
                log.debug(f'Skipping optional attribute "{c_name}::{s_name}"')
                continue
            if s_def.range in ancestors:
                # Do not recurse indefinitely
                log.error(f'"{c_name}" refers back to {s_def.range}" as "{prev}"')
                continue
            s_range = self.view.get_element(s_def.range)
            s_val = ''
            if self.view.is_inlined(s_def):
                # Inlined processing
                log.debug(f'Processing "{c_name}::{s_name}" as inlined list')
                s_val = self._class_instance(s_def.range, skip, populate,
                                             c_name)
                if s_def.multivalued:
                    s_val = [s_val]
            else:
                # Not-inlined processing
                if isinstance(s_range, TypeDefinition) and s_range.typeof is not None:
                    # FIXME: how broken is this assumption?
                    log.debug(f'Resolving type "{s_def.range}" to "{s_range.typeof}"')
                    s_def.range = s_range.typeof
                if isinstance(s_range, ClassDefinition):
                    log.debug(f'Processing "{s_def.range}" as range')
                    id_range = self.view.get_identifier_slot(s_def.range)
                    if id_range is not None:
                        s_val = self._get_uuid(f'{s_def.range}.{id_range.name}')
                        if s_def.multivalued:
                            s_val = [s_val]
                if s_def.slot_uri.split(':')[1] == 'conformsTo':
                    # Throw away prefix and hope this works
                    s_val = self.schema.id
                if s_def.slot_uri == 'owl:versionInfo':
                    s_val = self.schema.version
                if s_def.range in ['integer', 'float', 'double']:
                    s_val = 2 if populate else ''
                if s_def.range == 'boolean':
                    s_val = True if populate else ''
                if s_def.range == 'date':
                    s_val = datetime.now().strftime('%Y-%m-%d') if populate else ''
                if s_def.range == 'datetime':
                    # This is a mess: linkml validate and convert support
                    # different time formats, which means it can never be
                    # correct.
                    s_val = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ') if populate else ''
                    # s_val = datetime.now().isoformat()
                if isinstance(s_range, EnumDefinition):
                    # This is an enum, use the first permissable value
                    s_val = list(s_range.permissible_values.keys()).pop(0) if populate else ''
                if s_def.range == 'string' and s_def.identifier:
                    # Only add a string if the identifier is a string
                    s_val = self._get_uuid(f'{c_name}.{s_name}') if populate else ''
            # Store value
            obj[s_name] = s_val
        return obj

    def example(self, c_name, skip=False):
        """Generate an example YAML file"""
        # Output to YAML
        return dump(self._class_instance(c_name,skip=skip, populate=True),
                    Dumper=IndentDumper, sort_keys=False, allow_unicode=True)

    def _set_value(self, dataset, values):
        """Create a new instance based on the provided template."""
        # Template instance is expected at index 0
        obj = {}
        # Add values
        for k, v in values.items():
            # Disallow any values not in the template
            if k not in dataset:
                continue
            # Copy each key/value to the
            obj[k] = v
        return obj

    def _value_exists(self, dataset, key, value):
        """ """
        return any(item[key] == value for item in dataset)

    def _get_slots_by_range(self, range_name):
        """ """
        range_slots = []
        for s in self.view.all_slots().values():
            if s.range == range_name and s not in range_slots:
                range_slots.append(s)
        return range_slots

    def dataset(self, class_name=None, leaves=True):
        """Generate a dataset class. This is handled best-effort, i.e.
        inheritance is not handled correctly and needs to be manually
        corrected."""
        class_name = 'DataSet' if class_name is None else class_name
        # Initial DataSet
        dataset = {'description': 'A single instance of a published dataset.',
                   'attributes': {
                       'identifier': {'slot_uri': 'dct:identifier',
                                      'multivalued': False,
                                      'required': True},
                       'conforms_to': {'slot_uri': 'dct:conformsTo',
                                       'multivalued': False,
                                       'required': True},
                       'contact_point': {'slot_uri': 'dct:contactPoint',
                                         'multivalued': False,
                                         'required': True},
                       'release_date': {'slot_uri': 'dct:issued',
                                        'multivalued': False,
                                        'required': True},
                       'version': {'slot_uri': 'owl:versionInfo',
                                   'multivalued': False,
                                   'required': True}},
                   'class_uri': f'this:{class_name}',
                   'tree_root': True}
        # Process all classes as an attribute
        classes = (self.view.class_leaves() if leaves else
                   self.view.all_classes())
        for c_range in classes:
            # Skip inlined classes
            is_inlined = []
            for s_def in self._get_slots_by_range(c_range):
                is_inlined.append(self.view.is_inlined(s_def))
            if len(is_inlined) > 0 and all(is_inlined):
                log.info(f'Skipping inlined range {c_range}')
                continue
            # Convert to camelCase, IF naming convention has been followed
            c_plural = self._pluralise(c_range)
            c_name = c_plural[0].lower() + c_plural[1:]
            attr = {'description': f'All instances of {c_range}-s',
                    'slot_uri': f'this:{class_name}.{c_name}',
                    'multivalued': True,
                    'range': c_range,
                    'required': True,
                    'inlined_as_list': True}
            dataset['attributes'][self._snake_case(f'{c_plural}')] = attr
        # Convert to YAML
        return dump({f'{class_name}': dataset}, Dumper=IndentDumper,
                    sort_keys=False, allow_unicode=True)

    def shortest_path(self, source, destination):
        """Find the shortest path."""
        G = DiGraph()
        # Add classes
        G.add_nodes_from(self.view.all_classes().keys())
        # Process edges
        for c_name in G.copy().nodes():
            # log.info(f'Processing class "{c_name}"')
            c_def = self.view.get_class(c_name)
            if c_def.is_a:
                # G.add_edge(c_name, c_def.is_a, relation='specialise')
                G.add_edge(c_def.is_a, c_name, relation='generalise')
            for s_name, s_def in c_def.attributes.items():
                if not self._range_is_class(s_def):
                    continue
                if s_def.range not in G:
                    raise ValueError(f'Range "{s_def.range}" not in schema')
                G.add_edge(c_name, s_def.range, relation='associate')
        log.info(G)
        for i, path in enumerate(all_shortest_paths(G, source, destination),
                                 start=1):
            # Log command line for use by "profile"
            log.info(f'Path {i:02d} (cmdline): -c ' + ' -c '.join(path))
