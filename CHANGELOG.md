# Changelog

All notable changes to the [pystclient] project will be documented in this file.<br>
The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

* -/-


## [0.0.5] - 2026-05-07

### Changed
* Changed the approach how dynamic versioning is realised
  * Old:
    * `src/pystclient/__about__.py` was single source of truth for version number.
    * Version inside `pyproject.toml` was dynamically resolved via `hatch.version`.
  * New:
    * `pyproject.toml` is single source of truth for version number.
    * `__version__` attribute inside `src/pystclient/__init__.py` gets dynamically resolved from project metadata
  * NOTE: Project metadata (and hence the project version number) gets populated with data from `pyproject.toml` whenever the package is installed in the local environment, i.e. with every call to `uv sync`, `uv run`, or when a user installs the package via pip.
    This means: As long as the package is _installed_ (even when installed in "just" editable mode) the dynamic resolution of the version number from `pyproject.toml` as single source of truth works just fine.
    With that, the dynamic version is reliably resolved independent of whether or not the package is actually being _built_ (as in the former approach, via `hatch.version`). It is now sufficient that the package is _installed_ in the local environment. Only in the hypothetical case that one runs code from the package directly from source, without installing the package beforehand, the version resolution would fail. However, using code from a package without installing it has, latest since the advent of `uv`, become a very uncommon case.


## [0.0.4] - 2026-05-04

### Changed
* GitHub Workflows:
  * Added 'name: Checkout code' to uses of 'actions/checkout', for better readability and consistency across workflow files.
  * Added 'name: Download build artifacts' to uses of 'actions/download-artifact', for better readability and consistency across workflow files.
  * Added 'name: Publish to PyPI' to uses of 'pypa/gh-action-pypi-publish', for better readability and consistency across workflow files.
  * Added 'name: Upload build artifacts' to uses of 'actions/upload-artifact', for better readability and consistency across workflow files.
  * Changed 'uv sync --upgrade' to 'uv sync -U'
  * Ensured that actions 'upload-artifact' and 'download-artifact' uniformly specify 'dist' as (file)name for the artifact uploaded (or downloaded, respectively), for consistency across workflow files.
  * pull_request_to_main.yml and nightly_build.yml: Added 'workflow_dispatch:' in selected workflows to allow manual trigger of the workflow.
  * Removed redundant 'Set up Python' steps (no longer needed, as 'uv sync' will automatically install Python if not present).
  * Replaced 'Build source distribution and wheel' with 'Build source distribution and wheels' (plural) in workflow step names.
  * Replaced 'Run twine check' with 'Check build artifacts' in workflow step names, to better reflect the purpose of the step.
  * Updated the syntax used for the OS and Python matrix in test workflows.
* pyproject.toml:
  * Removed upper version constraint from required Python version, i.e. changed the "requires-python" field from ">= 3.11, < 3.15" to ">= 3.11". <br>
    Detailed background and reasoning in this good yet long post by Henry Schreiner:
    https://iscinumpy.dev/post/bound-version-constraints/#pinning-the-python-version-is-special <br>
    TLDR: Placing an upper Python version constraint on a Python package causes more harm than it provides benefits.
    The upper version constraint unnecessarily manifests incompatibility with future Python releases.
    Removing the upper version constraint ensures the package remains installable as Python evolves.
    In the majority of cases, the newer Python version will anyhow be backward-compatible. And in the rare case where your package would really not work with a newer Python version,
    users can at least find a solution manually to resolve the conflict, e.g. by pinning your package to the last version compatible with the environment they install it in.
    That way, we ensure it remains _possible_ for users to find a solution, instead of rendering it impossible forever.
* VS Code Settings (Recommended extensions):
  * Removed 'njqdev.vscode-python-typehint' (Python Type Hint). Not maintained since 1 year, and the functionality is now covered by GitHub Copilot.
  * Added 'ms-python.debugpy' (Python Debugger).
  * Added 'ms-python.vscode-python-envs' (Python Environments).
* Python modules: Changed `__ALL__` to `__all__` (lowercase, PEP8 and PEP257 compliant).
* Updated code base with latest changes in python_project_template v0.2.11

### Dependencies
* Added pip-system-certs>=5.3 to dev dependency-group
* .pre-commit-config.yaml: Updated rev of ruff-pre-commit to v0.15.9
* Updated to authlib>=1.6.9
* Updated to dictIO>=0.4.4
* Updated to edn-format>=0.7.5
* Updated to furo>=2025.12
* Updated to jupyter>=1.1.1
* Updated to mypy>=1.19.1
* Updated to myst-parser>=5.0
* Updated to pip-system-certs>=5.3
* Updated to pre-commit>=4.5
* Updated to pydantic>=2.12
* Updated to pyright>=1.1.408
* Updated to pytest-cov>=7.1
* Updated to pytest>=9.0
* Updated to python-dotenv>=1.2.2
* Updated to requests>=2.33
* Updated to ruff>=0.15.9
* Updated to sourcery>=1.43.0
* Updated to sphinx-argparse-cli>=1.21.3
* Updated to sphinx-autodoc-typehints>=3.6
* Updated to Sphinx>=9.0
* Updated to sphinxcontrib-mermaid>=2.0


## [0.0.3] - 2025-12-02

### Added
* Added support for Python 3.14
* Added docstrings:
  * Module docstrings (D100): Added to 7 public modules (clients, exception, misc, models, settings, types, utils/time)
  * Class docstrings (D101): Added to 32 classes across exception, models, and types modules
  * Method docstrings (D102): Added to 50+ public methods in api, clients, and models modules
  * Function docstrings (D103): Added to 8 utility functions in misc and utils/time
  * Magic method docstrings (D105): Added to `__init__`, `__iter__`, `__next__`, `__hash__`
  * ruff.toml: Removed D100-D105 from ignore list

