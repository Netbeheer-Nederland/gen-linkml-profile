# gen-linkml-profile

## Introduction

```gen-linkml-profile``` is a small tool to create a new
[LinkML](https://linkml.io/) schema from a source schema. The source schema is
queried for the requested classes, where ```gen-linkml-profile``` tries to
figure out all dependencies. It tries to be smart about this, where the
subclass hierarchy is extracted for both queried and dependant classes.
Enumerations and types are retrieved as well.  Namespaces and prefixes are
copied likewise, but no detection on usage is performed. A default namespace
for the ID of the source schema is added with the prefix ```this```.

By default, all class hierarchy dependencies are extracted.
```gen-linkml-profile``` will skip any ranges that are not explicitly provided
on the command line when profiling, but will log that such a skipped range (and
if its containing attribute is required) was encountered. This allows for
specific profiling, while still providing a valid target LinkML schema.

## Usage

Install ```gen-linkml-profiler``` using a package manager like ```pipx```
directly from this GitHub repository.

```
Usage: gen-linkml-profile [OPTIONS] COMMAND [ARGS]...

Options:
  --log FILENAME  Filename for log file
  --debug         Enable debug mode
  --help          Show this message and exit.

Commands:
  children  Show all children for the class in a hierarchical view
  docs      Generate a documentation table for the class names
  export    Export an OWL/XML output file.
  leaves    Log all leaf classes (classes without parents) in the LinkML...
  merge     Merge the source schema into the LinkML schema
  profile   Create a new LinkML schema based on the provided class...
  pydantic  Pre-process the schema for use by gen-pydantic
```

Most commands that accept a file will also accept input from stdin, allowing
for piping of output:

```
$ gen-linkml-profile profile operation.yaml -c Analog -c Discrete|gen-linkml-profile pydantic --fix-doc
```

## Development

Clone the repository and run ```poetry install``` in the ```gen-linkml-profiler```
directory.
