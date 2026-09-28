.PHONY: tools build test check smoke
GAME ?= paper
tools:
	sh tools/install-tools.sh
build:
	sh tools/build.sh $(GAME)
test:
	python3 -m unittest discover -s tests -v
check: test
	sh -n tools/build.sh tools/install-tools.sh tools/smoke.sh images/paper/squab-paper-launcher images/hytale/squab-hytale-launcher tools/smoke-hytale.sh
smoke:
	sh tools/smoke$(if $(filter hytale,$(GAME)),-hytale,).sh
