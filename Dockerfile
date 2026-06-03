FROM runpod/base:1.0.3-cuda1300-ubuntu2404
LABEL description="A Docker image for a Python 3.13.12 environment with Nginx, LAMP stack, phpMyAdmin, and Node.js, with mariadb, cuda 13.00 and pytorch 2.11.0."
SHELL ["/bin/bash", "-lc"]
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install Python Build Dependencies ONLY
# This layer rarely changes, keeping the cache intact for the next step.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget build-essential \
    libssl-dev zlib1g-dev libncurses5-dev libnss3-dev libreadline-dev libffi-dev libsqlite3-dev libbz2-dev \
 && rm -rf /var/lib/apt/lists/*

# 2. Install Python 3.13.12 System-wide from source
# The heaviest layer in the build, now safely cached near the top.
RUN cd /tmp \
 && wget https://www.python.org/ftp/python/3.13.12/Python-3.13.12.tar.xz \
 && tar -xf Python-3.13.12.tar.xz \
 && cd Python-3.13.12 \
 && ./configure --enable-optimizations \
 && make -j$(nproc) \
 && make altinstall \
 && ln -sf /usr/local/bin/python3.13 /usr/local/bin/python3 \
 && ln -sf /usr/local/bin/python3.13 /usr/local/bin/python \
 && ln -sf /usr/local/bin/pip3.13 /usr/local/bin/pip3 \
 && ln -sf /usr/local/bin/pip3.13 /usr/local/bin/pip \
 && cd / \
 && rm -rf /tmp/Python-3.13.12*

RUN pip install --no-cache-dir torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130

# 3. Install Nginx, LAMP Stack, phpMyAdmin, and Node.js
# If you add/remove web dependencies later, only this layer and below will rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx gnupg lsb-release \
    mariadb-server mariadb-client \
    apache2 php libapache2-mod-php php-mysql php-cli php-curl php-mbstring php-zip php-gd php-xml \
    debconf-utils \
 && echo "phpmyadmin phpmyadmin/reconfigure-webserver multiselect apache2" | debconf-set-selections \
 && echo "phpmyadmin phpmyadmin/dbconfig-install boolean false" | debconf-set-selections \
 && apt-get install -y --no-install-recommends phpmyadmin \
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g pm2 \
 && rm -rf /var/lib/apt/lists/*


# 4. Inject Custom MySQL Configuration to fix phpMyAdmin socket permissions
RUN echo "[mysqld]\nsocket=/var/run/mysqld/mysqld.sock\nsocket_chmod=0777\n" >> /etc/mysql/mariadb.conf.d/50-server.cnf

# 5. Inject the Wrapper Entrypoint
COPY start-services.sh /usr/local/bin/start-services.sh
RUN chmod +x /usr/local/bin/start-services.sh

ENTRYPOINT ["/usr/local/bin/start-services.sh"]