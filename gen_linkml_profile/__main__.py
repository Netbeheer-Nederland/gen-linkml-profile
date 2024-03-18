# -*- coding: utf-8 -*-

from click import option, group, argument, File
from xml.etree import ElementTree
from xml.etree.ElementTree import XMLPullParser
from collections import deque
from enum import Enum

from dataclasses import dataclass
from linkml.generators.linkmlgen import LinkmlGenerator
from linkml_runtime.linkml_model.meta import (ClassDefinition,
                                              ClassDefinitionName,
                                              SlotDefinition,
                                              SlotDefinitionName,
                                              EnumDefinition,
                                              PermissibleValue)

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

    def add_class(self, c_def):
        """Add a new class to the SchemaView"""
        self.schemaview.add_class(c_def)

    def add_enum(self, e_def):
        """Add a new enumeration to the SchemaView"""
        self.schemaview.add_enum(e_def)

    def all_classes(self):
        """Return all classes in the schemaview.
        TODO: add caching & cache invalidation.
        """
        return self.schemaview.all_classes()

    def all_enums(self):
        """Return all enums in the schemaview.
        TODO: add caching & cache invalidation.
        """
        return self.schemaview.all_enums()

    def clean(self, found):
        """Remove any unused references from the model.

        Terrible idea: delete all enums, types and classes not in {found}.
        This works because you cannot mix names for different elements.

        TODO: this really was a terrible idea, split out _found_ in classes,
        enums, types and slots
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
        merge_imports=False,
        **kwargs
    )
    gen.profile(class_names=class_name, data_product=data_product)
    print(gen.serialize())


def _get_value(elem, xpath=None, attr=None):
    """Helper function to get values from XML element or attribute """
    v = elem.find(xpath) if xpath is not None else elem
    if v is None:
        return ''
    return v.text.strip() if attr is None else v.get(attr, '').strip()


def _parse_extension(root, template):
    """ """
    p_defs, c_defs, s_defs,  e_defs = {}, {}, {}, {}
    # Process all packages in the extension
    for p in root.findall(f'.//element[@{XMI_NS}type="uml:Package"]'):
        p_name = p.get('name')
        if p_name is None:
            continue
        log.info(f'Found package "{p_name}"')
        # Each package is a new Generator
        gen = ProfilingLinkmlGenerator(
            template,
            materialize_attributes=False,
            materialize_patterns=False
        )
        gen.title = p_name
        gen.description = _get_value(p, 'properties', 'documentation')
        # gen.id is set as part of processing the packagedElements
        p_defs[_get_value(p, attr=f'{XMI_NS}idref')] = gen
    log.info(f'Processed [{len(p_defs)}] packages')
    # Process all classes in the extension
    for c in root.findall(f'.//element[@{XMI_NS}type="uml:Class"]'):
        c_id = _get_value(c, attr=f'{XMI_NS}idref')
        c_name = c.get('name')
        if c_name is None:
            continue
        # Enumerations are a special type of uml:Class in the extension
        if _get_value(c, 'properties', 'stereotype') == 'enumeration':
            e_def = EnumDefinition(name=c_name)
            # Populate permissible values
            for e in c.findall('.//attribute'):
                e_name = _get_value(e, attr='name')
                e_meaning = f'cim:{c_name}.{e_name}'
                try:
                    # Each PermissibleValue can have a _meaning_
                    e_value = PermissibleValue(text=e_name, meaning=e_meaning)
                except ValueError:
                    log.warning(f'URI "{e_meaning}" is not a valid URI')
                    e_value = PermissibleValue(text=e_name)
                e_def.permissible_values[e_name] = e_value
            e_defs[c_id] = e_def
            # Skip to next class, do not process enumerations any further
            continue
        c_def = ClassDefinition(name=c_name)
        c_def.class_uri = f'cim:{c_name}'    # TODO: add namespace to output!
        c_def.description = _get_value(c, 'properties', 'documentation')
        # c_def.is_a is replaced as part of processing the packagedElements
        is_a = _get_value(c, f'.//Generalization[@start="{c_id}"]', 'end')
        if len(is_a) > 0:
            c_def.is_a = is_a
        c_defs[c_id] = c_def
    log.info(f'Processed [{len(c_defs)}] classes')
    log.info(f'Processed [{len(e_defs)}] enumerations')
    # Process all attributes in the extension
    for s in root.findall('.//attribute'):
        s_name = s.get('name')
        if s_name is None:
            continue
        s_def = SlotDefinition(name=s_name)
        s_def.description = _get_value(s, 'documentation', 'value')
        # s_def.range is set as part of processing the packagedElements
        s_defs[_get_value(s, attr=f'{XMI_NS}idref')] = s_def
    log.info(f'Processed [{len(s_defs)}] attributes')
    #
    return (p_defs, c_defs, s_defs, e_defs)

@cli.command()
@option('--template', '-t', required=True, help='Template LinkML schema')
@argument('xmifile')
def testxmi(xmifile, template, **kwargs):
    """ """
    namespaces = {
        'xmi': "http://www.omg.org/spec/XMI/20131001",
        'uml': "http://www.omg.org/spec/UML/20161101",
        'umldi': "http://www.omg.org/spec/UML/20161101/UMLDI",
        'dc': "http://www.omg.org/spec/UML/20161101/UMLDC",
        'thecustomprofile': "http://www.sparxsystems.com/profiles/thecustomprofile/1.0",
        'EAUML': "http://www.sparxsystems.com/profiles/EAUML/1.0"
        }
    tree = ElementTree.parse(xmifile)
    p_defs, c_defs, s_defs, e_defs = _parse_extension(tree.getroot(), template)

    def _is_package(elem, elem_type):
        return elem.tag == 'packagedElement' and elem_type == 'uml:Package'

    def _is_class(elem, elem_type):
        return elem.tag == 'packagedElement' and elem_type == 'uml:Class'

    def _is_attribute(elem, elem_type):
        return elem.tag == 'ownedAttribute' and elem_type == 'uml:Property'

    def _is_enumeration(elem, elem_type):
        return elem.tag == 'packagedElement' and elem_type == 'uml:Enumeration'

    # Process the packagedElements
    parser = XMLPullParser(events=('start', 'end'))
    with open(xmifile, 'rb') as f:
        parser.feed(f.read())
    packages, p_names = {}, deque()
    p_def, c_def, s_def = None, None, None
    # Process events
    for event, elem in parser.read_events():
        elem_type = _get_value(elem, attr=f'{XMI_NS}type')
        if event == EVT_START:
            # --- Package -----------------------------------------------------

            if _is_package(elem, elem_type):
                # Set the Package ID to identify the package to add class to
                p_id = _get_value(elem, attr=f'{XMI_NS}id')
                p_names.append(_get_value(elem, attr='name'))
                if p_id not in p_defs:
                    continue
                packages['/'.join(p_names)] = p_def = p_defs[p_id]

            # --- Class -------------------------------------------------------

            if _is_class(elem, elem_type):
                if p_def is None:
                    continue
                c_id = _get_value(elem, attr=f'{XMI_NS}id')
                if c_id not in c_defs:
                    continue
                c_def = c_defs[c_id]
                log.info(f'Processing class "{"::".join(p_names)}::{c_def.name}"')
                # Set c_def.is_a
                if c_def.is_a is not None and c_def.is_a in c_defs:
                    c_def.is_a = c_defs[c_def.is_a].name
                p_def.add_class(c_def)

            # --- Enumeration -------------------------------------------------

            if _is_enumeration(elem,  elem_type):
                pass

            # --- Slot --------------------------------------------------------

            if _is_attribute(elem, elem_type):
                if c_def is None:
                    continue
                s_id = _get_value(elem, attr=f'{XMI_NS}id')
                if s_id not in s_defs:
                    continue
                s_def = s_defs[s_id]
                s_def.slot_uri = f'cim:{c_def.name}.{s_def.name}'
                # Set s_def.range
                r_id = _get_value(elem, 'type', attr=f'{XMI_NS}idref')
                if len(r_id) > 0 and r_id in c_defs:
                    # range is a class
                    s_def.range = c_defs[r_id].name
                    if c_defs[r_id].name not in p_def.all_classes():
                        p_def.add_class(c_defs[r_id])
                if len(r_id) > 0 and r_id in e_defs:
                    # range is an enumeration
                    s_def.range = e_defs[r_id].name
                    if e_defs[r_id].name not in p_def.all_enums():
                        p_def.add_enum(e_defs[r_id])
                # Cardinality
                lv = _get_value(elem, 'lowerValue', 'value')
                uv = _get_value(elem, 'upperValue', 'value')
                s_def.required = True if lv == 1 else None
                s_def.multivalued = True if uv == '*' else None
                # Add slot to class
                c_def.attributes[s_def.name] = s_def

        if event == EVT_END:
            if _is_package(elem, elem_type):
                p_names.pop()
                p_def = None
            if _is_class(elem, elem_type):
                c_def = None
            if _is_attribute(elem, elem_type):
                s_def = None

    # print(c_defs['EAID_EEB4990E_A0CF_4f4b_981C_2A2C774153BC'])
    print(packages['Model/TC57CIM/IEC61970/Base/Wires'].serialize())
