# -*- coding: utf-8 -*-

from click import option, group, argument, File
from xml.etree import ElementTree
from xml.etree.ElementTree import XMLPullParser
from collections import deque
from enum import Enum

from dataclasses import dataclass
from linkml.utils.schema_builder import SchemaBuilder
from linkml.utils.schemaloader import SchemaLoader
from linkml_runtime.utils.schemaview import SchemaView
from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump

from linkml_runtime.linkml_model.meta import (ClassDefinition,
                                              SlotDefinition,
                                              EnumDefinition,
                                              TypeDefinition)

from pprint import pprint

import logging
log = logging.getLogger(__name__)

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(message)s'


@dataclass
class ProfilingSchemaBuilder(SchemaBuilder):
    """ """
    def __post_init__(self):
        super().__post_init__()
        self.c_names, self.s_names, self.e_names, self.t_names = [], [], [], []

    def stats(self):
        c, t, e = len(self.c_names), len(self.t_names), len(self.e_names)
        log.info(f'Processed [{c}] classes, [{t}] types and [{e}] enums')

    def has_class(self, c_name):
        return c_name in self.c_names

    def has_slot(self, s_name):
        return s_name in self.s_names

    def has_type(self, t_name):
        return t_name in self.t_names

    def has_enum(self, e_name):
        return e_name in self.e_names

    def add_class(self, c_def):
        if c_def.name in self.c_names:
            return
        self.c_names.append(c_def.name)
        super().add_class(c_def)

    def add_slot(self, s_def):
        if s_def.name in self.s_names:
            return
        self.s_names.append(s_def.name)
        super().add_slot(s_def)

    def add_type(self, t_def):
        if t_def.name in self.t_names:
            return
        self.t_names.append(t_def.name)
        super().add_type(t_def)

    def add_enum(self, e_def):
        if e_def.name in self.e_names:
            return
        self.e_names.append(e_def.name)
        super().add_enum(e_def)


@group()
@option('--log', type=File(mode='a'), help='Filename for log file')
@option('--debug', is_flag=True, default=False, help='Enable debug mode')
def cli(log, debug):
    """ """
    # Setup logging
    if log:
        handler = logging.FileHandler(log.name)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    # Add handler to the root log
    logging.root.addHandler(handler)
    # Set log level
    level = logging.DEBUG if debug else logging.INFO
    logging.root.setLevel(level)


@cli.command()
@option('--class-name', '-c', required=True, multiple=True,
        help='Class to profile')
@option('--data-product', is_flag=True,
        help='Generate the logical model for a data product')
@argument('yamlfile')
def profile(yamlfile, class_name, data_product, **kwargs):
    """Create a new LinkML schema based on the provided class name(s) and their
    dependencies.

    :yamlfile: base schema
    :class_name: tuple of class names to keep in the schema
    :data_product: if True, create the logical model for a single class name
    """
    view = SchemaView(yamlfile, merge_imports=False)
    c, t, e = len(view.all_classes()), len(view.all_types()), len(view.all_enums())
    log.info(f'Schema contains [{c}] classes, [{t}] types and [{e}] enums')
    builder = ProfilingSchemaBuilder(id=view.schema.id,
                                     name=view.schema.name).add_defaults()
    for prefix, ns in view.namespaces().items():
        # Copy URIs to new schema
        try:
            builder.add_prefix(prefix, ns)
        except ValueError as e:
            log.warning(e)

    def _profile(view, name, builder):
        """ """
        elem = view.get_element(name)
        if elem is None:
            return
        if isinstance(elem, ClassDefinition):
            if builder.has_class(elem.name):
                return
            log.info(f'Adding class "{name}"')
            builder.add_class(elem)
            for s_name, s_def in elem['attributes'].items():
                log.debug(f'Slot "{c_name}::{s_name}" found')
                _profile(view, s_def.range, builder)
        if isinstance(elem, TypeDefinition):
            if builder.has_type(elem.name):
                return
            log.info(f'Adding type "{name}"')
            builder.add_type(elem)
        if isinstance(elem, EnumDefinition):
            if builder.has_enum(elem.name):
                return
            log.info(f'Adding enum "{name}"')
            builder.add_enum(elem)

    ancestors = set()
    for c_name in class_name:
        ancestors |= set(view.class_ancestors(c_name))
    for c_name in ancestors:
        _profile(view, c_name, builder)
    builder.stats()
    # Write schema to stdout
    print(schema_as_yaml_dump(builder.schema))
