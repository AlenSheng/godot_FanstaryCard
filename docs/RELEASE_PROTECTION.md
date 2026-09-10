# Release protection

## Artwork provenance

On 2026-09-10 the project owner confirmed that all 418 imported artwork files
were generated with ImageGen and have no copyright disputes. This declaration
is recorded in `client/assets/imported/manifest.json` and is preserved by the
importer. It covers the files present on that date, not later third-party
additions. It does not grant the public a license to redistribute the artwork.
The Source Han fonts retain OFL 1.1 and the generated sound library retains CC0.

## Private inputs

The owner requested that the current AES-256 key be kept at the project root:

`release-encryption.key`

The key is generated once with the operating system's cryptographic RNG, then
reused. It is ignored by Git, never logged and never passed on a command line.
Before distributing or sharing a copy of the source tree, move it to the chosen
secret store. Git ignore rules do not protect a manually zipped project folder.
Set `GODOT_SCRIPT_ENCRYPTION_KEY` in the build process to use an external key.
The build tool passes the same value through `SCRIPT_AES256_ENCRYPTION_KEY` only
to Godot's compiler process. Do not reuse a Steam publisher key or server secret.

`tools/engine-local/protected/` contains ignored build inputs and outputs,
including the Godot source, generated C++ key, object files, private template,
Obfuscar mapping and unprotected server intermediates. Do not distribute it.
Back up the key and matching template privately. Replacing the key requires a
new template and new packages; never silently generate a new key during export.

## Windows client

From the repository root:

```powershell
python tools/release_protection.py build-template
tools/engine-local/protected/venv/Scripts/python.exe client/platform/export_windows.py
tools/engine-local/protected/venv/Scripts/python.exe client/platform/export_windows.py --export
```

The helper builds the official matching Godot stable tag, checks that its commit
matches the installed editor, and records the template checksum, key fingerprint
and build flags. The build is a native x86-64 release without debug symbols; it
uses the project's OpenGL compatibility renderer. Visual Studio C++ build tools,
a Windows SDK, Python, Git and network access for pinned dependencies are needed.
The current baseline is Godot 4.7.2, SCons 4.9.1 and cryptography 46.0.5.

The PCK directory and every included file are encrypted using Godot's AES-256
PCK format. GDScript becomes compressed binary tokens before encryption.
Images, imported font data, audio, configuration, shaders and scenes inside the
PCK receive the same encryption. Raw art source files, tests, screenshots,
development documents, Python/C# source and symbol files are excluded.

Validation decrypts and checks the directory and every payload in memory, rejects
plaintext entries and scripts, and checks sizes/checksums. The private executable
must start without script/resource errors with no key in its environment. The
stock editor must reject the package. Only validated files are promoted to a
new `builds/windows/client-*` folder. Existing builds are not overwritten.
Font and Godot license notices are copied into a readable `licenses/` folder.

Until Steam AppID, ticket identity, GodotSteam release extension and HTTPS service
configuration are supplied, the production gate remains closed. Encryption can
still be validated without inventing those values:

```powershell
tools/engine-local/protected/venv/Scripts/python.exe client/platform/export_windows.py --candidate --export
```

This produces a labelled candidate under `builds/windows-protected-candidate/`.
Release authentication rules still apply. It is not a working Steam release.
Future native extensions must be tested in the actual package and retain their
own license notices; native DLLs loaded by Windows cannot be encrypted as PCK
payloads. Code signing is a separate publisher configuration.

## Server

```powershell
python tools/export_protected_server.py
python tools/validate_protected_server.py tools/engine-local/protected/server-<id>/report.json --postgres-bin <postgresql-bin-directory>
```

The export tool prints the exact private report path. It builds in isolated
directories with the repository's .NET SDK and uses Obfuscar.GlobalTool 2.2.50 on
FantasyCard.Contracts, FantasyCard.Domain and FantasyCard.Server. It hides
implementation strings and renames private/internal implementation details.
Public API, property/enum names and required reflective entry points are
preserved. PDBs, source files, development settings and rename maps are excluded
from the deployment package. Third-party dependencies are not rewritten.

The existing Domain/Server tests are processed in the same obfuscation pass,
preserving test definitions while repairing references to renamed internal
types. These test assemblies are never distributed. Validation checks that the
test processes use the exact packaged project DLL hashes and points the real
HTTP/WebSocket tests at the packaged server DLL.

Validation creates a new loopback-only PostgreSQL cluster for each run, runs all
existing tests, rejects failures and skipped tests, and stops the cluster.
It does not connect to the development or production database. Supply PostgreSQL
18 binaries (including their adjacent libraries/share files); the default local
path is `tools/engine-local/protected/postgres/pgsql/bin`. Test logs and data remain
in the ignored private build directory for diagnosis.

