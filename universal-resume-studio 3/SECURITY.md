# Security & privacy

This is a local single-user prototype, **not a production multi-tenant application**.

Do not expose its HTTP server to the public internet. Profile persistence stores plaintext locally if explicitly enabled. Use fictional data for examples and tests. Do not place actual candidate records, employer datasets or credentials in Git.

Before production release: implement authentication, tenant isolation and authorization on every data operation, encryption at rest and in transit, private object storage, retention/deletion controls, upload validation and malware scanning, rate limiting, threat-model review, and external service safeguards.

Report security bugs privately to the repository owner, not in a public issue containing exploit details or user data.
