# Server security hardening

This document describes the controls required by the cloud deployment. It does
not replace host firewall, encrypted disks, backups, or secret-store policy.

## Deployment requirements

The cloud `.env` must contain strong, unique values:

- `FANTASYCARD_DB_PASSWORD`
- `FANTASYCARD_ADMIN_KEY` (at least 32 characters; generate it randomly)

Compose expansion and application startup both fail when the administrator key
is missing or too short. Production explicitly disables local authentication.

The player API is served only through `https://relicbound.cn` and
`https://www.relicbound.cn`. Requests sent to the origin IP receive 404.
Port 20000 exposes the separate HTTPS management console. Restrict inbound TCP
20000 to administrator IPs in the cloud security group; the endpoint also
requires the administrator API key.

The administrator API still requires `X-Admin-Key` over the TLS tunnel.

## Assembly protection

Every cloud image build publishes in Release mode and runs Obfuscar 2.2.50 over:

- `FantasyCard.Contracts.dll`
- `FantasyCard.Domain.dll`
- `FantasyCard.Server.dll`

Private implementation names and strings are hidden, Unicode identifiers and
the SuppressIldasm flag are enabled, and PDB/XML/source/key files are excluded
from the runtime image. The Docker build fails unless a non-empty private
mapping is generated and all three protected DLLs differ from their published
inputs.

Endpoint methods, constructors, public API names, JSON properties, fields and
events remain stable because ASP.NET Minimal API, serializers and dependency
injection use reflection. Changing those exclusions requires running the full
protected-server integration suite before deployment.

Managed assemblies must be readable by the .NET runtime. Encrypting each live
DLL with AES while shipping the decryption key and loader in the same container
does not provide a meaningful trust boundary. Use encrypted host disks,
encrypted backups and a private container registry for encryption at rest and
in transit; use the repository's protected-export validation for reverse-
engineering resistance.

## Release verification

Before merging or deploying:

```bash
dotnet test server/FantasyCard.Server.slnx -c Release
docker compose -f server/compose.cloud.yaml --env-file server/.env config
docker compose -f server/compose.cloud.yaml --env-file server/.env build --no-cache server
```

Then verify:

- the root path returns 404;
- the domain certificate is publicly trusted;
- the origin IP returns 404 and never proxies the player API;
- port 20000 is reachable only from the administrator IP ranges configured in the cloud security group;
- local authentication is rejected in Production;
- the runtime image contains no PDB, XML documentation, source, key or mapping
  files.
