UBUNTU_20_04_URL="http://cdimage.ubuntu.com/ubuntu-base/releases/20.04/release/ubuntu-base-20.04-base-amd64.tar.gz"
UBUNTU_BASE=artifacts/build-dir/ubuntu.tar.gz

.PHONY: all
all: | clean behave

.PHONY: ci
ci: behave-ci

.PHONY: docker-ci
docker-ci: docker-behave-ci

.PHONY: behave
behave: prepare
	behave

.PHONY: docker-behave-ci
docker-behave-ci: prepare
	behave --tags=~@skip-in-docker-ci --tags=~@skip-in-ci

.PHONY: behave-ci
behave-ci: prepare
	behave --tags=~@skip-in-ci

.PHONY: prepare
prepare: $(UBUNTU_BASE)
	cp ../kernel/rootfs_overlay/etc/ssh/sshd_config artifacts/build-dir
	cp ../kernel/rootfs_overlay/root/.ssh/authorized_keys artifacts/build-dir
	cp resources/dhcp.network artifacts/build-dir

$(UBUNTU_BASE): | artifacts
	mkdir -p artifacts/build-dir
	curl -L $(UBUNTU_20_04_URL) -o artifacts/build-dir/ubuntu.tar.gz

artifacts:
	mkdir -p artifacts/

.PHONY: clean
clean:
	rm -rf artifacts
