#!/bin/sh
set -eu

# Rebind tests to renamed internal APIs, then use the exact final-image DLLs.
mkdir -p /unprotected /test-protected
cp /input/* /unprotected/
for assembly in FantasyCard.Contracts FantasyCard.Domain FantasyCard.Server; do
    cp "/src/src/$assembly/bin/Release/net10.0/$assembly.dll" /unprotected/
done
dotnet build /src/FantasyCard.Server.slnx -c Release --artifacts-path /src/artifacts/acceptance
/obfuscar/obfuscar.console /evidence/test-obfuscar.xml
for suite in FantasyCard.Domain.Tests FantasyCard.Server.Tests; do
    destination="/src/artifacts/acceptance/bin/$suite/release"
    cp "/test-protected/$suite.dll" "$destination/"
    for assembly in FantasyCard.Contracts FantasyCard.Domain FantasyCard.Server; do
        if [ -f "$destination/$assembly.dll" ]; then
            cp "/evidence/image-app/$assembly.dll" "$destination/"
            cmp "/evidence/image-app/$assembly.dll" "$destination/$assembly.dll"
            sha256sum "$destination/$assembly.dll" >> /evidence/test-dependency-hashes.txt
        fi
    done
done
dotnet vstest \
    /src/artifacts/acceptance/bin/FantasyCard.Domain.Tests/release/FantasyCard.Domain.Tests.dll \
    /src/artifacts/acceptance/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll \
    --Logger:trx --ResultsDirectory:/evidence/results
