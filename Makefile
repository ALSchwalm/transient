TRANSIENT_KERNEL=transient/static/transient-kernel
TRANSIENT_KCONFIG=config/transient-kernel-config
COMPREHENSIVE_EXAMPLE=docs/configuration-file/comprehensive-example.md
MAX_LINE_LENGTH?=100

.PHONY: check
check: check-format check-types

.PHONY: check-format
check-format:
	black -l 90 --check transient test scripts

.PHONY: check-types
check-types:
	mypy --strict transient scripts

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
