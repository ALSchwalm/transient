
MAX_LINE_LENGTH?=100

.PHONY: check
check: check-format check-types

.PHONY: check-format
check-format:
	pycodestyle --max-line-length $(MAX_LINE_LENGTH) transient

.PHONY: check-types
check-types:
	mypy transient

.PHONY: format
format:
	autopep8 -r -i --max-line-length $(MAX_LINE_LENGTH) transient

.PHONY: prep-release
prep-release:
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

.PHONY: docs
docs:
	mkdocs serve
