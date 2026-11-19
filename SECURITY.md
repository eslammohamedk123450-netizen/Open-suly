# Security Policy

Security is a core requirement for SULY because the platform may handle private user data, connected services, files, and agent actions.

## Reporting a vulnerability

Please do not publish exploitable vulnerability details in a public issue.

Until a dedicated private security contact is published, contact the repository owner through a private GitHub communication channel. Include:
- A concise description and potential impact.
- Affected component, endpoint, or commit if known.
- Reproduction steps or a proof of concept that does not access other users' data.
- Any suggested mitigation.

Do not include real user data, passwords, tokens, or live secrets in a report.

## Security expectations

- Keep secrets out of source control and client bundles.
- Use least-privilege credentials and server-side authorization.
- Apply and test Supabase Row Level Security policies for exposed data.
- Treat model output and external tool content as untrusted.
- Isolate code execution and constrain browser/tool permissions.
- Require explicit approval for sensitive or destructive actions.
- Keep dependencies and deployment environments maintained.
- Log security-relevant events without logging secrets or unnecessary personal data.

## Scope

This policy covers this repository and the SULY application components maintained here. Acknowledgment and remediation timelines will be documented when a formal security response process is established.
