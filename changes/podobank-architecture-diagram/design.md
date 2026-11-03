# PodoBank current system architecture diagram

## Intent

Create a clear, shareable view of the current PodoBank preview and its data and observability paths. It is for the project owner and developers who need to understand how the public Workers reach OCI and how financial data and events move through the Compose services.

## Goals

- Show the browser, the two public Cloudflare Workers, their existing Tunnel VPC Service paths, OCI loopback bindings, and the frontend/API containers.
- Distinguish MariaDB as the financial system of record, MongoDB as the API's best-effort event sink, and JSONL → Alloy → Loki/Prometheus → Grafana as observability.
- Make request, database/event, and observability paths easy to inspect interactively in a single self-contained HTML file.
- Keep the diagram scoped to the PodoBank development preview; omit unrelated shared-host services.

## Non-goals

- Propose or depict an AWS deployment, production-grade banking topology, or unimplemented availability/security controls.
- Change Cloudflare, OCI, Compose, application behavior, or service configuration.
- Treat MongoDB event writes as part of the MariaDB transaction or as loss-proof delivery.

## Approaches

1. **ASCII diagram:** portable and easy to diff, but the two request paths, data paths, and infrastructure boundaries become crowded in a single view.
2. **Static Mermaid diagram:** easy to maintain beside documentation, but offers limited interaction for isolating paths and exploring component notes.
3. **Self-contained interactive HTML (selected by the agent):** inline SVG/CSS/JavaScript can provide path filters, responsive layout, and component notes without runtime dependencies. This matches the user's invitation to use interactive HTML. AWS architecture diagrams inform the use of clear boundaries, labeled arrows, and restrained service groupings; AWS product icons are not used because this system runs on Cloudflare and OCI.

## Design and constraints

- Keep all diagram content and behavior in `docs/architecture/podobank-current-architecture.html`; do not add packages or fetch remote assets.
- Provide toggles for browser/API requests, financial storage and event writes, and observability. All paths remain visible in the default state.
- Use distinct line styles and labels to show the actual direction and meaning of each flow. State that the frontend makes credentialed browser requests directly to the API Worker; there is no `/api` prefix or path rewrite.
- Show the Cloudflare Workers and existing VPC Service/Tunnel connection as public edge and private-origin boundaries. The frontend and API ports are loopback-bound at `127.0.0.1:8081` and `127.0.0.1:8000`. MariaDB publishes its host port on loopback (`127.0.0.1:${DB_PORT:-3306}:3306`), not a public interface. MongoDB, Alloy, Loki, and Prometheus have no host-published ports; Grafana is loopback-only.
- Show MariaDB commits before the API's one-shot best-effort MongoDB write. Note that MongoDB has no outbox, relay, retry, or replay path and does not affect a committed financial response.
- Show API/CLI JSONL events flowing through Alloy to Loki, Alloy metrics flowing into Prometheus during scrape, and query data flowing from Loki and Prometheus into Grafana. Place Prometheus and Grafana at the right end of the expanded Compose area. State that Grafana displays query data and does not write logs or metrics.
- Omit NPM, Jenkins, and other unrelated shared-host services. Expand the OCI/Compose boundary into the space previously reserved for that context.
- Include a short note that this is the current development preview with synthetic data, plus links to the official AWS icon guidance and the recent event-driven payment architecture reference used for visual research.

## Open choices for the implementation

- Use native inline SVG and semantic HTML controls; no icon pack or JavaScript framework is needed.
- Keep every node readable on mobile by allowing horizontal scrolling for the system map and keeping controls and legend usable at narrow widths.
- Include keyboard focus states and accessible labels for path controls and service nodes; pointer selection and keyboard focus/activation update the component details panel.
- Keep flow labels outside component cards and separate labels that describe different edges so the SVG remains legible.
