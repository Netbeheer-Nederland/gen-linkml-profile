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

By default, all dependencies are extracted. ```gen-linkml-profile``` can
optionally skip classes that are a range for a slot which itself is not
```required```. In this case, the range is replaced with a
```ReplacedByProfiler``` type. Further manual inspection will be needed to
resolve these types, usually by removing the slot.

## Usage

Install ```gen-linkml-profiler``` using a package manager like ```pipx```
directly from this GitHub repository.

```
Usage: gen-linkml-profile profile [OPTIONS] YAMLFILE

  Create a new LinkML schema based on the provided class name(s) and their
  dependencies.

Options:
  -c, --class-name TEXT  Class(es) to profile  [required]
  --skip-opt             Do not process any ranges that are on an optional
                         slot
  --fix-doc              Normalise documentation by removing newlines
  --help                 Show this message and exit.
```

## Development

Clone the repository and run ```poetry install``` in the ```gen-linkml-profiler```
directory.
