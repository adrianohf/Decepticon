FROM kalilinux/kali-rolling:latest

# Fix SSL certificate issues with Kali mirrors, then install packages
# Disable apt sandbox so it doesn't fail to drop privileges/chown to _apt user
RUN echo "APT::Sandbox::User \"root\";" > /etc/apt/apt.conf.d/10sandbox && \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    nmap \
    dnsutils \
    whois \
    curl \
    wget \
    netcat-openbsd \
    iputils-ping \
    python3 \
    python3-pip \
    tmux \
    libcap2-bin \
    && apt-get clean

# Install subfinder (often not in default kali repos or needs specific setup, but lets try to get it via apt if possible, otherwise we skip or use go)
# Actually, subfinder is in Kali repos: `apt install subfinder`
RUN apt-get update && apt-get install -y --no-install-recommends subfinder && apt-get clean

# Exploit & post-exploitation tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    hydra \
    sqlmap \
    nikto \
    smbclient \
    exploitdb \
    dirb \
    gobuster \
    && apt-get clean

# OPSEC: Give nmap raw packet capabilities so it can perform SYN scans (-sS) without being root
RUN setcap cap_net_raw,cap_net_admin,cap_net_bind_service+eip /usr/bin/nmap

# Configure tmux: 50K line scrollback buffer to prevent output truncation
RUN echo "set-option -g history-limit 50000" > /root/.tmux.conf

# Working directory for the agent's virtual filesystem
WORKDIR /workspace

# Keep the container alive so the backend can 'docker exec' into it
CMD ["tail", "-f", "/dev/null"]
