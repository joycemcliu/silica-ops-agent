"""Bridge MCP user-input requests to the authorized session's DM replies."""

import asyncio
import json
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker, SchemaError

from .config import APPROVAL_SECONDS


def review_schema(schema):
    """Reject secret inputs and references before validating a self-contained form."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("only object forms are supported")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError("the form schema is invalid") from error

    def check(value):
        if isinstance(value, dict):
            if any(k in value for k in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise ValueError("schema references are not supported")
            if value.get("writeOnly") or value.get("format") == "password":
                raise ValueError("secret inputs must be configured outside Slack")
            for name in value.get("properties", {}):
                if name.lower().replace("_", "").replace("-", "") in {
                    "password", "secret", "token", "apikey", "accesstoken", "clientsecret",
                }:
                    raise ValueError("secret inputs must be configured outside Slack")
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


async def elicit(session, params):
    mode = params.get("mode")
    schema, validator = None, None
    try:
        if mode in ("form", "openai/form", "openaiForm"):
            schema = params.get("requestedSchema")
            validator = review_schema(schema)
            details = json.dumps(schema, ensure_ascii=False, indent=2)
            if len(details) > 12000:
                raise ValueError("the form is too large for Slack")
            instructions = (
                "Reply with a JSON object matching this form ({} for an empty form). "
                "Do not enter passwords, tokens, or other secrets in Slack.\n" + details
            )
        elif mode == "url":
            url = params.get("url", "")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("the request must supply an HTTPS URL without embedded credentials")
            instructions = (
                "Open this URL in your browser if you trust the named server. "
                "Complete the requested interaction there, then reply accept to continue. "
                "Do not paste credentials into Slack.\n" + url
            )
        else:
            raise ValueError("this elicitation mode is not supported")
    except ValueError as error:
        await session.manager.post(session, f"MCP input declined: {error}. The diagnosis can continue.")
        return {"action": "decline"}

    prompt = (
        f"MCP input request from {params.get('serverName', '(unknown server)')}\n"
        f"{params.get('message', '')}\n{instructions}\n"
        "Reply decline to refuse or cancel to dismiss. Expires in 10 min."
    )
    try:
        async with asyncio.timeout(APPROVAL_SECONDS):
            while True:
                session.question = asyncio.get_running_loop().create_future()
                await session.manager.post(session, prompt)
                reply = (await session.question).strip()
                action = reply.lower()
                if action in ("decline", "cancel"):
                    return {"action": action}
                if mode == "url":
                    if action == "accept":
                        return {"action": "accept"}
                else:
                    if reply.startswith("```") and reply.endswith("```"):
                        reply = reply.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    try:
                        content = json.loads(reply)
                    except ValueError:
                        content = None
                    if isinstance(content, dict) and validator.is_valid(content):
                        return {"action": "accept", "content": content}
                prompt = (
                    "That reply does not match the request. Send accept for a browser request, "
                    "or a JSON object matching the displayed form. You can also decline or cancel."
                )
    except TimeoutError:
        await session.manager.post(session, "MCP input request expired; cancelled. The diagnosis can continue.")
        return {"action": "cancel"}
    finally:
        session.question = None
