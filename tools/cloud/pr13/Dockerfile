FROM mcr.microsoft.com/dotnet/sdk@sha256:4beef5b8919dcaa2dc924233bd069257e883cc7a061e09088a97d152d6a48510

# This image owns native cloud fixtures, including actual headless Godot.
# Desktop player/load sessions are a separate client-to-cloud execution layer.
ENV DEBIAN_FRONTEND=noninteractive DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv ca-certificates libfontconfig1 libx11-6 libxcursor1 \
    libxinerama1 libxrandr2 libxi6 libgl1 libvulkan1 libwayland-client0 \
    libwayland-cursor0 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/pr13-venv \
    && /opt/pr13-venv/bin/pip install --no-cache-dir psutil==7.0.0
COPY godot /usr/local/bin/godot
RUN chmod 0755 /usr/local/bin/godot && godot --headless --version && dotnet --version
ENV PATH="/opt/pr13-venv/bin:${PATH}" \
    DOTNET_CLI_HOME=/cache/dotnet-home NUGET_PACKAGES=/cache/nuget
USER 1000:1000
WORKDIR /work
