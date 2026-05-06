[![pypi](https://img.shields.io/pypi/v/pystclient.svg?color=blue)](https://pypi.python.org/pypi/pystclient)
[![versions](https://img.shields.io/pypi/pyversions/pystclient.svg?color=blue)](https://pypi.python.org/pypi/pystclient)
[![license](https://img.shields.io/pypi/l/pystclient.svg)](https://github.com/dnv-opensource/pystclient/blob/main/LICENSE)
![ci](https://img.shields.io/github/actions/workflow/status/dnv-opensource/pystclient/.github%2Fworkflows%2Fnightly_build.yml?label=ci)
[![docs](https://img.shields.io/github/actions/workflow/status/dnv-opensource/pystclient/.github%2Fworkflows%2Fpush_to_release.yml?label=docs)][pystclient_docs]

# Pystclient - A Python client for Simulation Trust Center (STC)

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
  - [Logging in to STC](#logging-in-to-stc)
  - [Running a Simulation](#running-a-simulation)
  - [Fetching and Displaying Results](#fetching-and-displaying-results)
  - [CLI Options](#cli-options)
- [Development Setup](#development-setup)
- [Meta](#meta)
- [Contributing](#contributing)

`pystclient` is a Python client library for **Simulation Trust Center (STC)**.
It provides a convenient, typed Python API for interacting with STC backend,
so you can manage simulation projects and run simulations directly from Python
scripts, notebooks, or CI pipelines without having to call the underlying
HTTP API by hand.

`pystclient` supports:

* **Authentication** — interactive OAuth2 authorization-code flow via Veracity Identity with
  automatic token caching and refresh.
* **Project management** — create, configure, list, and delete STC projects;
  manage their FMU model selections, parameter sets, variable connections,
  and logging configuration.
* **Simulator lifecycle management** — provision (create) one or more
  simulators from a simulation configuration, wait for readiness, and start,
  stop, or terminate them.
* **Simulator control & monitoring** — query simulator status, start/stop
  result recording, and gracefully end running simulations.
* **Retrieving simulation data** — list per-instance measurement records,
  query time-series variable data over arbitrary time windows, and iterate
  through simulation results in configurable time steps.


## Installation

```sh
pip install pystclient
```

## Usage

### Logging in to STC

```py
from pystclient.clients import PyStclient

# Authenticate and create a client instance
client = PyStclient()

# If you want to use interactive login (browser-based OAuth2):
client.authenticate()  # This will prompt for login if needed

# Now you can use the client to interact with STC
projects = client.list_projects()
print(projects)
```

### Running a Simulation

The following example runs a non-interactive distributed simulation using a
Spring-Mass-Damper project that has already been configured on the STC platform.

```py
import time

from pystclient.clients import PyStclient, SimulationResults
from pystclient.models import (
    LoggingConfiguration,
    ModelParameters,
    ModelVariable,
    SimulationConfig,
    SimulationParameters,
)
from pystclient.types import SimulationType

# 1 — Authenticate
client = PyStclient()
client.authenticate()

# 2 — Select an existing project
projects = client.project.info_all()
project = next(p for p in projects if p.name == "Spring-Mass-Damper")

# 3 — Configure simulation parameters
sim_params = SimulationParameters(
    base_step_size=0.01,
    end_time=20,
    config_name="Config 1",
    model_parameters=[
        ModelParameters(
            name="Mass1",
            step_size=0.02,
            parameters=[ModelVariable(name="absTolerance", initial_value=2e-4)],
        ),
        ModelParameters(
            name="Spring1",
            parameters=[ModelVariable(name="absTolerance", initial_value=2e-4)],
        ),
        ModelParameters(
            name="Damper1",
            parameters=[ModelVariable(name="absTolerance", initial_value=2e-4)],
        ),
    ],
)
client.project.update_parameters(project.id, sim_params)

# 4 — Enable post-plotting so results are persisted
client.project.update_log_config(
    project.id, LoggingConfiguration(post_plotting=True)
)

# 5 — Create a simulator and wait until it is ready
statuses, ready_future = client.simulator.create(
    SimulationConfig(
        project_id=project.id,
        parameter_set_names=["Config 1"],
        type=SimulationType.DISTRIBUTED,
    )
)
simulator_id = statuses[0].id
assert ready_future.result(600), "Simulator did not become ready in time!"

# 6 — Start the simulation with recording enabled
client.simulator.start(simulator_id, record=True)

# 7 — Poll until the simulation finishes
while not client.simulator.finished(simulator_id):
    s = client.simulator.status(simulator_id)
    print(f"  simulation_time={s.simulation_time}  end_time={s.end_time}")
    time.sleep(2)

# 8 — End the simulation and collect results
results: SimulationResults | None = client.simulator.end_simulation(simulator_id).result(120)
assert results is not None, "No results returned!"
print(f"Results available — {results.measurement_size()} measurement(s).")
```

### Fetching and Displaying Results

Once a simulation has completed and a `SimulationResults` object is available
(see the previous example), you can iterate over the time-series data and
plot it with [matplotlib](https://matplotlib.org/):

```py
import matplotlib.pyplot as plt

from pystclient.models import QueryVariable
from pystclient.utils.time import convert_to_timestamp

# Reset the results iterator to start from the beginning
results.reset()

# Iterate through all time windows and collect displacement data
fig, ax = plt.subplots(figsize=(10, 5))

for query_result in results:
    for result in query_result:
        if result.signal == "dis_yx":
            x = convert_to_timestamp(result.x)
            ax.plot(x, result.y, label=f"{result.module} — {result.signal}")

ax.set_xlabel("Time [s]")
ax.set_ylabel("Displacement [m]")
ax.set_title("Spring-Mass-Damper — Displacement (dis_yx)")
ax.legend()
plt.tight_layout()
plt.show()
```

You can also narrow the query to specific variables using `query_variables`:

```py
results.reset(
    query_variables=[
        QueryVariable(instance_name="Mass1", name="dis_yx", causality="output"),
    ]
)

for query_result in results:
    for result in query_result:
        print(f"{result.module}.{result.signal}: {len(result.y)} data points")
```

> **Tip**: Use `results.step(timedelta(minutes=5))` to change the size of
> each time window when paging through results.

> **See also**: For complete, runnable notebooks check the
> [`examples/`](https://github.com/dnv-opensource/pystclient/tree/main/examples) directory.

### CLI Options

The `pystclient` command-line interface supports the following options:

| Option                | Description |
|-----------------------|-------------|
| `-c`, `--config <file>`      | Name of the file containing the pystclient configuration. Optional. |
| `--login`             | Login to Veracity Identity to retrieve and store an access token to a local cache. Mutually exclusive with `--delete-token`. Required unless `--delete-token` is used. |
| `--delete-token`      | Delete an access token stored in a local cache. Mutually exclusive with `--login`. Required unless `--login` is used. |
| `-q`, `--quiet`       | Console output will be quiet (sets log level to ERROR). Mutually exclusive with `--verbose`. |
| `-v`, `--verbose`     | Console output will be verbose (sets log level to INFO). Mutually exclusive with `--quiet`. |
| `--log <file>`        | Name of log file. If specified, activates logging to file. Optional. |
| `--log-level <level>` | Set a specific log level for file logging. Choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Default: `WARNING`. |



_For more examples and usage, please refer to pystclient's [documentation][pystclient_docs]._


## Development Setup

### 1. Install uv
This project uses `uv` as package manager.
If you haven't already, install [uv](https://docs.astral.sh/uv), preferably using it's ["Standalone installer"](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_2) method: <br>
..on Windows:
```sh
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
..on MacOS and Linux:
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```
(see [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) for all / alternative installation methods.)

Once installed, you can update `uv` to its latest version, anytime, by running:
```sh
uv self update
```

### 2. Clone the repository
Clone the pystclient repository into your local development directory:
```sh
git clone https://github.com/dnv-opensource/pystclient path/to/your/dev/pystclient
```
Change into the project directory after cloning:
```sh
cd pystclient
```

### 3. Install dependencies
Run `uv sync -U` to create a virtual environment and install all project dependencies into it:
```sh
uv sync -U
```
> **Note**: Using `--no-dev` will omit installing development dependencies.

> **Explanation**: The `-U` option stands for `--update`. It forces `uv` to fetch and install the latest versions of all dependencies,
> ensuring that your environment is up-to-date.

> **Note**: `uv` will create a new virtual environment called `.venv` in the project root directory when running
> `uv sync -U` the first time. Optionally, you can create your own virtual environment using e.g. `uv venv`, before running
> `uv sync -U`.

### 4. (Optional) Activate the virtual environment
When using `uv`, there is in almost all cases no longer a need to manually activate the virtual environment. <br>
`uv` will find the `.venv` virtual environment in the working directory or any parent directory, and activate it on the fly whenever you run a command via `uv` inside your project folder structure:
```sh
uv run <command>
```

However, you still _can_ manually activate the virtual environment if needed.
When developing in an IDE, for instance, this can in some cases be necessary depending on your IDE settings.
To manually activate the virtual environment, run one of the "known" legacy commands: <br>
..on Windows:
```sh
.venv\Scripts\activate.bat
```
..on Linux:
```sh
source .venv/bin/activate
```

### 5. Install pre-commit hooks
The `.pre-commit-config.yaml` file in the project root directory contains a configuration for pre-commit hooks.
To install the pre-commit hooks defined therein in your local git repository, run:
```sh
uv run pre-commit install
```

All pre-commit hooks configured in `.pre-commit-config.yaml` will now run each time you commit changes.

pre-commit can also manually be invoked, at anytime, using:
```sh
uv run pre-commit run --all-files
```

To skip the pre-commit validation on commits (e.g. when intentionally committing broken code), run:
```sh
uv run git commit -m <MSG> --no-verify
```

To update the hooks configured in `.pre-commit-config.yaml` to their newest versions, run:
```sh
uv run pre-commit autoupdate
```

### 6. Test that the installation works
To test that the installation works, run pytest in the project root folder:
```sh
uv run pytest
```

### 7. Generating the third-party license file

A `THIRD_PARTY_LICENSES` file that aggregates the license texts of all
runtime dependencies can be generated by running:

```sh
pip-licenses --with-license-file --no-license-path --output-file THIRD_PARTY_LICENSES
```

> **Note**: `pip-licenses` reports licenses of packages that are *installed*
> in the current environment. Make sure your project dependencies are
> installed (e.g. via `uv sync`) before running the command, otherwise the
> generated file will be empty or incomplete.

Using `uv`:

```sh
uv run pip-licenses --with-license-file --no-license-path --output-file THIRD_PARTY_LICENSES
```


## License

This project is licensed under the Mozilla Public License, v. 2.0 (MPL‑2.0).

A copy of the license is included in the [LICENSE](LICENSE.md) file.
You may also obtain a copy at https://mozilla.org/MPL/2.0/.

## Meta

Copyright (c) 2026 [DNV](https://www.dnv.com) AS. All rights reserved.

pystclient is developed by DNV Group Research and Development in collaboration with DNV Maritime.

All code in pystclient is DNV intellectual property of DNV.

Hee Jong Park - [@LinkedIn](https://www.linkedin.com/in/heejongpark/) - hee.jong.park@dnv.com

Claas Rostock - [@LinkedIn](https://www.linkedin.com/in/claasrostock/?locale=en_US) - claas.rostock@dnv.com

## Contributing

1. Fork it (<https://github.com/dnv-opensource/pystclient/fork>)
2. Create an issue in your GitHub repo
3. Create your branch based on the issue number and type (`git checkout -b issue-name`)
4. Evaluate and stage the changes you want to commit (`git add -i`)
5. Commit your changes (`git commit -am 'place a descriptive commit message here'`)
6. Push to the branch (`git push origin issue-name`)
7. Create a new Pull Request in GitHub

For your contribution, please make sure you follow the [STYLEGUIDE](STYLEGUIDE.md) before creating the Pull Request.

<!-- Markdown link & img dfn's -->
[pystclient_docs]: https://dnv-opensource.github.io/pystclient/README.html
