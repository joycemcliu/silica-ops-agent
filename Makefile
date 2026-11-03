SHELL := /bin/bash
export PATH := $(CURDIR)/.tools/bin:$(PATH)

.PHONY: lint test secrets hooks dev-tools

lint:
	shellcheck scripts/*.sh .githooks/pre-commit
	python3 scripts/validate-envs.py envs.yaml

test:
	bats tests
	python3 -m unittest discover -s tests -p '*_test.py'

secrets:
	bash scripts/scan-secrets.sh

hooks:
	chmod +x .githooks/pre-commit
	git config --local core.hooksPath .githooks

dev-tools:
	bash scripts/install-dev-tools.sh
