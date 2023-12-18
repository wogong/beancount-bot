.DEFAULT_GOAL:=help
SHELL:=/bin/bash

.PHONY: help install run docker

help:  ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install:  ## Install dependency
	$(info Installing dependency)
	pip3 -r install -r requirements.txt

run:  ## Running natively using python
	$(info Running use python)
	python3 beanbot.py

docker: ## Runing using docker-compose
	$(info Docker-compose...)
	docker-compose up -d

