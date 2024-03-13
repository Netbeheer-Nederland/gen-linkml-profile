# -*- coding: utf-8 -*-

from click import option, group, argument, File
from xml.etree import ElementTree
from xml.etree.ElementTree import XMLPullParser
from collections import deque

from dataclasses import dataclass
from linkml.generators.linkmlgen import LinkmlGenerator

from pprint import pprint

import logging
log = logging.getLogger(__name__)

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(message)s'

XMI_NS = '{http://www.omg.org/spec/XMI/20131001}'
EVT_START = 'start'
EVT_END = 'end'


@dataclass
class ProfilingLinkmlGenerator(LinkmlGenerator):
    """This generator provides a direct conversion of a LinkML schema
    into yaml. Additional profiling and merge operations are provided.
    """

    def __post_init__(self):
        # TODO: consider moving up a level
        super().__post_init__()
        self.format = 'yaml'

    def _data_product(self, class_name):
        """Create a schema for a data product.

        :class_name: Class name to use as base for the data product
        """
        log.info(f'Processing "{class_name}" as a data product')
        # flatten class hierarchy to a single class {class_name}
        c_def = self.schemaview.get_class(class_name)
        attrs = self.schemaview.class_induced_slots(class_name)
        for attr in attrs:
            c_def.attributes[attr.name] = attr
        # Copy identifier attribute for class referred in range for slot
        attrs = c_def.attributes.copy()
        for s_name, s_def in attrs.items():
            if s_def.range is None:
                continue
            try:
                identifier = self.schemaview.get_identifier_slot(s_def.range)
                if identifier is None:
                    log.info(f'Range "{s_def.range}" does not have an identifier, skipping')
                    continue
                # TODO: do we need to copy more attributes?
                s_def.range = identifier.range
            except ValueError:
                continue

    def clean(self, found):
        """Remove any unused references from the model.

        Terrible idea: delete all enums, types and classes not in {found}.
        This works because you cannot mix names for different elements.
        """
        # Delete all unused classes
        all_classes = self.schemaview.all_classes()
        for c_name, c_def in all_classes.items():
            if c_name in found:
                continue
            # TODO: check if delete_reference=bad?
            self.schemaview.delete_class(c_name)
        # Delete unused enums
        all_enums = self.schemaview.all_enums()
        for e_name, e_def in all_enums.items():
            if e_name in found:
                continue
            self.schemaview.delete_enum(e_name)
        # Delete unused types
        all_types = self.schemaview.all_types()
        for t_name, t_def in all_types.items():
            if t_name in found:
                continue
            self.schemaview.delete_type(t_name)
        # TODO: delete unused slots?

    def profile(self, class_names, data_product=False):
        """Profile the schema based on provided class name.

        :class_names: Tuple of classnames in schema to profile
        :data_product: If True, do additional processing to create the
                       logical model for a data product
        """
        def _profile(c_name, found=None):
            """ """
            if found is None:
                found = set()
            c_def = self.schemaview.get_class(c_name)
            if c_def is None:
                log.info(f'Class "{c_name}" not found')
                return []
            for s_name, s_def in c_def['attributes'].items():
                if s_def.range not in found:
                    log.debug(f'Slot "{c_name}::{s_name}" found')
                    found.add(s_def.range)
                    _profile(s_def.range, found)
            return found

        ancestors = set()    # List of classes to keep in the schema
        for class_name in class_names:
            ancestors |= set(self.schemaview.class_ancestors(class_name))
        found = set()
        for class_name in ancestors:
            log.info(f'Processing "{class_name}"')
            found.add(class_name)
            found |= _profile(class_name)

        # Data product processing
        if data_product:
            if len(class_names) != 1:
                raise ValueError('Please provide a single class name')
            # Modifies self.schemaview!
            self._data_product(class_names[0])
            # Only keep the single class name
            found.clear()
            found.add(class_names[0])

        log.info(f'Retaining the following {len(found)} elements: {found}')
        self.clean(found)


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
    gen = ProfilingLinkmlGenerator(
        yamlfile,
        materialize_attributes=False,
        materialize_patterns=False,
        **kwargs
    )
    gen.profile(class_names=class_name, data_product=data_product)
    print(gen.serialize())


@cli.command()
@argument('xmifile')
def testxmi(xmifile, **kwargs):
    """ """
    namespaces = {
        'xmi': "http://www.omg.org/spec/XMI/20131001",
        'uml': "http://www.omg.org/spec/UML/20161101",
        'umldi': "http://www.omg.org/spec/UML/20161101/UMLDI",
        'dc': "http://www.omg.org/spec/UML/20161101/UMLDC",
        'thecustomprofile': "http://www.sparxsystems.com/profiles/thecustomprofile/1.0",
        'EAUML': "http://www.sparxsystems.com/profiles/EAUML/1.0"
        }
    # tree = ElementTree.parse(xmifile)
    # root = tree.getroot()
    # for c in (tree.findall('.//packagedElement[@xmi:type="uml:Package"]', namespaces)):
    #     pprint(c.attrib['name'])

    def _is_package(elem, elem_type):
        return elem.tag == 'packagedElement' and elem_type == 'uml:Package'

    def _is_class(elem, elem_type):
        return elem.tag == 'packagedElement' and elem_type == 'uml:Class'

    def _is_generalization(elem, elem_type):
        return elem.tag == 'generalization' and elem_type == 'uml:Generalization'

    def _is_attribute(elem, elem_type):
        return elem.tag == 'ownedAttribute' and elem_type == 'uml:Property'

    def _is_enumeration(elem, elem_type):
        return elem.tag == 'packagedElement' and elem_type == 'uml:Enumeration'

    def _find_element(package, idref):
        return package.find(f'.//element[@xmi:idref="{idref}"]', namespaces)

    def _find_attribute(package, idref):
        return package.find(f'.//attribute[@xmi:idref="{idref}"]', namespaces)

    def _get_parent(package, idref):
        pass

    parser = XMLPullParser(events=('start', 'end'))
    with open(xmifile, 'rb') as f:
        parser.feed(f.read())
    packages = deque()
    c_def, s_def = None, None
    # Process events
    for event, elem in parser.read_events():
        elem_type = elem.get(f'{XMI_NS}type', None)
        package_name = '::'.join([x.get('name') for x in packages])
        if event == EVT_START:
            elem_name = elem.get('name', None)
            if _is_package(elem, elem_type):
                packages.append(elem)
            if _is_class(elem, elem_type):
                if elem_name is None:
                    continue
                log.info(f'Processing class "{package_name}::{elem_name}"')
                c_def = True
                # TODO: create a new SchemaView for package if none exists
                # TODO: get documentation, generate URI and figure out 'is_a'
            if _is_attribute(elem, elem_type):
                # TODO: convert attribute to slot definition
                # TODO: add slot definition to class
                pass
            if _is_generalization(elem, elem_type):
                # Only allow generalization if a class definition is available
                if c_def is None:
                    continue
                # TODO: Find parent and create 'is_a' attribute
                idref = elem.get('general')
        if event == EVT_END:
            if _is_package(elem, elem_type):
                packages.pop()
            if _is_class(elem, elem_type):
                c_def = None
