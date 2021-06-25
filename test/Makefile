ALPINE_3_13_URL="https://github.com/alpinelinux/docker-alpine/blob/db57c96bfff7363dd9bccc56a0ce6e846261bbf8/x86_64/alpine-minirootfs-3.13.4-x86_64.tar.gz?raw=true"
ALPINE_3_13_BASE=artifacts/build-dir/alpine-3.13.tar.xz

.PHONY: all
all: | clean behave

.PHONY: ci
ci: behave-ci

.PHONY: docker-ci
docker-ci: docker-behave-ci

.PHONY: behave
behave:
	behave --tags=~@none

docker-behave-ci-%:
	behave -i $* --tags=~@skip-in-docker-ci --tags=~@skip-in-ci

behave-ci-%:
	behave -i $* --tags=~@skip-in-ci

.PHONY: docker-behave-ci
docker-behave-ci:
	behave --tags=~@skip-in-docker-ci --tags=~@skip-in-ci

.PHONY: behave-ci
behave-ci:
	behave --tags=~@skip-in-ci

.PHONY: prepare-build
prepare-build: $(ALPINE_3_13_BASE)
	cp ../kernel/rootfs_overlay/root/.ssh/authorized_keys artifacts/build-dir
	cp resources/interfaces artifacts/build-dir

$(ALPINE_3_13_BASE): artifacts
	mkdir -p artifacts/build-dir
	curl -L $(ALPINE_3_13_URL) -o $@

artifacts:
	mkdir -p artifacts/

.PHONY: clean
clean:
	rm -rf artifacts
