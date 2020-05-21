
.PHONY: all
all: | clean behave

.PHONY: ci
ci: behave-ci

.PHONY: behave
behave:
	behave

.PHONY: behave-ci
behave-ci:
	behave --tags=~@skip-in-ci

.PHONY: clean
clean:
	rm -rf test-frontend test-backend
