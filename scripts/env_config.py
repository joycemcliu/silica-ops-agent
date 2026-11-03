#!/usr/bin/env python3
import json
from pathlib import Path
import sys

import jsonschema
import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    pass


class ConfigError(ValueError):
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


def load_config(path):
    try:
        schema_path = Path(__file__).resolve().parent.parent / "envs.schema.json"
        schema = json.loads(schema_path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        config = yaml.load(Path(path).read_text(), Loader=UniqueKeyLoader)
        jsonschema.Draft202012Validator(schema).validate(config)
        return config
    except (OSError, ValueError, TypeError, yaml.YAMLError, jsonschema.SchemaError, jsonschema.ValidationError):
        raise ConfigError("Invalid environment configuration (values suppressed).") from None


def main():
    if len(sys.argv) != 2:
        print("Usage: validate-envs.py <envs.yaml>", file=sys.stderr)
        return 2
    try:
        load_config(sys.argv[1])
    except ConfigError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Environment configuration is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
