.DEFAULT_GOAL:=help
SHELL:=/bin/bash

PROJECT_NAME ?= $(notdir $(CURDIR))
UV_HOME ?= $(HOME)/uv
UV_ENV_DIR ?= $(UV_HOME)/$(PROJECT_NAME)

SERVICE_NAME ?= beancountbot
SERVICE_FILE := $(SERVICE_NAME).service
SYSTEMD_USER_DIR ?= $(HOME)/.config/systemd/user
INSTALLED_SERVICE := $(SYSTEMD_USER_DIR)/$(SERVICE_FILE)
PYTHON ?= /usr/bin/env python3
.PHONY: help install run docker env

help:  ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

start: ## Start the systemd service
	@systemctl --user start $(SERVICE_NAME).service

stop: ## Stop the systemd service
	@systemctl --user stop $(SERVICE_NAME).service

restart: ## Restart the systemd service
	@systemctl --user restart $(SERVICE_NAME).service

status: ## Show current service status
	@systemctl --user status $(SERVICE_NAME).service --no-pager

enable: ## Enable the service at login without starting it
	@systemctl --user enable $(SERVICE_NAME).service

disable: ## Disable the service so it no longer starts at login
	@systemctl --user disable $(SERVICE_NAME).service

reload: ## Reload the systemd manager configuration
	@systemctl --user daemon-reload

logs: ## Show recent journal entries for the service
	@journalctl --user-unit $(SERVICE_NAME).service --since "-5min" --no-pager

tail: ## Follow the journal for the service
	@journalctl --user-unit $(SERVICE_NAME).service -f

env: ## Create a fresh uv environment under ~/uv/$(PROJECT_NAME) and activate it
	@set -euo pipefail; \
	ENV_DIR="$(UV_ENV_DIR)"; \
	if [ -d "$$ENV_DIR" ]; then \
		echo "Environment already exists at $$ENV_DIR, skipping."; \
		exit 0; \
	fi; \
	mkdir -p "$(UV_HOME)"; \
	uv venv "$$ENV_DIR"; \
	echo "Activating environment at $$ENV_DIR"; \
	. "$$ENV_DIR/bin/activate"; \
	exec $(SHELL) -i

run:  ## Running natively using python
	$(info Running use python)
	python3 src/bot.py

test:  ## Running python test
	$(info Running python test)
	pytest -q src/test_bot.py

docker: ## Runing using docker-compose
	$(info Docker-compose...)
	docker-compose up -d
