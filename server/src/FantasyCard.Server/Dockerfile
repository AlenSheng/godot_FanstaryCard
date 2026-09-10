FROM mcr.microsoft.com/dotnet/sdk:10.0.400 AS build
WORKDIR /src
COPY Directory.Build.props Directory.Packages.props global.json ./
COPY src/FantasyCard.Contracts/FantasyCard.Contracts.csproj src/FantasyCard.Contracts/
COPY src/FantasyCard.Domain/FantasyCard.Domain.csproj src/FantasyCard.Domain/
COPY src/FantasyCard.Server/FantasyCard.Server.csproj src/FantasyCard.Server/
RUN dotnet restore src/FantasyCard.Server/FantasyCard.Server.csproj
COPY . .
RUN dotnet publish src/FantasyCard.Server/FantasyCard.Server.csproj -c Release -o /input --no-restore \
    -p:DebugType=None -p:DebugSymbols=false -p:UseAppHost=false
RUN dotnet tool install Obfuscar.GlobalTool --version 2.2.50 --tool-path /obfuscar
RUN mkdir -p /framework /private \
    && cp /usr/share/dotnet/shared/Microsoft.NETCore.App/10.*/*.dll /framework/ \
    && cp /usr/share/dotnet/shared/Microsoft.AspNetCore.App/10.*/*.dll /framework/ \
    && /obfuscar/obfuscar.console /src/protection/obfuscar.xml \
    && cp /output/FantasyCard.Contracts.dll /output/FantasyCard.Domain.dll /output/FantasyCard.Server.dll /input/ \
    && rm -f /input/*.pdb /input/*.xml /input/appsettings.Development.json

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /input .
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "FantasyCard.Server.dll"]
