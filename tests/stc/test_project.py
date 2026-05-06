# sourcery skip: dont-import-test-modules
import os
import uuid

import pytest

from pystclient.clients import PyStclient
from pystclient.models import (
    BaseProject,
    FmuConnections,
    FmuNode,
    FmuSelect,
    ModelParameters,
    ModelVariable,
    ProjectInformation,
    SimulationParameters,
)
from pystclient.types import FmuVariableTypeEnum
from tests.stc.conftest import TEST_PROJECT_PREFIX

pytestmark = pytest.mark.skipif(os.environ.get("CI") is not None, reason="Skip on CI test")


@pytest.mark.dependency
def test_create_and_delete_project(client: PyStclient):
    project_name = f"{TEST_PROJECT_PREFIX}-{uuid.uuid4()}"
    project_info = client.project.create(BaseProject(name=project_name))
    assert project_info.name == project_name
    assert client.project.delete(project_info.id)


def test_get_project(client: PyStclient, test_project: ProjectInformation):
    resp = client.project.info(test_project.id)
    assert resp.id == test_project.id
    assert resp.name == test_project.name


def test_select_models_by_name(
    client: PyStclient,
    test_project: ProjectInformation,
    test_models_by_filename: list[FmuSelect],
) -> None:
    assert client.project.select_models(project_id=test_project.id, fmu_models=test_models_by_filename)
    assert client.project.deselect_all_models(project_id=test_project.id)


def test_select_models_by_version_id(
    client: PyStclient,
    test_project: ProjectInformation,
    test_models_by_version_id: list[FmuSelect],
):
    assert client.project.select_models(project_id=test_project.id, fmu_models=test_models_by_version_id)
    assert client.project.deselect_all_models(project_id=test_project.id)


def test_select_models_by_model_id(
    client: PyStclient,
    test_project: ProjectInformation,
    test_models_by_model_id: list[FmuSelect],
):
    assert client.project.select_models(project_id=test_project.id, fmu_models=test_models_by_model_id)
    assert client.project.deselect_all_models(project_id=test_project.id)