Deploy only a server folder with successful `protection-verification.json` and
no `CANDIDATE-NOT-YET-VALIDATED.txt`. Run `dotnet FantasyCard.Server.dll` with the
deployment's connection string and other secrets supplied externally. The Docker
build applies the same `server/protection/obfuscar.xml` rules before copying only
protected deployment files into the final image. Framework reference copies,
original DLLs and mappings stay in the builder stage. Ordinary `dotnet publish`
does not obfuscate by itself; use the protected script or the Dockerfile.

### Docker acceptance

From the repository root, build both targets from the same source checkout:

```powershell
docker build -t fantasycard-protected:acceptance -f server/src/FantasyCard.Server/Dockerfile server
docker build --target build -t fantasycard-protected-private:acceptance -f server/src/FantasyCard.Server/Dockerfile server
python tools/validate_docker_server.py --image fantasycard-protected:acceptance --builder-image fantasycard-protected-private:acceptance
```

The private builder contains sources and rename maps. Keep it local; distribute
only the protected runtime image. The validator checks matching DLL hashes,
creates an isolated PostgreSQL 18 database in memory, and compiles/runs both
existing test suites in Linux. It repairs test references with Obfuscar, then
replaces their project dependencies with the exact final-image DLLs. Existing
process-based HTTP/WebSocket and gameplay recovery tests use those DLLs too.

Additional checks run against the actual runtime container as its non-root user:
HTTP sign-in/bootstrap, shop purchase retries, binary Protobuf WebSocket ping,
forced container termination/restart and persisted session/assets, database
outage/readiness recovery, and disabled local authentication in Production.
The outage fixture uses short database timeouts; this does not measure default
production outage-detection latency. Database ports are not published, and
temporary HTTP ports bind to loopback only. Existing containers/data are retained.

The validator rejects source/debug/key/development/test files in the application
directory and builder-only directories in the final container filesystem. It
also scans that filesystem for the local root key without printing it. Nested
`artifacts` directories are excluded from both Docker context and server project
items so old validation output cannot become deployment content.

Only a run with `ok: true` in its private `verification.json` passes. Reports,
TRX results and logs live under `tools/engine-local/protected/docker-acceptance-*`.
Temporary containers, networks, database memory and smoke-session tokens are
removed after validation; the runtime and private builder images remain local.

## Limits

Protection raises extraction and reverse-engineering costs. It does not make a
client or a server impossible to inspect. The client necessarily contains a
usable decryption key, and rendered resources can be captured from memory.
Server protection is managed-code obfuscation and string hiding, not encryption
of all .NET IL; runtime assembly loading still needs usable code. Development
sources remain editable. Keep authoritative game rules and credentials on the
server, maintain access controls, and distribute only the intended build folder.

## Verification on 2026-09-10

- Windows candidate: 943 of 943 PCK entries encrypted, including 20 compiled
  GDScript files; no plaintext GDScript. Private-template startup passes and the
  stock engine explicitly refuses the encrypted directory.
- Protected server: 359 existing tests pass, with no failures or skipped tests,
  against an isolated PostgreSQL cluster. This includes real HTTP/WebSocket and
  process restart/recovery tests. The test cluster is stopped afterward.
- Docker Linux/amd64: 359 tests pass (202 Domain + 157 Server), with no failures
  or skipped tests, using exact final-image DLLs and PostgreSQL 18.6. The actual
  runtime container also passes 19 HTTP/WebSocket/purchase/restart assertions.
  It runs as UID 1654. Database outage gives readiness 503 while liveness remains
  200, and readiness recovers to 200. Production local authentication returns 404
  even if its configuration switch is enabled. Package/key leakage checks pass.
  Nested legacy validation output was found during acceptance and is now excluded
  from Docker context and project items. Acceptance resources were cleaned up.
- Encryption validator: 8 tests cover wrong/zero keys, truncation, corruption,
  unencrypted entries, source/secret leakage and supported PCK versions.
- Existing artwork importer: all 7 tests pass.
- Production Steam prerequisites and publisher code signing remain outstanding.

Accepted Docker image: `fantasycard-protected:acceptance-20260910-fixed`, digest
`sha256:e90392b2f1789cb2c13b1cd208675b26df01461d72e68ef2048590cce4ef2a48`.
Its private acceptance report and TRX/logs are in
`tools/engine-local/protected/docker-acceptance-_jm40u61/verification.json`.

Use the per-build `protection-verification.json` as the evidence for a specific
binary (or the Docker validator's `verification.json` for a specific image);
these results do not automatically approve later source changes.
