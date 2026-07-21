# Sinhala Proofreader — operations Makefile (Ubuntu / Docker Engine).
#
# The docker-compose.yml lives in the webapp/ subdirectory, so every target
# points compose at it with -f. Run these from the repo root
# (/home/lotus_dev/vidath/proofreader).
#
# Uses '>' as the recipe prefix (instead of a TAB) so the file is robust to
# editors that convert tabs — GNU make 3.82+ (Ubuntu ships 4.3).
.RECIPEPREFIX = >
.DEFAULT_GOAL := help

COMPOSE := docker compose -f webapp/docker-compose.yml
DATA_DIR := webapp/data
DB := /app/data/corrections.db
BACKUP_ROOT := /mnt/10thdev/backups

.PHONY: help up down logs restart status shell backup db-check ps

help:
> @echo "Targets:"
> @echo "  make up       - build + start containers (detached)"
> @echo "  make down     - stop and remove containers"
> @echo "  make logs     - follow the web app logs"
> @echo "  make restart  - restart containers"
> @echo "  make status   - list containers"
> @echo "  make shell    - open a shell in the web container"
> @echo "  make backup   - copy webapp/data to $(BACKUP_ROOT)/proofreader-<ts>/"
> @echo "  make db-check - print SQLite journal_mode + integrity_check"

up:
> $(COMPOSE) up -d --build

down:
> $(COMPOSE) down

logs:
> $(COMPOSE) logs -f web

restart:
> $(COMPOSE) restart

status ps:
> $(COMPOSE) ps

shell:
> $(COMPOSE) exec web bash

# Copy the live data dir (SQLite DB + WAL/SHM + usage log + config + key) to a
# timestamped backup folder. Uses cp -a to preserve perms/timestamps.
backup:
> @ts=$$(date +%Y%m%d-%H%M%S); \
>   dest="$(BACKUP_ROOT)/proofreader-$$ts"; \
>   mkdir -p "$$dest"; \
>   cp -a $(DATA_DIR)/. "$$dest/"; \
>   echo "Backup complete -> $$dest"; \
>   ls -lh "$$dest"

# Runs sqlite3 INSIDE the container (image now ships the sqlite3 CLI).
db-check:
> $(COMPOSE) exec web sqlite3 $(DB) "PRAGMA journal_mode; PRAGMA integrity_check;"
