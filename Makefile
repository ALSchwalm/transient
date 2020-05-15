
MAX_LINE_LENGTH?=100

.PHONY: check
check: check-format check-types

.PHONY: check-format
check-format:
	pycodestyle --max-line-length $(MAX_LINE_LENGTH) transient

check-types:
	mypy --strict transient

.PHONY: format
format:
	autopep8 -r -i --max-line-length $(MAX_LINE_LENGTH) transient
