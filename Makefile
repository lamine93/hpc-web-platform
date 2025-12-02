# Minimal Makefile for slurm-gui docker-compose management

.PHONY: help build up down restart logs shell clean build-gui up-gui

# Variables
COMPOSE := docker-compose
PROJECT := slurm-gui

# Default target
.DEFAULT_GOAL := help

##@ Help

help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

##@ Build & Deploy

build: ## Build slurm-gui image
	$(COMPOSE) build --progress plain

up: ## Start all services (detached)
	$(COMPOSE) up -d
	@echo "GUI available at: http://192.168.64.2:5000"


restart-gui: ## Rebuild and restart slurm-gui only (clean old containers)
	@echo "Cleaning old slurm-gui containers..."
	docker ps -a | grep slurm-gui | awk '{print $$1}' | xargs -r docker rm -f || true
	@echo "Rebuilding slurm-gui..."
	$(COMPOSE) build slurm-gui
	@echo "Starting slurm-gui..."
	$(COMPOSE) up -d slurm-gui
	@echo "slurm-gui rebuilt and restarted"



down: ## Stop and remove containers
	$(COMPOSE) down

##@ Control

start: ## Start existing containers
	$(COMPOSE) start

stop: ## Stop containers without removing
	$(COMPOSE) stop

restart: ## Restart all services
	$(COMPOSE) restart


##@ Logs & Monitoring

logs: ## Show all logs (live)
	$(COMPOSE) logs -f

logs-gui: ## Show slurm-gui logs
	$(COMPOSE) logs -f slurm-gui

ps: ## List running containers
	$(COMPOSE) ps

status: ## Show detailed status
	@$(COMPOSE) ps

##@ Shell Access

shell: ## Open bash shell in slurm-gui
	$(COMPOSE) exec slurm-gui bash

shell-mongo: ## Open MongoDB shell
	$(COMPOSE) exec mongodb mongosh

##@ Maintenance

clean: ## Stop and clean up stopped containers
	$(COMPOSE) down --remove-orphans
	docker system prune -f

backup: ## Backup MongoDB
	@mkdir -p backups
	docker exec $$($(COMPOSE) ps -q mongodb) mongodump --out /tmp/backup
	docker cp $$($(COMPOSE) ps -q mongodb):/tmp/backup ./backups/mongodb-$$(date +%Y%m%d-%H%M%S)
	@echo "Backup saved to ./backups/"

reset: down clean up ## Full reset (down + clean + up)
