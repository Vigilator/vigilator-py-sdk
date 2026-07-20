# vigilator-py-sdk

[![Release](https://img.shields.io/github/v/release/vigilator/vigilator-py-sdk)](https://img.shields.io/github/v/release/vigilator/vigilator-py-sdk)
[![Build status](https://img.shields.io/github/actions/workflow/status/vigilator/vigilator-py-sdk/main.yml?branch=main)](https://github.com/vigilator/vigilator-py-sdk/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/vigilator/vigilator-py-sdk/branch/main/graph/badge.svg)](https://codecov.io/gh/vigilator/vigilator-py-sdk)
[![Commit activity](https://img.shields.io/github/commit-activity/m/vigilator/vigilator-py-sdk)](https://img.shields.io/github/commit-activity/m/vigilator/vigilator-py-sdk)
[![License](https://img.shields.io/github/license/vigilator/vigilator-py-sdk)](https://img.shields.io/github/license/vigilator/vigilator-py-sdk)

This is the SDK for the vigilator API.

- **Github repository**: <https://github.com/vigilator/vigilator-py-sdk/>
- **Documentation** <https://docs.vigilator.ai>

## Getting started with the vigilator SDK for development

### 1. Set Up Your Development Environment

Then, install the environment and the pre-commit hooks with

```bash
make install
```

This will also generate your `uv.lock` file

### 2. Run the pre-commit hooks

Initially, the CI/CD pipeline might be failing due to formatting issues. To resolve those run:

```bash
uv run pre-commit run -a
```

### 3. Commit the changes

Lastly, commit the changes made by the two steps above to your repository.

```bash
git add .
git commit -m 'chore: fix formatting issues'
git push origin main
```

You are now ready to start development on your project!
The CI/CD pipeline will be triggered when you open a pull request, merge to main, or when you create a new release.

## Commit messages

This project uses [Commitizen](https://commitizen-tools.github.io/commitizen/) to enforce the [Conventional Commits](https://www.conventionalcommits.org/) standard. Two pre-commit hooks (installed by `make install`) enforce this:

- **On commit**: the commit message is validated and the commit is rejected if it does not follow the convention.
- **On push**: all commits on the branch are validated again.

Commit messages must have the form `<type>(<optional scope>): <description>`, for example:

```
feat(client): add retry support to API requests
fix: handle empty responses from the vigilator API
docs: document the authentication flow
```

Common types are `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, and `chore`. Use `feat` for changes that should trigger a minor version bump and `fix` for a patch bump; add a `BREAKING CHANGE:` footer (or `!` after the type) for breaking changes.

If you prefer an interactive prompt that builds the message for you, run:

```bash
cz c
```
Install Commitizen as a tool: ``uv tool install commitizen``

## Releasing a new version

The project version lives in `pyproject.toml` and is managed by Commitizen. To release:

1. Bump the version, update `CHANGELOG.md`, and create a git tag (in the form `*.*.*`, no `v` prefix) in one step. Commitizen determines the new semver version from the conventional commits since the last tag:

```bash
cz bump
git push --follow-tags
```

While the project is on major version `0`, breaking changes bump the minor version instead of the major version (`major_version_zero` is enabled).

2. Create a [new release](https://github.com/vigilator/vigilator-py-sdk/releases/new) on Github from the pushed tag.
