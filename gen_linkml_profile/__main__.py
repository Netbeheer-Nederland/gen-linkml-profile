# -*- coding: utf-8 -*-

from click import option, group, argument, File, echo
from sys import stdin, stdout

from .schema_profiler import SchemaProfiler

from treelib import Tree, Node
from linkml.generators.owlgen import OwlSchemaGenerator
from linkml_runtime.utils.schemaview import SchemaView
from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump

from rdflib import Graph

import logging
log = logging.getLogger(__name__)

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(message)s'


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
    c, t, e = (len(view.all_classes()), len(view.all_types()),
               len(view.all_enums()))
    log.info(f'Profiling [{c}] classes, [{t}] types and [{e}] enums')

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
    profiler = SchemaProfiler(SchemaView(yamlfile.read(), merge_imports=False))
    echo(schema_as_yaml_dump(profiler.pydantic(dict(attr))), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--class-name', '-c', required=True, help='Class to profile')
@argument('yamlfile', type=File('rt'), default=stdin)
def data_product(yamlfile, out, class_name):
    """Process a single class as a data product"""
    profiler = SchemaProfiler(SchemaView(yamlfile.read(), merge_imports=False))
    echo(schema_as_yaml_dump(profiler.data_product(class_name)), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@argument('yamlfile', type=File('rt'), default=stdin)
def export(yamlfile, out, **kwargs):
    """ """
    gen = OwlSchemaGenerator(yamlfile.read(), **kwargs)
    ttl = gen.serialize(**kwargs)
    # Convert TTL to RDF/XML
    g = Graph()
    g.parse(data=ttl)
    # Output
    echo(g.serialize(format='pretty-xml'), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--class-name', '-c', required=True, multiple=True,
        help='Class(es) to profile')
@option('--fix-doc', is_flag=True,
        help='Normalise documentation by removing newlines')
@argument('yamlfile', type=File('rt'), default=stdin)
def profile(yamlfile, out, class_name, fix_doc):
    """Create a new LinkML schema based on the provided class name(s) and their
    dependencies.
    """
    profiler = SchemaProfiler(SchemaView(yamlfile.read(), merge_imports=False),
                              class_name)
    echo(schema_as_yaml_dump(profiler.profile(fix_doc=fix_doc)), file=out)
