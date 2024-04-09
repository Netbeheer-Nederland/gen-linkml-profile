# -*- coding: utf-8 -*-

from click import option, group, argument, File, echo
from dataclasses import dataclass
from re import split
from sys import stdin, stdout

from treelib import Tree, Node
from linkml.utils.schema_builder import SchemaBuilder
from linkml.utils.helpers import convert_to_snake_case
from linkml_runtime.utils.schemaview import SchemaView, OrderedBy
from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump
from linkml_runtime.linkml_model.meta import (ClassDefinition,
                                              SlotDefinition,
                                              EnumDefinition,
                                              TypeDefinition)
import logging
log = logging.getLogger(__name__)

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(message)s'
TYPE_REPLACED_BY_PROFILER = 'replaced_by_profiler'


@dataclass
class ProfilingSchemaBuilder(SchemaBuilder):
    """ """
    def stats(self):
        c, t, e = (len(self.schema.classes), len(self.schema.types),
                   len(self.schema.enums))
        log.info(f'Profiled [{c}] classes, [{t}] types and [{e}] enums')

    def has_class(self, c_name):
        return c_name in self.schema.classes

    def has_slot(self, s_name):
        return s_name in self.schema.slots

    def has_type(self, t_name):
        return t_name in self.schema.types

    def has_enum(self, e_name):
        return e_name in self.schema.enums


def _create_builder(view):
    """Create a new Builder object based on the provided view."""
    builder = ProfilingSchemaBuilder(id=view.schema.id,
                                     name=view.schema.name).add_defaults()
    builder.schema.title = view.schema.title
    builder.schema.description = view.schema.description
    # Fix default prefix
    builder.schema.default_prefix = 'this'
    if 'this' not in view.namespaces():
        builder.add_prefix('this', view.schema.id)
    for prefix, ns in view.namespaces().items():
        # Copy URIs to new schema
        try:
            builder.add_prefix(prefix, ns)
        except ValueError as e:
            log.debug(e)
    return builder


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
@option('--schema', '-s', type=File('rt'), required=True, default=stdin,
        help='Schema to merge into yamlfile')
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--clobber', is_flag=True, help='Overwrite existing elements')
@argument('yamlfile', type=File('rt'), default=stdin)
def merge(yamlfile, schema, out, clobber):
    """Merge one or more schemas into the target schema"""
    view = SchemaView(yamlfile.read(), merge_imports=False)
    view.merge_schema(SchemaView(schema.read(), merge_imports=False).schema,
                      clobber)
    # Output
    echo(schema_as_yaml_dump(view.schema), file=out)


@cli.command()
@option('--class-name', '-c', required=False, multiple=True,
        help='Root of class hierarchy')
@argument('yamlfile', type=File('rt'), default=stdin)
def children(yamlfile, class_name):
    """Show all children for the class in a hierarchical view"""
    view = SchemaView(yamlfile.read(), merge_imports=False)

    def _nodes(c_name, tree, parent=None):
        if c_name in tree:
            return
        tree.create_node(c_name, c_name, parent=parent)
        for c in view.class_children(c_name, imports=False):
            _nodes(c, tree, c_name)

    all_classes = [c for c in view.all_classes(imports=False) if
                   len(view.class_parents(c, imports=False)) == 0]
    class_names = class_name if len(class_name) > 0 else all_classes
    for c_name in class_names:
        tree = Tree()
        _nodes(c_name, tree)
        echo('\n' + tree.show(stdout=False))


