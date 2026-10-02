# fleet-monitoring — operator entrypoints
# Every target is idempotent. `make verify` is the real gate, not `make up`.

SHELL := /bin/bash
STACK := stack
COMPOSE := docker compose -f $(STACK)/docker-compose.yml --env-file .env

.DEFAULT_GOAL := help

.PHONY: help
help: ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------- config ----------
.PHONY: env
env: ## create .env from .env.example if missing
	@test -f .env || { cp .env.example .env; echo "created .env — EDIT IT before continuing"; }

.PHONY: check-env
check-env: ## fail if .env still has placeholder values
	@scripts/check-env.sh

# ---------- stack lifecycle ----------
.PHONY: config
config: ## validate compose + component configs (no containers started)
	$(COMPOSE) config -q && echo "compose: OK"
	@scripts/lint-configs.sh

.PHONY: render-configs
render-configs: ## materialise file-based secrets (Alertmanager token) from .env
	@scripts/render-configs.sh

.PHONY: up
up: env check-env render-configs config ## start/refresh the stack
	$(COMPOSE) up -d --remove-orphans
	@$(COMPOSE) ps

.PHONY: down
down: ## stop the stack (volumes kept)
	$(COMPOSE) down

.PHONY: logs
logs: ## tail stack logs
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## stack status
	$(COMPOSE) ps

.PHONY: pull
pull: ## pull pinned images
	$(COMPOSE) pull

# ---------- verification (the real gate) ----------
.PHONY: verify
verify: ## assert DATA is arriving: metrics, logs, datasources
	@scripts/verify.sh

.PHONY: smoke
smoke: verify ## alias for verify

# ---------- build ----------
# QA-MONITORING-006: the QA fresh-install battery probes `make build` first and falls back
# to `make verify` only when there is no build target. There was none, so the battery ran
# verify against a stack it never started and graded the ambiguous 'no containers' as a
# repo defect. This target is the dependency-free compile step the battery can use — the
# compose stack itself is pulled up by `up`, so building here means the configs render.
.PHONY: build
build: ## compile-check what can be compiled without a running stack
	@test -f .env || cp .env.example .env
	@$(COMPOSE) config -q && echo "build: compose config renders"

# ---------- host / fleet ----------
.PHONY: bootstrap
bootstrap: ## prepare THIS host: docker, dirs, sysctls, tailscale
	@scripts/bootstrap.sh

.PHONY: agent-install
agent-install: ## install the Alloy agent on ONE host: make agent-install HOST=dedi-2
	@test -n "$(HOST)" || { echo "HOST= required"; exit 1; }
	cd ansible && ansible-playbook -l $(HOST) site.yml

.PHONY: agent-install-all
agent-install-all: ## install the Alloy agent on every host in the inventory
	cd ansible && ansible-playbook site.yml

# ---------- infra ----------
.PHONY: tf-plan
tf-plan: ## terraform plan (firewall, optional server)
	cd terraform && terraform init -input=false && terraform plan

.PHONY: tf-apply
tf-apply: ## terraform apply
	cd terraform && terraform init -input=false && terraform apply

.PHONY: tf-fmt
tf-fmt: ## terraform fmt + validate
	cd terraform && terraform fmt -recursive && terraform init -input=false -backend=false && terraform validate

.PHONY: cloud-init
cloud-init: ## render cloud-init user-data for a new instance
	@scripts/render-cloud-init.sh

# ---------- durability ----------
.PHONY: backup
backup: ## push snapshots + git bundle to S3
	@set -a && . ./.env && set +a && scripts/backup-to-s3.sh

.PHONY: restore-check
restore-check: ## assert the newest S3 backup is readable
	@set -a && . ./.env && set +a && scripts/restore-check.sh

.PHONY: restore
restore: ## restore Grafana/Prometheus state from S3: make restore [FROM=monitoring/<ts>]
	@set -a && . ./.env && set +a && scripts/restore-from-s3.sh $(FROM)

# ---------- hygiene ----------
.PHONY: lint
lint: tf-fmt ## shellcheck + yamllint + terraform validate
	@scripts/lint-configs.sh
