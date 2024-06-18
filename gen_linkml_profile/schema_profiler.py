# -*- coding: utf-8 -*-

from dataclasses import dataclass
from re import split
from yaml import load, CBaseLoader
from copy import deepcopy

from linkml.utils.schema_builder import SchemaBuilder
from linkml.utils.helpers import convert_to_snake_case

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


class SchemaProfiler(object):
    """Helper class to profile LinkML schemas."""
    def __init__(self, yamlfile, c_names=None):
        # Load SchemaDefinition from YAML file, to copy from
        from linkml_runtime.loaders.yaml_loader import YAMLLoader
        yaml_loader = YAMLLoader()
        schema: SchemaDefinition
        self.schema = yaml_loader.load_any(yamlfile, target_class=SchemaDefinition)
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
        log.info(f'Schema contains [{c}] classes, [{t}] types and [{en}] enums')

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

    def pydantic(self, attr, fix_doc):
        """Pre-process the schema for use by gen-pydantic."""
        for c_name, c_def in self.schema[CLASSES].items():
            # Process classes in the schema, not a copy of c_def through SchemaView
            if 'attributes' not in c_def:
                continue
            # Fix documentation
            if fix_doc and c_def.description is not None:
                # Clean up description
                c_def.description = ' '.join(split('\s+', c_def.description))
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
                    s_def.description = ' '.join(split('\s+', s_def.description))
                # Replace reference
                attributes[snake_case] = s_def
            self.schema.classes[c_name]['attributes'] = attributes
        return self.schema