@cli.command()
@option('--attr', '-a', type=(str, str), multiple=True,
        help='Manual mapping values. Use --attr [source] [target]')
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@argument('yamlfile', type=File('rt'), default=stdin)
def pydantic(yamlfile, attr, out):
    """Pre-process the schema for use by gen-pydantic"""
    def _snake_case(s):
        # return ''.join('_' + c if c.isupper() else c for c in s).strip()
        return convert_to_snake_case(s)
    view = SchemaView(yamlfile.read(), merge_imports=False)
    attr = dict(attr)
    log.info(f'Processing [{len(view.schema.classes)}] classes')
    for c_name, c_def in view.schema.classes.items():
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
                snake_case = _snake_case(s_name)
            log.debug(f'Processing "{c_name}::{s_name}" as "{snake_case}"')
            # Replace reference
            attributes[snake_case] = s_def
        view.schema.classes[c_name]['attributes'] = attributes
    view.set_modified()
    echo(schema_as_yaml_dump(view.schema), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--class-name', '-c', required=True, help='Class to profile')
@argument('yamlfile', type=File('rt'), default=stdin)
def data_product(yamlfile, out, class_name):
    """Process a single class as a data product"""
    view = SchemaView(yamlfile.read(), merge_imports=False)
    builder = _create_builder(view)
    # Retrieve class
    c_def = view.get_class(class_name)
    if c_def is None:
        raise ValueError(f'Class "{class_name}" not found in schema')
    # Flatten class hierarchy
    c_def = view.induced_class(c_def.name)
    for s_name, s_def in c_def['attributes'].items():
        if s_def.range is None:
            continue
        # Check if range is a class
        c_range = view.get_class(s_def.range)
        if c_range is None:
            log.debug(f'Range "{s_def.range}" is not a class, skipping')
            continue
        # Replace range with type of the identifier for the referred class
        s_range_def = view.get_identifier_slot(c_range.name, imports=False)
        if s_range_def is None:
            log.error(f'No identifying slot found for "{c_range.name}"')
            continue
        s_range = view.get_slot(s_range_def.name)
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
    echo(schema_as_yaml_dump(builder.schema), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--class-name', '-c', required=True, multiple=True,
        help='Class(es) to profile')
@option('--skip-opt', is_flag=True,
        help='Do not process any ranges that are on an optional slot')
@option('--fix-doc', is_flag=True,
        help='Normalise documentation by removing newlines')
@argument('yamlfile', type=File('rt'), default=stdin)
def profile(yamlfile, out, class_name, skip_opt, fix_doc, **kwargs):
    """Create a new LinkML schema based on the provided class name(s) and their
    dependencies.
    """
    # TODO: Replace SchemaView with SchemaDefinition to prevent magic behaviour
    view = SchemaView(yamlfile.read(), merge_imports=False)
    c, t, e = len(view.all_classes()), len(view.all_types()), len(view.all_enums())
    log.info(f'Schema contains [{c}] classes, [{t}] types and [{e}] enums')
    builder = _create_builder(view)
    # Add a type to identify removed ranges
    if skip_opt:
        t_replaced = TypeDefinition(
                        name=TYPE_REPLACED_BY_PROFILER,
                        base='str',
                        uri='xsd:string',
                        description='Range was replaced by the profiler')
        builder.add_type(t_replaced)

    def _slot(s_name, s_def, skip_opt):
        """Process a SlotDefinition"""
        if skip_opt:
            r_name = s_def.range
            required = r_name not in keep and view.get_class(r_name)
            if not s_def.required and required:
                # Set range to a native type, replacing the class
                log.debug(f'Replacing optional range "{s_def.range}"')
                s_def.range = TYPE_REPLACED_BY_PROFILER

    def _profile(view, name, builder, skip_opt, keep, fix_doc=False):
        """ """
        elem = view.get_element(name, imports=False)
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
            log.debug(f'Adding class "{name}"')
            builder.add_class(elem)
            for c_name in view.class_ancestors(elem.name):
                if elem.name == c_name or builder.has_class(c_name):
                    continue
                # Process inheritance (is_a) for this class
                log.debug(f'Processing ancestor "{c_name}" for "{elem.name}"')
                _profile(view, c_name, builder, skip_opt, keep, fix_doc)
            for s_name in elem['slots']:
                if builder.has_slot(s_name):
                    continue
                s_def = view.get_slot(s_name)
                builder.add_slot(s_def)
                _slot(s_name, s_def, skip_opt)
                _profile(view, s_def.range, builder, skip_opt, keep, fix_doc)
            for s_name, s_def in elem['attributes'].items():
                _slot(s_name, s_def, skip_opt)
                _profile(view, s_def.range, builder, skip_opt, keep, fix_doc)
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
        # TODO: How to handle mixins?
        # TODO: How to handle specific instructions likee emit_prefixes?

    keep = set()
    for c_name in class_name:
        try:
            _profile(view, c_name, builder, skip_opt, keep, fix_doc)
        except ValueError as e:
            log.warning(e)
    builder.stats()
    # Write schema to stdout
    echo(schema_as_yaml_dump(builder.schema), file=out)
