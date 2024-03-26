# -*- coding: utf-8 -*-

from click import option, group, argument, File
from dataclasses import dataclass
from re import split

from linkml.utils.schema_builder import SchemaBuilder
from linkml_runtime.utils.schemaview import SchemaView
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
    def __post_init__(self):
        super().__post_init__()
        self.c_names, self.s_names, self.e_names, self.t_names = {}, {}, {}, {}

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
        self.c_names[c_def.name] = c_def
        super().add_class(c_def)

    def add_slot(self, s_def):
        if s_def.name in self.s_names:
            return
        self.s_names[s_def.name] = s_def
        super().add_slot(s_def)

    def add_type(self, t_def):
        if t_def.name in self.t_names:
            return
        self.t_names[t_def.name] = t_def
        super().add_type(t_def)

    def add_enum(self, e_def):
        if e_def.name in self.e_names:
            return
        self.e_names[e_def.name] = e_def
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
@option('--schema', '-s', required=True, multiple=True,
        help='Schema to merge into yamlfile')
@option('--clobber', is_flag=True, help='Overwrite existing elements')
@argument('yamlfile')
def merge(yamlfile, schema, clobber):
    """Merge one or more schemas into the target schema. Existing elements
    can be overwritten or retained.
    """
    view = SchemaView(yamlfile, merge_imports=False)
    for s in schema:
        view.merge_schema(SchemaView(s, merge_imports=False).schema, clobber)
    print(schema_as_yaml_dump(view.schema))


@cli.command()
@option('--class-name', '-c', required=True, multiple=True,
        help='Class(es) to profile')
@option('--data-product', is_flag=True,
        help='Generate the logical model for a data product')
@option('--skip-opt', is_flag=True,
        help='Do not process any ranges that are on an optional slot')
@option('--fix-doc', is_flag=True,
        help='Normalise documentation by removing newlines')
@argument('yamlfile')
def profile(yamlfile, class_name, data_product, skip_opt, fix_doc, **kwargs):
    """Create a new LinkML schema based on the provided class name(s) and their
    dependencies.
    """
    view = SchemaView(yamlfile, merge_imports=False)
    c, t, e = len(view.all_classes()), len(view.all_types()), len(view.all_enums())
    log.info(f'Schema contains [{c}] classes, [{t}] types and [{e}] enums')
    builder = ProfilingSchemaBuilder(id=view.schema.id,
                                     name=view.schema.name).add_defaults()
    # Fix default prefix
    builder.schema.default_prefix = 'this'
    if 'this' not in view.namespaces():
        builder.add_prefix('this', view.schema.id)
    for prefix, ns in view.namespaces().items():
        # Copy URIs to new schema
        try:
            builder.add_prefix(prefix, ns)
        except ValueError as e:
            log.warning(e)
    # Add a type to identify removed ranges
    if skip_opt:
        t_replaced = TypeDefinition(
                        name=TYPE_REPLACED_BY_PROFILER,
                        base='str',
                        uri='xsd:string',
                        description='Range was replaced by the profiler')
        builder.add_type(t_replaced)

    def _profile(view, name, builder, skip_opt, keep, fix_doc=False):
        """ """
        elem = view.get_element(name, imports=False)
        if elem is None:
            return
        # Fix documentation
        if fix_doc and elem.description is not None:
            # Clean up description
            elem.description = ' '.join(split('\s+', elem.description))
        if isinstance(elem, ClassDefinition):
            if builder.has_class(elem.name):
                return
            log.info(f'Adding class "{name}"')
            builder.add_class(elem)
            for c_name in view.class_ancestors(elem.name):
                if elem.name == c_name or builder.has_class(c_name):
                    continue
                # Process inheritance (is_a) for this class
                log.debug(f'Processing ancestor "{c_name}" for "{elem.name}"')
                _profile(view, c_name, builder, skip_opt, keep, fix_doc)
            for s_name, s_def in elem['attributes'].items():
                if fix_doc and s_def.description is not None:
                    s_def.description = ' '.join(split('\s+', s_def.description))
                if skip_opt:
                    r_name = s_def.range
                    required = r_name not in keep and view.get_class(r_name)
                    if not s_def.required and required:
                        # Set range to a native type, replacing the class
                        log.info(f'Replacing range "{s_def.range}"')
                        s_def.range = TYPE_REPLACED_BY_PROFILER
                        continue
                # Process ranges
                log.debug(f'Slot "{s_name}" found')
                _profile(view, s_def.range, builder, skip_opt, keep, fix_doc)
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
        try:
            ancestors |= set(view.class_ancestors(c_name))
        except ValueError as e:
            log.warning(e)
    for c_name in ancestors:
        _profile(view, c_name, builder, skip_opt, ancestors, fix_doc)
    builder.stats()
    # Write schema to stdout
    print(schema_as_yaml_dump(builder.schema))
