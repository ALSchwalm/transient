TRANSIENT_KERNEL=transient/static/transient-kernel
TRANSIENT_KCONFIG=config/transient-kernel-config
MAX_LINE_LENGTH?=100

.PHONY: check
check: check-format check-types

.PHONY: check-format
check-format:
	black -l 90 --check transient test

.PHONY: check-types
check-types:
	mypy --strict transient

.PHONY: format
format:
	black -l 90 transient test

.PHONY: prep-release
prep-release: clean
	python setup.py sdist bdist_wheel
	twine check dist/*

.PHONY: upload-test-release
upload-test-release: prep-release
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*

.PHONY: upload-release
upload-release: prep-release
	twine upload dist/*

.PHONY: test
test:
	make -C test all

test-%:
	make -C test $*

$(TRANSIENT_KERNEL): $(TRANSIENT_KCONFIG)
	git clone --depth 1 --branch v5.7 https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git transient-kernel
	cp $(TRANSIENT_KCONFIG) transient-kernel/.config
	make -C transient-kernel bzImage
	cp transient-kernel/arch/x86/boot/bzImage $(TRANSIENT_KERNEL)

.PHONY: kernel
kernel: transient/static/transient-kernel

.PHONY: docs
docs:
	mkdocs serve

.PHONY: clean
clean:
	rm -rf sdist dist
	make -C test clean
