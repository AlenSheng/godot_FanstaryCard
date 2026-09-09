FROM mcr.microsoft.com/dotnet/sdk:10.0.400 AS build
WORKDIR /src
COPY Directory.Build.props Directory.Packages.props global.json ./
COPY src/FantasyCard.Contracts/FantasyCard.Contracts.csproj src/FantasyCard.Contracts/
COPY src/FantasyCard.Domain/FantasyCard.Domain.csproj src/FantasyCard.Domain/
COPY src/FantasyCard.Server/FantasyCard.Server.csproj src/FantasyCard.Server/
RUN dotnet restore src/FantasyCard.Server/FantasyCard.Server.csproj
COPY . .
RUN dotnet publish src/FantasyCard.Server/FantasyCard.Server.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /app .
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "FantasyCard.Server.dll"]
