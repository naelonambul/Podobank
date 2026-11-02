# Serena project configuration design

## Intent

Keep the PodoBank Serena connection explicitly named and configured as the project-specific HTTP MCP endpoint. The selected change removes the generic disabled `serena` entry and retains the `serena_podobank` URL unchanged.

## Goals

- Leave `.codex/config.toml` with the `serena_podobank` table pointing to `http://127.0.0.1:9121/mcp`.
- Keep this pull request limited to the Codex project setting and its change packet.

## Non-goals

- Change how Serena is launched, reused, or stopped.
- Change the HTTP endpoint, application code, or verification registry.
- Guarantee a process count. Removing a Codex configuration override does not manage server processes.

## Approaches

1. Keep `[mcp_servers.serena] enabled = false`. This preserves a project-level guard against a future global server but keeps the extra entry in the project file.
2. Remove that entry and retain the named project endpoint. This matches the selected settings-only scope and keeps the project connection explicit. **Selected.**
3. Add process lifecycle or deduplication management. This could address process count directly, but it exceeds the selected configuration-only scope.

## Constraints and behavior

The project-level `.codex/config.toml` has higher precedence than user-level `~/.codex/config.toml` in Codex's documented configuration order ([configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic)). Removing the project-level disabled entry therefore means a future user-level server named `serena` may be enabled alongside `serena_podobank`. The currently inspected host has no user-level MCP server entry and had one Serena process bound to `127.0.0.1:9121` with the PodoBank project path; those observations describe this host and are not guarantees of the setting.

## Acceptance

- The final TOML parses successfully.
- The only MCP server table in `.codex/config.toml` is `serena_podobank`, with URL `http://127.0.0.1:9121/mcp`.
- No process-management or application changes are included.
