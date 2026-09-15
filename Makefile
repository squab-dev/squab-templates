.PHONY: tools build test check smoke
tools:
	sh tools/install-tools.sh
build:
	sh tools/build.sh paper
test:
	python3 -m unittest discover -s tests -v
check: test
	sh -n tools/build.sh tools/install-tools.sh tools/smoke.sh images/paper/squab-paper-launcher
smoke:
	sh tools/smoke.sh
