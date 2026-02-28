# -*- coding: utf-8 -*-

from click import option, group, argument, File, echo, ClickException
from functools import wraps, partial
from sys import stdin, stdout

import logging
log = logging.getLogger(__name__)

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(message)s'
FIXED_DOMAIN = 'netbeheernederland.nl'


def catch_exception(func=None, *, handle):
    if not func:
        return partial(catch_exception, handle=handle)

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except handle as e:
            log.error(e)
            # raise ClickException(e)
    return wrapper


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
    from treelib import Tree, Node
    from linkml_runtime.utils.schemaview import SchemaView

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
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--leaves', is_flag=True, default=False,
        help='Generate the diagram only using leaf classes')
@option('--skip', is_flag=True, default=False,
        help='Skip optional attributes')
@option('--directed', is_flag=True, default=False,
        help='Add directionality to the diagram')
@argument('yamlfile', type=File('rt'), default=stdin)
def diagram(yamlfile, out, leaves, skip, directed):
    """Create a D2 diagram based on the provided class name"""
    from .schema_profiler import SchemaProfiler

    profiler = SchemaProfiler(yamlfile.read())
    ranges = list(profiler.ranges(leaves=leaves, skip=skip))
    if not directed:
        ranges = [p for i, p in enumerate(ranges)
                  if p not in ranges[:i] and (p[1], p[0]) not in ranges[:i]]
    classes = sorted(list({v for x in ranges for v in x[:2]}))
    #
    echo('.Diagram')
    echo('[d2,svg,theme=4]')
    echo('----')
    for c_name in classes:
        echo(f'{c_name}')
    echo()
    d = '->' if directed else '--'
    for from_class, to_class in ranges:
        echo(f'{from_class} {d} {to_class}')
    echo('----')


@cli.command()
@option('--class-name', '-c', required=False, multiple=True,
        help='Root of class hierarchy')
@argument('yamlfile', type=File('rt'), default=stdin)
def docs(yamlfile, class_name):
    """Generate a documentation table for the class names"""
    from linkml_runtime.utils.schemaview import SchemaView

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
    from .schema_profiler import SchemaProfiler
    from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump

    profiler = SchemaProfiler(yamlfile.read())
    echo(schema_as_yaml_dump(profiler.pydantic(dict(attr), fix_doc=fix_doc)),
         file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@argument('yamlfile', type=File('rt'), default=stdin)
def export(yamlfile, out, **kwargs):
    """Export an OWL/XML output file. Can be read by SparX EA"""
    from linkml.generators.owlgen import OwlSchemaGenerator
    from rdflib import Graph

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
    from .schema_profiler import SchemaProfiler

    profiler = SchemaProfiler(yamlfile.read())
    profiler.leaves()


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--to-schema', type=File('rt'), help='Merge provided classes into this schema')
@argument('from-schema', type=File('rt'), default=stdin)
def merge(from_schema, out, to_schema, **kwargs):
    """Merge the source schema into the LinkML schema"""
    from .schema_profiler import SchemaProfiler
    from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump

    profiler = SchemaProfiler(to_schema.read())
    echo(schema_as_yaml_dump(profiler.merge(from_schema.read())), file=out)


@cli.command()
@argument('yamlfile', type=File('rt'), default=stdin)
def lint(yamlfile, **kwargs):
    """Check the schema for common problems"""
    from .schema_profiler import SchemaProfiler

    profiler = SchemaProfiler(yamlfile.read())
    profiler.lint()


@cli.command()
@option('--source', '-s', required=True)
@option('--destination', '-d', required=True)
@argument('yamlfile', type=File('rt'), default=stdin)
def path(yamlfile, source, destination):
    """Find the shortest path between two classes"""
    from .schema_profiler import SchemaProfiler

    profiler = SchemaProfiler(yamlfile.read())
    profiler.shortest_path(source, destination)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--leaves', is_flag=True, default=False,
        help='Generate the dataset only using leaf classes')
@option('--skip', is_flag=True, default=False,
        help='Skip optional attributes')
@argument('yamlfile', type=File('rt'), default=stdin)
@catch_exception(handle=(ValueError))
def example(yamlfile, out, leaves, skip):
    """Generate an example from the provided class"""
    from .schema_profiler import SchemaProfiler

    profiler = SchemaProfiler(yamlfile.read())
    echo(profiler.example(leaves, skip), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print JSON to stdout')
@option('--indent', type=int, default=2,
        help='Indent level to pretty print at')
@argument('yamlfile', type=File('rt'), default=stdin)
def convert(yamlfile, out, indent):
    """Convert YAML formatted instance data to JSON"""
    from yaml import safe_load
    from json import dumps

    echo(dumps(safe_load(yamlfile.read()), indent=indent, default=str), file=out)


@cli.command()
@option('--out', '-o', type=File('wt'), default=stdout,
        help='Output file.  Omit to print schema to stdout')
@option('--class-name', '-c', default=None,
        help='Class name to use for dataset')
@option('--leaves', is_flag=True, default=False,
        help='Generate the dataset only using leaf classes')
@argument('yamlfile', type=File('rt'), default=stdin)
def dataset(yamlfile, out, class_name, leaves):
    """Generate an example from the provided class"""
    from .schema_profiler import SchemaProfiler

    profiler = SchemaProfiler(yamlfile.read())
    echo(profiler.dataset(class_name, leaves), file=out)


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
    from .schema_profiler import SchemaProfiler
    from linkml_runtime.utils.schema_as_dict import schema_as_yaml_dump

    profiler = SchemaProfiler(yamlfile.read(), class_name)
    echo(schema_as_yaml_dump(profiler.profile()), file=out)


def uuid5_with_domain(name: str) -> str:
    """Generate a stable uuid5
    """
    return str(uuid5(NAMESPACE_DNS, f'{name}_{FIXED_DOMAIN}'))


@cli.command()
@option("--var", nargs=2, multiple=True, metavar="KEY VALUE")
@argument('templatefile', default=stdin)
def template(templatefile, var):
    """Generate output based on a jinja2 template"""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from uuid import uuid4, uuid5, NAMESPACE_DNS

    env = Environment(loader=FileSystemLoader('.'),
                      undefined=StrictUndefined, autoescape=False)
    env.globals["uuid4"] = lambda: str(uuid4())
    env.globals["uuid5"] = uuid5_with_domain

    try:
        template = env.get_template(templatefile)
        echo(template.render(dict(var)))
    except Exception as e:
        raise ClickException(str(e))