### Removed
* Removed support for Python 3.10

### Changed
* Changed from `pip`/`tox` to `uv` as package manager
* Updated code base to latest changes in python_project_template v0.2.4
* Refactored tests, and partly refactored pystclient code for better typing
* README.md : Completely rewrote section "Development Setup", introducing `uv` as package manager.
* Changed publishing workflow to use OpenID Connect (Trusted Publisher Management) when publishing to PyPI
* pyproject.toml:
  * added required-environments to uv.tools (windows, linux, macos)
  * updated required Python version to ">= 3.11, < 3.15"
  * updated supported Python versions to 3.11, 3.12, 3.13, 3.14
  * Changed build-backend from "setuptools.build_meta" to "hatchling"
  * removed leading carets and trailing slashes from 'exclude' paths
* GitHub workflow _test.yml:
  * updated Python versions in test matrix to 3.11, 3.12, 3.13, 3.14
* GitHub workflow _test_future.yml:
  * updated Python version in test_future to 3.15.0-alpha - 3.15.0
  * Improved the regex and PowerShell code that finds and removes the Python upper version constraint in pyproject.toml
* Added .pre-commit-config.yaml
* Added .sourcery.yaml
* Sphinx conf.py:
  * removed ruff rule exception on file level
* ruff.toml:
  * updated target Python version to "py311"
* VS Code settings:
  * Turned off automatic venv activation
  * (Recommended extensions) Removed deprecated IntelliCode extension and replaced it by GitHub Copilot Chat as recommended replacement.
  * Updated 'mypy-type-checker.reportingScope' to 'custom'.

### Resolved
* Resolved ruff and pyright errors

### Dependencies
* Updated to pydantic>=2.12  (from pydantic~=2.11.4)
* Updated to ruff>=0.14.3  (from ruff>=0.3.0)
* Updated to pyright>=1.1.407  (from pyright>=1.1.352)
* Added mypy>=1.18
* Added sourcery>=1.40
* Added pre-commit>=4.3
* Replaced notebook>=7.4.2 by jupyter>=1.1  (jupyter includes notebook)
* Updated to matplotlib>=3.10  (from matplotlib>=3.10.3)
* Updated to Authlib>=1.6.5  (from Authlib~=1.5.0)
* Updated to requests>=2.32  (from requests~=2.32.3)
* Updated to dictIO>=0.4.2  (from dictIO>=0.3.3)
* Updated to pytest>=8.4  (from pytest>=7.4)
* Updated to pytest-cov>=7.0  (from pytest-cov>=4.1)
* Updated to Sphinx>=8.2  (from Sphinx>=7.2)
* Updated to sphinx-argparse-cli>=1.20  (from sphinx-argparse-cli>=1.11)
* Updated to sphinx-autodoc-typehints>=3.5  (from sphinx-autodoc-typehints>=2.5)
* Updated to myst-parser>=4.0  (from myst-parser>=2.0)
* Updated to furo>=2025.9  (from furo>=2023.9.10)
* Updated to checkout@v5  (from checkout@v4)
* Updated to setup-python@v6  (from setup-python@v4)
* Updated to setup-uv@v7  (from setup-uv@v2)
* Updated to peaceiris/actions-gh-pages@v4  (from peaceiris/actions-gh-pages@v3)
* Updated to upload-artifact@v5  (from upload-artifact@v3)


## [0.0.2] - 2024-02-22

### Added
* README.md : Under `Development Setup`, added a step to install current package in "editable" mode, using the pip install -e option.
This removes the need to manually add /src to the PythonPath environment variable in order for debugging and tests to work.

### Removed
* VS Code settings: Removed the setting which added the /src folder to PythonPath. This is no longer necessary. Installing the project itself as a package in "editable" mode, using the pip install -e option, solves the issue and removes the need to manually add /src to the PythonPath environment variable.

### Changed
* Moved all project configuration from setup.cfg to pyproject.toml
* Moved all tox configuration from setup.cfg to tox.ini.
* Moved pytest configuration from pyproject.toml to pytest.ini
* Deleted setup.cfg
* replaced black formatter with ruff formatter
* VS Code settings: Turned off automatic venv activation

### Dependencies
* updated to ruff==0.3.0  (from ruff==0.2.1)
* updated to pyright==1.1.352  (from pyright==1.1.350)
* updated to dictIO>=0.3.3  (from dictIO>=0.3.1)
* updated to black[jupyter]==24.1  (from black[jupyter]==23.12)
* updated to sourcery==1.15  (from sourcery==1.14)
* removed black


## [0.0.1] - 2023-02-21

* Initial release

### Added

* added this

### Changed

* changed that

### Dependencies

* updated to some_package_on_pypi>=0.1.0

### Fixed

* fixed issue #12345

### Deprecated

* following features will soon be removed and have been marked as deprecated:
    * function x in module z

### Removed

* following features have been removed:
    * function y in module z



<!-- Markdown link & img dfn's -->
[unreleased]: https://github.com/dnv-opensource/pystclient/compare/v0.0.5...HEAD
[0.0.5]: https://github.com/dnv-opensource/pystclient/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/dnv-opensource/pystclient/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/dnv-opensource/pystclient/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/dnv-opensource/pystclient/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/dnv-opensource/pystclient/releases/tag/v0.0.1
[pystclient]: https://github.com/dnv-opensource/pystclient
