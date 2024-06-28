# -*- coding: utf-8 -*-

from click import option, group, argument, File, echo
from sys import stdin, stdout

from .schema_profiler import SchemaProfiler

from treelib import Tree, Node
from linkml.generators.owlgen import OwlSchemaGenerator
from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump
from linkml_runtime.utils.schemaview import SchemaView

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
@option('--class-name', '-c', required=False, multiple=True,
        help='Root of class hierarchy')
@argument('yamlfile', type=File('rt'), default=stdin)
def docs(yamlfile, class_name):
    """Generate a documentation table for the class names"""
    view = SchemaView(yamlfile.read(), merge_imports=False)
    c, t, e = (len(view.all_classes()), len(view.all_types()),
               len(view.all_enums()))
    log.info(f'Profiling [{c}] classes, [{t}] types and [{e}] enums')

    from py_markdown_table.markdown_table import markdown_table
    from re import split
    rows = []
    for c_name in class_name:
        log.info(f'Process class "{c_name}"')
        c_def = view.induced_class(c_name)
        if c_def is None:
            raise ValueError(f'Class "{class_name}" not found in schema')
        first = True
        c_description = c_def.description if c_def.description is not None else ''
        for s_name, s_def in sorted(c_def.attributes.items(), key=lambda x: x[0]):
            attr = {}
            req = '1' if s_def.required else '0'
            mult = '*' if s_def.multivalued else '1'
            s_description = s_def.description if s_def.description is not None else ''
            #
            attr = {'Class Name': c_name if first else '',
                    'Class Description': c_description if first else '',
                    'Name': s_name,
                    'Range': s_def.range,
                    'Card': f'{req}..{mult}',
                    'Description': s_description}
            rows.append(attr)
            first = False
    c_name_len = len(max([x['Class Name'] for x in rows], key=len))
    s_name_len = len(max([x['Name'] for x in rows], key=len))
    r_name_len = len(max([x['Range'] for x in rows], key=len))
    echo(markdown_table(rows).set_params(
         padding_width=0,
         padding_weight='right',
         quote=False,
         multiline_strategy='rows_and_header',
         multiline={'Class Name': c_name_len if c_name_len > 10 else 10,
                    'Class Description': 50,
                    'Name': s_name_len if s_name_len > 4 else 4,
                    'Range': r_name_len if r_name_len > 5 else 5,
                    'Card': 4,
                    'Description': 50}).get_markdown())
    echo()


@cli.command()
@option('--attr', '-a', type=(str, str), multiple=True,
        help='Manual mapping values. Use --attr [source] [target]')
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--fix-doc', is_flag=True,
        help='Normalise documentation by removing newlines')
@argument('yamlfile', type=File('rt'), default=stdin)
def pydantic(yamlfile, attr, out, fix_doc):
    """Pre-process the schema for use by gen-pydantic"""
    profiler = SchemaProfiler(yamlfile.read())
    echo(schema_as_yaml_dump(profiler.pydantic(dict(attr), fix_doc=fix_doc)),
         file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@argument('yamlfile', type=File('rt'), default=stdin)
def export(yamlfile, out, **kwargs):
    """Export an OWL/XML output file. Can be read by SparX EA"""
    gen = OwlSchemaGenerator(yamlfile.read(), **kwargs)
    ttl = gen.serialize(**kwargs)
    # Convert TTL to RDF/XML
    g = Graph()
    g.parse(data=ttl)
    # Output
    echo(g.serialize(format='pretty-xml'), file=out)


@cli.command()
@argument('yamlfile', type=File('rt'), default=stdin)
def leaves(yamlfile):
    """Log all leaf classes (classes without parents) in the LinkML schema.
    Useful for determining which classes to include in diagrams"""
    profiler = SchemaProfiler(yamlfile.read())
    profiler.leaves()


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--source', type=File('rt'), help='Merge provided schema into this schema')
@argument('yamlfile', type=File('rt'), default=stdin)
def merge(yamlfile, out, source, **kwargs):
    """Merge the source schema into the LinkML schema"""
    profiler = SchemaProfiler(yamlfile.read())
    echo(schema_as_yaml_dump(profiler.merge(source.read())), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--class-name', '-c', required=True, multiple=True,
        help='Class(es) to profile')
@argument('yamlfile', type=File('rt'), default=stdin)
def profile(yamlfile, out, class_name):
    """Create a new LinkML schema based on the provided class name(s) and their
    dependencies
    """
    profiler = SchemaProfiler(yamlfile.read(), class_name)
    echo(schema_as_yaml_dump(profiler.profile()), file=out)
