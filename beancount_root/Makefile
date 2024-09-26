.DEFAULT_GOAL:=help
SHELL:=/bin/bash
BEAN = beancount_path # beancount path, where you put all your ledger files and Makefile
BEANCOUNT_FILE = beancount_file_path # beancount file path, your root file

.PHONY: help bal pay check

help:  ## Display this help
        @awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

bal: ## Check balance, make bal account=1234
        $(info Query account balance)
        @if [ -z "$(account)" ]; then \
                echo "Error: Please specify an account name. Usage: make bal account=<account_name>"; \
                exit 1; \
        fi
        @echo "Checking balance for account: $(account)"
        $(BEAN)/.venv/bin/bean-query $(BEANCOUNT_FILE) "SELECT account, sum(position) WHERE account ~ '$(account)' GROUP BY account"

pay: ## Check month payment, make pal account=2345
        $(info Query account payment)
        @if [ -z "$(account)" ]; then \
                echo "Error: Please specify an account name. Usage: make pay account=<account_name>"; \
                exit 1; \
        fi
        @echo "Checking payment for account: $(account)"
        $(BEAN)/.venv/bin/bean-query $(BEANCOUNT_FILE) "select account, month(date) as month, sum(position) from year=2024 where account ~ '$(account)' and number<0 group by account, month order by month desc"

check: ## bean-check
        $(info Check beancount file)
        $(BEAN)/.venv/bin/bean-check $(BEANCOUNT_FILE)