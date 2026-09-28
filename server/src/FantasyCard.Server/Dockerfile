FROM mcr.microsoft.com/dotnet/sdk:10.0.400 AS build
WORKDIR /src
COPY server/Directory.Build.props server/Directory.Packages.props server/global.json ./
COPY server/src/FantasyCard.Contracts/FantasyCard.Contracts.csproj src/FantasyCard.Contracts/
COPY server/src/FantasyCard.Domain/FantasyCard.Domain.csproj src/FantasyCard.Domain/
COPY server/src/FantasyCard.Server/FantasyCard.Server.csproj src/FantasyCard.Server/
COPY protocol/ /protocol/
RUN dotnet restore src/FantasyCard.Server/FantasyCard.Server.csproj
COPY server/ .
RUN dotnet publish src/FantasyCard.Server/FantasyCard.Server.csproj -c Release -o /input --no-restore \
    -p:DebugType=None -p:DebugSymbols=false -p:UseAppHost=false
RUN dotnet tool install Obfuscar.GlobalTool --version 2.2.50 --tool-path /obfuscar
RUN mkdir -p /framework /private \
    && cp /usr/share/dotnet/shared/Microsoft.NETCore.App/10.*/*.dll /framework/ \
    && cp /usr/share/dotnet/shared/Microsoft.AspNetCore.App/10.*/*.dll /framework/ \
    && /obfuscar/obfuscar.console /src/protection/obfuscar.xml \
    && test -s /private/mapping.xml \
    && for assembly in FantasyCard.Contracts FantasyCard.Domain FantasyCard.Server; do \
         test -s "/output/${assembly}.dll"; \
         ! cmp -s "/input/${assembly}.dll" "/output/${assembly}.dll"; \
       done \
    && cp /output/FantasyCard.Contracts.dll /output/FantasyCard.Domain.dll /output/FantasyCard.Server.dll /input/ \
    && rm -f /input/*.pdb /input/*.xml /input/appsettings.Development.json \
    && ! find /input -type f \( -name '*.pdb' -o -name '*.cs' -o -name '*.key' -o -name '*.dpapi' \) -print -quit | grep -q .

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /input .
# The publish output preserves restrictive source modes.  The runtime is
# intentionally non-root, so configuration must remain readable after COPY.
RUN chmod a+r /app/appsettings.json
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "FantasyCard.Server.dll"]
