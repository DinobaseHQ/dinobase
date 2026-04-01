.PHONY: test build bump

test:
	uv run pytest

build:
	python -m build

# Usage: make bump V=0.2.0
bump:
	@test -n "$(V)" || (echo "Usage: make bump V=0.2.0" && exit 1)
	@sed -i.bak 's/^version = ".*"/version = "$(V)"/' pyproject.toml && rm pyproject.toml.bak
	@git add pyproject.toml
	@git commit -m "chore: bump version to $(V)"
	@git tag "v$(V)"
	@echo "Tagged v$(V). Push with: git push origin main v$(V)"
