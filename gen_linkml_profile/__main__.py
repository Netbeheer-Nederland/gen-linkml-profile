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
    from uuid import uuid5, NAMESPACE_DNS
    return str(uuid5(NAMESPACE_DNS, f'{name}_{FIXED_DOMAIN}'))


@cli.command()
@option("--var", multiple=True, metavar="KEY")
@option("--delimiter", default=",")
@argument('templatefile')
def template(templatefile, var, delimiter):
    """Generate output based on a jinja2 template"""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from uuid import uuid4
    from dateutil import parser
    from datetime import timezone

    env = Environment(loader=FileSystemLoader('.'),
                      undefined=StrictUndefined, autoescape=False)
    env.globals["uuid4"] = lambda: str(uuid4())
    env.globals["uuid5"] = uuid5_with_domain
    env.filters["xsd_datetime"] = lambda v: (
        (lambda dt: dt.replace(tzinfo=timezone.utc)
         .isoformat(timespec="milliseconds")
         if dt.tzinfo is None else dt.isoformat(timespec="milliseconds"))
        (parser.parse(v))
    )

    try:
        template = env.get_template(templatefile)

        if stdin.isatty():
            raise ValueError('Input must be provided on stdin')

        import csv
        reader = csv.DictReader(stdin, delimiter=delimiter, fieldnames=var)
        for row in reader:
            echo(template.render(**row))
    except Exception as e:
        raise ClickException(str(e))
