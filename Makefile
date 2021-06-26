TRANSIENT_KERNEL=transient/static/transient-kernel
TRANSIENT_INITRAMFS=transient/static/transient-initramfs
TRANSIENT_BUILDROOT_CONFIG=kernel/buildroot-config
TRANSIENT_KCONFIG=kernel/kernel-config
COMPREHENSIVE_EXAMPLE=docs/configuration-file/comprehensive-example.md
MAX_LINE_LENGTH?=100

.PHONY: check
check: check-format check-types check-deadcode

.PHONY: check-format
check-format:
	black -l 90 --check transient test scripts

.PHONY: check-types
check-types:
	mypy --strict transient scripts

.PHONY: check-deadcode
check-deadcode:
	vulture transient --min-confidence 90

.PHONY: format
format:
	black -l 90 transient test scripts

.PHONY: dev
dev: venv/.dev-finished

venv/.dev-finished:
	python3 -m venv venv
	. venv/bin/activate; \
	    python3 -m pip install -e '.[dev]'
	touch venv/.dev-finished
	@echo "Finished building dev environment. Run '. venv/bin/activate'"

.PHONY: prep-release
prep-release: | clean dev $(COMPREHENSIVE_EXAMPLE)
	. venv/bin/activate; \
	    python setup.py sdist bdist_wheel; \
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

.PHONY: unittest
unittest:
	pytest -v

# For running locally. A detailed coverage report
.PHONY: unittest-coverage
unittest-coverage:
	pytest -v --cov=transient --cov-report=term --cov-report=html:artifacts/coverage/html

$(TRANSIENT_INITRAMFS) $(TRANSIENT_KERNEL): $(TRANSIENT_KCONFIG) $(TRANSIENT_BUILDROOT_CONFIG)
	cp $(TRANSIENT_BUILDROOT_CONFIG) kernel/buildroot/.config
	make -C kernel/buildroot
	cp kernel/buildroot/output/images/bzImage $(TRANSIENT_KERNEL)
	cp kernel/buildroot/output/images/rootfs.cpio.gz $(TRANSIENT_INITRAMFS)

.PHONY: kernel
kernel: $(TRANSIENT_KERNEL)

.PHONY: initramfs
initramfs: $(TRANSIENT_INITRAMFS)

.PHONY: $(COMPREHENSIVE_EXAMPLE)
$(COMPREHENSIVE_EXAMPLE):
	scripts/embed_file_into_markdown_template.py \
		--file-to-embed test/config-files/comprehensive-config \
		--markdown-template docs/templates/comprehensive-example-template.md \
		--output-file $@

.PHONY: docs
docs: $(COMPREHENSIVE_EXAMPLE)
	mkdocs serve

.PHONY: clean
clean:
	rm -rf sdist dist $(COMPREHENSIVE_EXAMPLE)
	make -C test clean
	make -C kernel/buildroot clean
