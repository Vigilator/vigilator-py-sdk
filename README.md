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
git commit -m 'Fix formatting issues'
git push origin main
```

You are now ready to start development on your project!
The CI/CD pipeline will be triggered when you open a pull request, merge to main, or when you create a new release.


## Releasing a new version

- Create a [new release](https://github.com/vigilator/vigilator-py-sdk/releases/new) on Github.
- Create a new tag in the form `*.*.*`.
