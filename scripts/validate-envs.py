#!/usr/bin/env python3
import json
from pathlib import Path
import sys

import jsonschema
import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError("mapping keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def main():
    if len(sys.argv) != 2:
        print("Usage: validate-envs.py <envs.yaml>", file=sys.stderr)
        return 2
    try:
        schema_path = Path(__file__).resolve().parent.parent / "envs.schema.json"
        schema = json.loads(schema_path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        config = yaml.load(Path(sys.argv[1]).read_text(), Loader=UniqueKeyLoader)
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(config))
        if errors:
            print("Invalid environment configuration (values suppressed).", file=sys.stderr)
            return 1
    except (OSError, ValueError, TypeError, yaml.YAMLError, jsonschema.SchemaError):
        print("Cannot validate environment configuration (values suppressed).", file=sys.stderr)
        return 1
    print("Environment configuration is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
