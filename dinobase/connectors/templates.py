"""Pure YAML builders for local custom connectors.

Extracted from the `dinobase connector create` CLI so the setup GUI can
construct the same files without shelling out.
"""

from __future__ import annotations

import shlex


_REST_TEMPLATE = """\
name: {name}
description: "{description}"
mode: {mode}

credentials:
  - name: api_key
    flag: "--api-key"
    env: {env_prefix}_API_KEY
    prompt: "{display_name} API key"
    secret: true

client:
  base_url: "{base_url}"
  auth:
    type: {auth_type}
    token: "{{api_key}}"
{paginator_block}
resource_defaults:
  primary_key: id
  write_disposition: replace
  endpoint:
    data_selector: "{data_selector}"

resources:
  - name: {resource_name}
    endpoint:
      path: {endpoint_path}
"""


def build_rest_connector_yaml(
    name: str,
    url: str | None = None,
    auth_type: str = "bearer",
    endpoint: str | None = None,
    data_selector: str = "$",
    mode: str = "auto",
) -> str:
    """Render a REST-API connector YAML.

    Matches the template previously inlined in cli.py so existing fixtures
    and snapshots keep diffing cleanly.
    """
    display_name = name.replace("_", " ").title()
    env_prefix = name.upper()
    resource_name = (endpoint or name).strip("/").split("/")[-1] or name

    paginator_block = ""
    if url and "posthog" in url.lower():
        paginator_block = '  paginator:\n    type: json_link\n    next_url_path: "next"\n'

    return _REST_TEMPLATE.format(
        name=name,
        description=f"Custom connector for {display_name}",
        mode=mode,
        base_url=url or "https://api.example.com/",
        auth_type=auth_type,
        env_prefix=env_prefix,
        display_name=display_name,
        data_selector=data_selector,
        resource_name=resource_name,
        endpoint_path=endpoint or "endpoint/path",
        paginator_block=paginator_block,
    )


def _yaml_double_quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_mcp_connector_yaml(
    name: str,
    transport: str,
    command: str | None = None,
    url: str | None = None,
    mode: str = "live",
    env: dict[str, str] | None = None,
) -> str:
    """Render an MCP connector YAML for stdio / sse / streamable_http transports.

    Raises ValueError if the required inputs for the chosen transport are missing.
    """
    if transport not in ("stdio", "sse", "streamable_http"):
        raise ValueError(f"Unknown MCP transport: {transport!r}")

    if transport == "stdio" and not command:
        raise ValueError("stdio transport requires a command")
    if transport in ("sse", "streamable_http") and not url:
        raise ValueError(f"{transport} transport requires a url")

    if env:
        for key in env:
            if not key or not isinstance(key, str):
                raise ValueError(f"env keys must be non-empty strings, got {key!r}")

    mcp_mode = mode if mode != "auto" else "live"
    display_name = name.replace("_", " ").title()

    if transport == "stdio":
        parts = shlex.split(command or "")
        if not parts:
            raise ValueError("stdio transport requires a non-empty command")
        cmd = parts[0]
        args = parts[1:]
        content = (
            f'name: {name}\n'
            f'description: "MCP connector for {display_name}"\n'
            f'mode: {mcp_mode}\n'
            f'\n'
            f'transport:\n'
            f'  type: stdio\n'
            f'  command: {cmd}\n'
        )
        if args:
            args_str = "\n".join(f'    - {_yaml_double_quoted(a)}' for a in args)
            content += f'  args:\n{args_str}\n'
        if env:
            env_lines = "\n".join(
                f'    {k}: {_yaml_double_quoted(str(v) if v is not None else "")}'
                for k, v in env.items()
            )
            content += f'  env:\n{env_lines}\n'
        return content

    return (
        f'name: {name}\n'
        f'description: "MCP connector for {display_name}"\n'
        f'mode: {mcp_mode}\n'
        f'\n'
        f'transport:\n'
        f'  type: {transport}\n'
        f'  url: {_yaml_double_quoted(url or "")}\n'
    )
