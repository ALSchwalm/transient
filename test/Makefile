
.PHONY: all
all: | clean behave

.PHONY: ci
ci: behave-ci

.PHONY: docker-ci
docker-ci: docker-behave-ci

.PHONY: behave
behave:
	behave

.PHONY: docker-behave-ci
docker-behave-ci:
	behave --tags=~@skip-in-docker-ci --tags=~@skip-in-ci

.PHONY: behave-ci
behave-ci:
	behave --tags=~@skip-in-ci

.PHONY: clean
clean:
	rm -rf test-frontend test-backend
