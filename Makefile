.PHONY: build test lint fmt deps setup check-config coverage
build test lint fmt deps check-config coverage:
	bash scripts/project.sh $@

setup:
	bash scripts/setup-tools.sh
