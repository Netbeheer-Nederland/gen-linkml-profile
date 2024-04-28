# -*- coding: utf-8 -*-

from dataclasses import dataclass
from re import split

from linkml_runtime.utils.schemaview import SchemaView
from linkml.utils.schema_builder import SchemaBuilder
from linkml.utils.helpers import convert_to_snake_case
from linkml_runtime.utils.schemaview import SchemaView
from linkml_runtime.linkml_model.meta import (ClassDefinition,
                                              SlotDefinition,
                                              EnumDefinition,
                                              TypeDefinition)
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
    def __init__(self, view, c_names=None):
        self.view = view
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
        builder = ProfilingSchemaBuilder(id=self.view.schema.id,
                                         name=self.view.schema.name).add_defaults()
        builder.schema.title = self.view.schema.title
        builder.schema.description = self.view.schema.description
        # Fix default prefix
        builder.schema.default_prefix = 'this'
        if 'this' not in self.view.namespaces():
            builder.add_prefix('this', self.view.schema.id)
        for prefix, ns in self.view.namespaces().items():
            # Copy URIs to new schema
            try:
                builder.add_prefix(prefix, ns)
            except ValueError as e:
                log.debug(e)
        return builder

    def _range_is_class(self, s_def):
        """ """
        return True if self.view.get_class(s_def.range) else False

    def _profile(self, name, builder, fix_doc=False):
        """Profile schema elements recursively."""
        elem = self.view.get_element(name, imports=False)
        if elem is None:
            return
        # Fix documentation
        if fix_doc and elem.description is not None:
            # Clean up description
            log.debug(f'Fixing doc for class "{elem.name}"')
            elem.description = ' '.join(split('\s+', elem.description))
        if isinstance(elem, ClassDefinition):
            if builder.has_class(elem.name):
                return
            log.info('{s:-^80}'.format(s=f' {elem.name} '))
            log.debug(f'Adding class "{name}"')
            builder.add_class(elem)
            # Find all classes that have a slot with range equal to this class
            for c_def in self.view.all_classes().values():
                for s_def in c_def.attributes.values():
                    if s_def.range == elem.name and c_def.name not in self.c_names:
                        log.info(f'Class "{elem.name}" is used as range for slot "{c_def.name}::{s_def.name}"')
            # TODO: Call _profile() for each SlotDefinition
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
                # self._profile(s_def.range, builder, fix_doc)
            elem['attributes'] = attr
            for s_def in attr.values():
                # Process each attribute separately to simplify logging
                self._profile(s_def.range, builder, fix_doc)
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

    def profile(self, fix_doc=False):
        """Create a new LinkML schema based on the provided class name(s) and
        their dependencies.
        """
        # TODO: Replace SchemaView with SchemaDefinition to prevent magic behaviour
        builder = self._create_builder()
        log.info(f'Profiling classes: {", ".join(sorted(self.c_names))}')
        for c_name in self.c_names:
            try:
                self._profile(c_name, builder, fix_doc)
            except ValueError as e:
                log.warning(e)
        log.info('{s:-^80}'.format(s=' Statistics '))
        builder.stats()
        return builder.schema

    def _snake_case(self, s):
        # return ''.join('_' + c if c.isupper() else c for c in s).strip()
        return convert_to_snake_case(s)

    def pydantic(self, attr):
        """Pre-process the schema for use by gen-pydantic."""
        for c_name, c_def in self.view.schema.classes.items():
            # Process classes in the schema, not a copy of c_def through SchemaView
            if 'attributes' not in c_def:
                continue
            # Convert attributes to snake_case
            attributes = {}
            for s_name, s_def in c_def['attributes'].items():
                if s_name in attr:
                    snake_case = attr[s_name]
                    log.info(f'Processing "{c_name}::{s_name}" as "{snake_case}"')
                else:
                    snake_case = self._snake_case(s_name)
                log.debug(f'Processing "{c_name}::{s_name}" as "{snake_case}"')
                # Replace reference
                attributes[snake_case] = s_def
            self.view.schema.classes[c_name]['attributes'] = attributes
        self.view.set_modified()
        return self.view.schema

    def data_product(self, class_name):
        """Process a single class as a data product."""
        builder = self._create_builder()
        # Retrieve class
        c_def = self.view.get_class(class_name)
        if c_def is None:
            raise ValueError(f'Class "{class_name}" not found in schema')
        # Flatten class hierarchy
        c_def = self.view.induced_class(c_def.name)
        for s_name, s_def in c_def['attributes'].items():
            if s_def.range is None:
                continue
            # Check if range is a class
            c_range = self.view.get_class(s_def.range)
            if c_range is None:
                log.debug(f'Range "{s_def.range}" is not a class, skipping')
                continue
            # Replace range with type of the identifier for the referred class
            s_range_def = self.view.get_identifier_slot(c_range.name, imports=False)
            if s_range_def is None:
                log.error(f'No identifying slot found for "{c_range.name}"')
                continue
            s_range = self.view.get_slot(s_range_def.name)
            if s_range is None:
                log.debug(f'No identifier found for "{c_def.name}::{s_def.name}"')
                continue
            log.debug(f'Set range "{s_range.name}" for "{c_def.name}::{s_def.name}"')
            # TODO: check if the identifying slot range is not another class
            s_def.range = s_range.range
        # Clean up class
        c_def.is_a = None
        # Generate output
        log.info(f'Processed class "{c_def.name}" as data product')
        builder.add_class(c_def)
        return builder.schema
