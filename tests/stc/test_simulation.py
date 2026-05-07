import logging
import os
import time
import uuid
from concurrent import futures
from pathlib import Path

import pytest

from pystclient.clients import PyStclient, SimulationResults
from pystclient.models import (
    FmuConnections,
    FmuNode,
    FmuSelect,
    LoggingConfiguration,
    MeasurementQuery,
    Measurements,
    ProjectInformation,
    QueryVariable,
    SimulationConfig,
    SimulationInfo,
    SimulationParameters,
)
from pystclient.types import SimulationType

pytestmark = pytest.mark.skipif(os.environ.get("CI") is not None, reason="Skip on CI test")

logger = logging.getLogger(__name__)


def test_run_simulation(
    client: PyStclient,
    test_project: ProjectInformation,
    test_models_by_model_id: list[FmuSelect],
):
    assert client.project.select_models(project_id=test_project.id, fmu_models=test_models_by_model_id)

    mass = FmuNode(instance="Mass1", fmu="Mass.fmu")
    spring = FmuNode(instance="Spring1", fmu="Spring.fmu")
    damper = FmuNode(instance="Damper1", fmu="Damper.fmu")

    conns = FmuConnections.build_connections(
        [
            (mass, "spring_connector", spring, "mass_connector"),
            (mass, "damper_connector", damper, "mass_connector"),
        ]
    )

    assert client.project.create_connections(test_project.id, conns)

    sim_params = SimulationParameters(
        base_step_size=0.01,
        end_time=10,
    )
    assert client.project.update_parameters(test_project.id, sim_params)

    logger.info("Turn on time-series data logging")
    log_config = LoggingConfiguration(post_plotting=True)
    assert client.project.update_log_config(test_project.id, log_config)

    logger.info("Creating a simulator..")
    status, future = client.simulator.create(
        SimulationConfig(
            project_id=test_project.id,
            parameter_set_names=["Config 1"],
            type=SimulationType.DISTRIBUTED,
            is_interactive=True,
        )
    )
    simulator_id = status[0].id
    assert str(status[0].project_id).casefold() == str(test_project.id).casefold()
    assert status[0].status == "created"

    assert len(client.project.current_simulators(test_project.id)) == 1

    logger.info("Waiting until the simulator status becomes ready")
    assert future.result(600)  # In case node needs to scale up

    logger.info("Starting simulation")
    assert client.simulator.start(simulator_id, record=True)

    logger.info("Waiting until the simulation is finished")
    while not client.simulator.finished(simulator_id):
        time.sleep(1)

    logger.info("Terminating simulation")
    f = client.simulator.end_simulation(simulator_id)
    simulation_results = f.result(120)

    assert isinstance(simulation_results, SimulationResults)


def _test_tutorial_measurements(
    client: PyStclient,
    project_id: uuid.UUID,
    meas: Measurements,
) -> None:
    mid = meas.id
    instance = meas.metadata.instances[0]
    variable = instance.variables[0]
    q = MeasurementQuery(
        variables=[
            QueryVariable(
                instance_id=instance.instance_id,
                name=variable.name,
                causality=variable.causality,
            )
        ],
        time_from=0,
        time_to=10,
    )
    logger.info(f"Testing measurement for {q.model_dump(by_alias=True, mode='json')}")
    result1 = client.measurement.query(mid, q)
    assert result1[0].signal == variable.name
    assert result1[0].module == instance.instance_name

    # Another way to check the results..
    completed_simulation: SimulationInfo = client.project.completed_simulations(project_id, limit=1)[0]
    simulation_results = client.measurement.simulation_results(project_id, completed_simulation.id)
    assert isinstance(simulation_results, SimulationResults)

    simulation_results.reset(
        0,
        [
            QueryVariable(
                instance_name=instance.instance_name,
                name=variable.name,
                causality=variable.causality,
            )
        ],
    )

    for result in simulation_results:
        assert result[0].signal == variable.name
        assert result[0].module == instance.instance_name

    simulation_results.reset(
        0,
        [
            QueryVariable(
                instance_name=instance.instance_name,
                name=variable.name,
                causality=variable.causality,
            )
        ],
    )
    result = next(simulation_results)
    assert result[0].y[:10] == result1[0].y[:10]


def test_simulation_data(
    client: PyStclient,
    test_project: ProjectInformation,
) -> None:
    # One way to check results
    measurements = client.measurement.measurements(test_project.id)
    assert len(measurements) > 0
    _test_tutorial_measurements(client, test_project.id, measurements[0])


