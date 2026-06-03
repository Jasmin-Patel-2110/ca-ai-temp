#!/bin/bash

# 1. Ensure MariaDB runtime directories exist
mkdir -p /var/run/mysqld
chown mysql:mysql /var/run/mysqld
chmod 777 /var/run/mysqld
mkdir -p /var/lib/mysql
chown -R mysql:mysql /var/lib/mysql

# 2. Start background services
service mariadb start
service apache2 start

# Wait a moment to ensure daemon is fully up
sleep 3 

# 3. Configure MariaDB for phpMyAdmin
mysql -e "CREATE USER IF NOT EXISTS 'admin'@'localhost' IDENTIFIED BY 'admin2026';"
mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'admin'@'localhost' WITH GRANT OPTION;"
mysql -e "FLUSH PRIVILEGES;"

# 4. Hand control back to RunPod
exec /start.sh "$@"