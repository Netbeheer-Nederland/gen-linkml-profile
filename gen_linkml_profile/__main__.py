# -*- coding: utf-8 -*-

from click import option, group, argument, File

from dataclasses import dataclass
from linkml.generators.linkmlgen import LinkmlGenerator

import logging
log = logging.getLogger(__name__)

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(message)s'


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