@pytest.mark.dependency
def test_select_and_connect_models(
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


@pytest.mark.dependency(depends=["test_select_and_connect_models"])
def test_update_simulation_parameters(
    client: PyStclient,
    test_project: ProjectInformation,
) -> None:
    var = ModelVariable(
        name="absTolerance",
        initial_value=1.5,
    )
    model_params = ModelParameters(name="Mass1", step_size=0.3, parameters=[var])
    sim_params = SimulationParameters(
        model_parameters=[model_params],
        base_step_size=0.05,
        end_time=20,
    )
    assert client.project.update_parameters(test_project.id, sim_params)

    parameter_names = client.project.parameter_names(test_project.id)
    assert len(parameter_names) == 1
    assert parameter_names[0] == "Config 1"

    params = client.project.parameter(test_project.id, parameter_names[0])
    assert params.config_name == "Config 1"
    assert params.base_step_size == 0.05
    assert params.end_time == 20
    assert params.model_parameters is not None
    assert params.model_parameters[0].name == "Mass1"
    assert params.model_parameters[0].step_size == 0.3
    assert params.model_parameters[0].variables is not None
    assert params.model_parameters[0].variables[0].name == "absTolerance"
    assert params.model_parameters[0].variables[0].type == FmuVariableTypeEnum.REAL
    assert params.model_parameters[0].variables[0].initial_value == 1.5


@pytest.mark.dependency(depends=["test_select_and_connect_models"])
def test_update_multiple_simulation_parameters_at_once(
    client: PyStclient,
    test_project: ProjectInformation,
) -> None:
    var = ModelVariable(
        name="absTolerance",
        initial_value=1.5,
    )
    var2 = ModelVariable(
        name="dampingCoefficient",
        initial_value=1,
    )
    model_params = ModelParameters(name="Mass1", step_size=0.3, parameters=[var])
    model_params2 = ModelParameters(name="Damper1", step_size=0.3, parameters=[var, var2])
    sim_params = SimulationParameters(
        config_name="Config 1",
        model_parameters=[model_params],
        base_step_size=0.05,
        end_time=20,
    )

    sim_params2 = SimulationParameters(
        config_name="Config 2",
        model_parameters=[model_params, model_params2],
        base_step_size=0.05,
        end_time=22,
    )

    assert client.project.update_parameters(test_project.id, sim_params, sim_params2)
    params = client.project.parameters(test_project.id)
    assert len(params) == 2
    assert params[0].config_name == "Config 1"
    assert params[1].config_name == "Config 2"

    param = params[0]
    assert param.config_name == "Config 1"
    assert param.base_step_size == 0.05
    assert param.end_time == 20
    assert param.model_parameters is not None
    assert param.model_parameters[0].name == "Mass1"
    assert param.model_parameters[0].step_size == 0.3
    assert param.model_parameters[0].variables is not None
    assert param.model_parameters[0].variables[0].name == "absTolerance"
    assert param.model_parameters[0].variables[0].type == FmuVariableTypeEnum.REAL
    assert param.model_parameters[0].variables[0].initial_value == 1.5

    param = params[1]
    assert param.config_name == "Config 2"
    assert param.base_step_size == 0.05
    assert param.end_time == 22
    assert param.model_parameters is not None
    assert param.model_parameters[0].name == "Mass1"
    assert param.model_parameters[0].step_size == 0.3
    assert param.model_parameters[0].variables is not None
    assert param.model_parameters[0].variables[0].name == "absTolerance"
    assert param.model_parameters[0].variables[0].type == FmuVariableTypeEnum.REAL
    assert param.model_parameters[0].variables[0].initial_value == 1.5
    assert param.model_parameters[1].name == "Damper1"
    assert param.model_parameters[1].step_size == 0.3
    assert param.model_parameters[1].variables is not None
    assert param.model_parameters[1].variables[1].name == "dampingCoefficient"
    assert param.model_parameters[1].variables[1].type == FmuVariableTypeEnum.REAL
    assert param.model_parameters[1].variables[1].initial_value == 1


@pytest.mark.dependency(depends=["test_select_and_connect_models"])
def test_update_multiple_simulation_parameters_one_by_one(
    client: PyStclient,
    test_project: ProjectInformation,
) -> None:
    var = ModelVariable(
        name="absTolerance",
        initial_value=1.5,
    )
    var2 = ModelVariable(
        name="dampingCoefficient",
        initial_value=1,
    )
    model_params = ModelParameters(name="Mass1", step_size=0.3, parameters=[var])
    model_params2 = ModelParameters(name="Damper1", step_size=0.3, parameters=[var, var2])
    sim_params3 = SimulationParameters(
        config_name="Config 3",
        model_parameters=[model_params],
        base_step_size=0.05,
        end_time=20,
    )

    sim_params4 = SimulationParameters(
        config_name="Config 4",
        model_parameters=[model_params, model_params2],
        base_step_size=0.05,
        end_time=22,
    )

    assert client.project.update_parameters(test_project.id, sim_params3)
    assert client.project.update_parameters(test_project.id, sim_params4)

    config3 = client.project.parameter(test_project.id, "Config 3")
    assert config3.config_name == "Config 3"
    assert config3.base_step_size == 0.05
    assert config3.end_time == 20
    assert config3.model_parameters is not None
    assert config3.model_parameters[0].name == "Mass1"
    assert config3.model_parameters[0].step_size == 0.3
    assert config3.model_parameters[0].variables is not None
    assert config3.model_parameters[0].variables[0].name == "absTolerance"
    assert config3.model_parameters[0].variables[0].type == FmuVariableTypeEnum.REAL
    assert config3.model_parameters[0].variables[0].initial_value == 1.5

    config4 = client.project.parameter(test_project.id, "Config 4")
    assert config4.config_name == "Config 4"
    assert config4.base_step_size == 0.05
    assert config4.end_time == 22
    assert config4.model_parameters is not None
    assert config4.model_parameters[0].name == "Mass1"
    assert config4.model_parameters[0].step_size == 0.3
    assert config4.model_parameters[0].variables is not None
    assert config4.model_parameters[0].variables[0].name == "absTolerance"
    assert config4.model_parameters[0].variables[0].type == FmuVariableTypeEnum.REAL
    assert config4.model_parameters[0].variables[0].initial_value == 1.5
    assert config4.model_parameters[1].name == "Damper1"
    assert config4.model_parameters[1].step_size == 0.3
    assert config4.model_parameters[1].variables is not None
    assert config4.model_parameters[1].variables[1].name == "dampingCoefficient"
    assert config4.model_parameters[1].variables[1].type == FmuVariableTypeEnum.REAL
    assert config4.model_parameters[1].variables[1].initial_value == 1


def test_delete_parameter_sets(
    client: PyStclient,
    test_project: ProjectInformation,
) -> None:
    def reset_params():
        var = ModelVariable(
            name="absTolerance",
            initial_value=1.5,
        )
        model_params = ModelParameters(name="Mass1", step_size=0.3, parameters=[var])
        _params = [
            SimulationParameters(
                config_name=f"Config {x}",
                model_parameters=[model_params],
                base_step_size=0.05,
                end_time=20,
            )
            for x in range(1, 4)
        ]
        assert client.project.update_parameters(test_project.id, *_params)

    reset_params()

    assert client.project.delete_parameters(test_project.id, "Config 3", "Config 4")
    assert set(client.project.parameter_names(test_project.id)) == {"Config 1", "Config 2"}

    assert client.project.delete_parameters(test_project.id, "Config 1", "Config 2")
    params = client.project.parameters(test_project.id)
    assert not params

    reset_params()
    assert client.project.delete_parameters(test_project.id)
    assert not params
