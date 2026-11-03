import re
from urllib.parse import parse_qsl, urlsplit

from access_common import AccessError


def approved_get_path(request_target, specification, approved_paths):
    if not isinstance(request_target, str) or not 1 <= len(request_target) <= 4096:
        raise AccessError("API request target rejected.")
    if re.search(r"[\x00-\x20\x7f\\#%]", request_target) or not request_target.startswith("/") or request_target.startswith("//"):
        raise AccessError("API request target rejected.")
    parsed = urlsplit(request_target)
    if parsed.scheme or parsed.netloc or parsed.fragment or ":" in parsed.path:
        raise AccessError("API request target rejected.")
    if any(segment in {"", ".", ".."} for segment in parsed.path.split("/")[1:]) and parsed.path != "/":
        raise AccessError("API request target rejected.")
    if not re.fullmatch(r"/[A-Za-z0-9_./{}-]*", parsed.path):
        raise AccessError("API request target rejected.")
    if not isinstance(specification, dict) or not str(specification.get("openapi", "")).startswith("3."):
        raise AccessError("A local OpenAPI 3 specification is required.")
    paths = specification.get("paths")
    if not isinstance(paths, dict) or not isinstance(approved_paths, list) or not all(isinstance(path, str) for path in approved_paths):
        raise AccessError("Invalid API path policy.")
    matches = []
    for template, definition in paths.items():
        if not isinstance(template, str) or not isinstance(definition, dict) or not template.startswith("/"):
            continue
        escaped = re.escape(template)
        pattern = re.sub(r"\\\{[A-Za-z_][A-Za-z0-9_]*\\\}", "[A-Za-z0-9_-]+", escaped)
        if re.fullmatch(pattern, parsed.path):
            matches.append((template, definition))
    exact = [match for match in matches if match[0] == parsed.path]
    matches = exact or matches
    if len(matches) != 1:
        raise AccessError("API path is absent or ambiguous in OpenAPI.")
    template, definition = matches[0]
    operation = definition.get("get")
    if template not in approved_paths or not isinstance(operation, dict) or "$ref" in definition or "$ref" in operation:
        raise AccessError("API path is not approved for read-only GET access.")
    shared_parameters = definition.get("parameters", [])
    operation_parameters = operation.get("parameters", [])
    if not isinstance(shared_parameters, list) or not isinstance(operation_parameters, list):
        raise AccessError("Invalid OpenAPI parameters.")
    parameters = shared_parameters + operation_parameters
    if not all(isinstance(parameter, dict) and "$ref" not in parameter for parameter in parameters):
        raise AccessError("Resolve API parameter references before enabling this route.")
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=50)
    except ValueError:
        raise AccessError("Too many API query parameters.") from None
    names = [name for name, _value in query]
    allowed = {parameter.get("name") for parameter in parameters if parameter.get("in") == "query"}
    if len(names) != len(set(names)) or any(name not in allowed for name in names):
        raise AccessError("API query parameter is not approved by OpenAPI.")
    required = {parameter.get("name") for parameter in parameters if parameter.get("in") == "query" and parameter.get("required")}
    if not required.issubset(names):
        raise AccessError("A required API query parameter is missing.")
    if any(not re.fullmatch(r"[A-Za-z0-9_.~-]{0,256}", value) for _name, value in query):
        raise AccessError("API query value rejected.")
    return request_target