def test_batch_simulation(
    client: PyStclient,
    test_project: ProjectInformation,
    test_models_by_model_id: list[FmuSelect],
) -> None:
    assert client.project.select_models(project_id=test_project.id, fmu_models=test_models_by_model_id)

    mass = FmuNode(instance="Mass1", fmu="Mass.fmu")
    spring = FmuNode(instance="Spring1", fmu="Spring.fmu")
    damper = FmuNode(instance="Damper1", fmu="Damper.fmu")

    conns = FmuConnections.build_connections(
        [
            (mass, "spring_connector", spring, "mass_connector"),
            (mass, "damper_connector", damper, "mass_connector"),
        ]
    )

    assert client.project.create_connections(test_project.id, conns)

    logger.info("Turn on time-series data logging")
    log_config = LoggingConfiguration(post_plotting=True)
    assert client.project.update_log_config(test_project.id, log_config)

    sim_params1 = SimulationParameters(base_step_size=0.01, end_time=10, config_name="Config 1")
    sim_params2 = SimulationParameters(base_step_size=0.01, end_time=10, config_name="Config 2")
    assert client.project.update_parameters(test_project.id, sim_params1, sim_params2)

    logger.info("Creating a batch simulation..")
    statuses, future = client.simulator.create(
        SimulationConfig(
            project_id=test_project.id,
            parameter_set_names=["Config 1", "Config 2"],
            type=SimulationType.DISTRIBUTED,
            batch_size=2,
        )
    )

    _ = future.result(120)
    logger.info("Created:")
    for s in statuses:
        logger.info(f"Batch-id: {s.batch_id}, simulator-id: {s.id}")

    # assert len(client.project.current_simulators(test_project.id)) == 2

    logger.info("Waiting until the simulation is finished")
    simulator_ids = [x.id for x in statuses]

    while not client.simulator.finished(*simulator_ids):
        time.sleep(1)

    logger.info("All simulations are done..")

    ####################################
    # Example: Retrieving Measurements
    ####################################

    # Getting simulation IDs via `completed_simulations`
    completed_simulations: list[SimulationInfo] = []

    while len(completed_simulations) != 2:
        completed_simulations = client.project.completed_simulations(
            project_id=test_project.id,
            simulator_ids=simulator_ids,
            limit=10,
        )
        time.sleep(5)

    assert len(completed_simulations) == 2

    # First two measurements are from the previous batch simulation: Config 1 and Config 2
    measurements_1 = client.measurement.measurements(test_project.id)[:2]
    assert len(measurements_1) == 2

    simulation_id_set = {x.simulation.id for x in statuses if x.simulation is not None}

    # Checking if the retrieved simulation IDs are consistent with the simulator statuses
    for i in range(len(completed_simulations)):
        m = client.measurement.measurements(test_project.id, completed_simulations[i].id)[0]
        assert m.simulation_id in simulation_id_set
        assert measurements_1[i].simulation_id in simulation_id_set

    # Getting simulation lists for this batch-id
    batch_id = statuses[0].batch_id
    assert batch_id is not None

    sims = client.project.completed_simulations_by_batch_id(test_project.id, batch_id)
    assert len(sims) == 2

    time.sleep(5)  # Wait for the measurements to be available
    # Checking if measurements are correctly fetched
    for sim in sims:
        m = client.measurement.measurements(test_project.id, sim.id)[0]
        _test_tutorial_measurements(client, test_project.id, m)


def test_failed_init(
    client: PyStclient,
    test_project: ProjectInformation,
    test_models_by_model_id: list[FmuSelect],
) -> None:
    fmus_dir_path = Path().absolute().parent
    _ = client.model.upload_model(fmus_dir_path / "fmus" / "ErrorAtInit.fmu")

    fmus: list[FmuSelect] = [*test_models_by_model_id, FmuSelect(filename="ErrorAtInit.fmu")]
    assert client.project.select_models(project_id=test_project.id, fmu_models=fmus)

    mass = FmuNode(instance="Mass1", fmu="Mass.fmu")
    spring = FmuNode(instance="Spring1", fmu="Spring.fmu")
    damper = FmuNode(instance="Damper1", fmu="Damper.fmu")
    error_at_init = FmuNode(instance="ErrorAtInit1", fmu="ErrorAtInit.fmu")

    conns = FmuConnections.build_connections(
        [
            (mass, "spring_connector", spring, "mass_connector"),
            (mass, "damper_connector", damper, "mass_connector"),
            error_at_init,
        ]
    )

    assert client.project.create_connections(test_project.id, conns)

    status, future = client.simulator.create(
        SimulationConfig(
            project_id=test_project.id,
            parameter_set_names=["Config 1"],
            type=SimulationType.DISTRIBUTED,
        )
    )

    simulator_id = status[0].id

    # Waiting for 20 seconds. Future will throw TimeoutError because the simulator won't start to run (stepping) within
    # the specified amount of time
    with pytest.raises(futures.TimeoutError):
        _ = future.result(20)

    # Alternatively, you can also check if the simulator is ready by calling SimulatorClient.ready()
    assert not client.simulator.ready(simulator_id)

    # Because the simulator did not become ready within the expected time bound, we terminate it
    assert client.simulator.terminate(simulator_id)

    # Deleting the erroneous fmu uploaded to the Model Library
    models = client.model.find_models_by_filename("ErrorAtInit.fmu")
    assert client.model.delete_models([x.id for x in models])
