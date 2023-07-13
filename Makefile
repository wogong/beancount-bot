.DEFAULT_GOAL:=help
SHELL:=/bin/bash

.PHONY: help deps clean build watch

help:  ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

run:  ## Running natively using python
	$(info Installing dependency and running use python)
	pip3 -r install -r requirements.txt

docker: ## Runing using docker-compose
	$(info Docker-compose...)
	docker-compose up -d

