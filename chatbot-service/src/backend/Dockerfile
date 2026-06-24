FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build
WORKDIR /src
COPY src/backend/Novit.Web.Api/Novit.Web.Api.csproj ./Novit.Web.Api/
RUN dotnet restore Novit.Web.Api/Novit.Web.Api.csproj
COPY src/backend/Novit.Web.Api/ ./Novit.Web.Api/
WORKDIR /src/Novit.Web.Api
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgssapi-krb5-2 && rm -rf /var/lib/apt/lists/*
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:5000
EXPOSE 5000
ENTRYPOINT ["dotnet", "Novit.Web.Api.dll"]
