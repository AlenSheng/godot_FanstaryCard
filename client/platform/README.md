# Platform login and Windows packaging

Local login is available only in a debug build with
`platform/development/local_auth=true` and a server that advertises
`identity.local`. Windows release builds use the Steam login path; Android
Production uses Google login. Neither release path replaces a failed provider
login with local authentication.

Android Production uses the Google login path. The client expects a native
`GoogleSignIn` singleton exposing `sign_in(web_client_id)` and a
`sign_in_completed` signal that returns an ID token. The server validates the
token with Google, checks issuer/audience/expiry/email verification, and maps
the stable Google `sub` to the internal UserId. Configure the real Web Client
ID in the private Android export environment or project configuration; do not
commit OAuth secrets. The native plugin, Android OAuth client, package/SHA-256
fingerprint registration, and Play Console configuration are external release
acceptance tasks. Until they exist, the release button stays disabled with an
actionable message.

Steam login requires a compatible GodotSteam 4.x native extension exposing the
`Steam` singleton, a real AppID, and a Web API ticket identity. Configure
`platform/steam/app_id` and `platform/steam/web_api_identity` in `project.godot`.
The identity must equal the server's `Identity:Steam:Identity`. The publisher key
belongs only in the server secret store and must never ship in the client.

The adapter initializes Steam, checks the running AppID and Steam sign-in,
requests a `getAuthTicketForWebApi` ticket, waits for the
`get_ticket_for_web_api(handle, result, size, buffer)` callback, and submits only
the hexadecimal ticket to `/api/v1/auth/steam`. The server determines SteamID.
Tickets are cancelled after the HTTP sign-in attempt or timeout. Tokens remain
in memory. Missing configuration or native APIs returns an actionable login
message without inventing a ticket or reporting authentication success.

`Windows Desktop` in `export_presets.cfg` defines a release package with test
scenes, evidence, source documentation, and logs excluded. Set
`platform/server_url` to the intended HTTPS service before distribution. Install
the private encryption template matching the project's exact Godot version.
Use the protected export helper instead of a stock template. Every exported PCK
payload and its directory are encrypted; scripts are compiled to compressed
binary tokens before encryption. The validated executable and PCK are written
to a unique folder below `builds/windows/`; keep them together.

Local automated validation covers missing platform configuration, ticket
callback validation, session invalidation/relogin, and configuration mismatches.
No AppID or native Steam plugin has been supplied, so real Steam authentication,
native plugin packaging, a signed release executable, and a Steam library launch
remain external release acceptance tasks. A preset is not an already exported
or platform-approved build. Do not use a sample AppID as the game's identity.

Run `python tools/release_protection.py build-template` first to prepare the
private template and its dependencies. The release key is stored at the project
root in `release-encryption.key`, as requested by the owner; it is ignored by
Git and never copied into a release. A CI secret named
`GODOT_SCRIPT_ENCRYPTION_KEY` can replace this file. Never print the key or pass
it as a command-line argument. See `docs/RELEASE_PROTECTION.md` for recovery and
server packaging instructions.

Run `tools/engine-local/protected/venv/Scripts/python.exe client/platform/export_windows.py` from the repository root to check
the real release prerequisites without writing a package. Once they are met,
add `--export` to create the release. Missing requirements stop the export;
the helper does not install credentials, substitute an AppID, or switch to a
development build. `--candidate --export` creates an explicitly labelled
encryption/startup candidate while retaining the unmet Steam/service requirements
in the report. It does not enable development authentication in a release.
Every export verifies all encrypted payloads, starts the game with the private
template, and confirms that the stock editor cannot open the same PCK. Missing
keys, mismatched templates, plaintext scripts, corrupt payloads or startup errors
stop package promotion. Required third-party licenses remain readable beside
the game in `licenses/`.

`python client/tests/session_http_fixture.py` exercises
authentication against an isolated temporary local HTTP server without touching
game accounts or overwriting gameplay evidence.
