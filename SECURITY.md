# Security Policy

## Reporting a Vulnerability

If you believe you've found a security vulnerability, please report it privately to
**compliance@convictional.com**. Do not open a public issue or pull request for security reports.

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce, or a proof of concept.
- The affected component and the version or commit you tested against.

We'll acknowledge your report within three business days and keep you updated as we investigate. Please give
us a reasonable opportunity to address the issue before any public disclosure.

## Scope

In scope: this application — the API, the web frontend, authentication and session handling, the background
job runner, the MCP server, and the integrations under `integrations/`.

Out of scope:

- Findings that require a configuration this application documents as unsafe. `ENABLE_FAKE_AUTH` signs users
  in with no credentials by design and is documented as development-only; a report that it permits
  unauthenticated access isn't a vulnerability.
- Missing hardening on a self-hosted deployment you control — an unset `SECRET_KEY`, a database reachable
  from the internet, absent TLS. See [self-hosting](docs/self-hosting.md) for what a deployment is expected
  to supply.
- Vulnerabilities in third-party dependencies with no demonstrated impact here. Report those upstream; tell
  us if this application's use of them makes the impact worse.
- Automated scanner output with no analysis attached.

Reports about the hosted Convictional service are also welcome at the address above — they reach the same
team.
