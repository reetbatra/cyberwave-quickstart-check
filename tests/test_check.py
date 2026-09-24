"""Tests run offline against the installed SDK. No network, no API key."""

import textwrap

from check import check, find_calls, python_blocks


def calls_for(*blocks: str):
    clients: set[str] = set()
    twins: set[str] = set()
    found = []
    for code in blocks:
        found.extend(find_calls("page", 1, textwrap.dedent(code), clients, twins))
    return found


def broken_attrs(*blocks: str) -> list[str]:
    return [r.call.attr for r in check(calls_for(*blocks)) if not r.ok]


def test_python_blocks_extracts_only_python_fences_with_page_line_numbers():
    markdown = "intro\n```bash\npip install cyberwave\n```\n```python theme={null}\ncw = 1\n```\n"
    assert python_blocks(markdown) == [(6, "cw = 1\n")]


def test_twins_called_like_a_function_is_broken():
    assert broken_attrs(
        """
        cw = Cyberwave()
        arm = cw.twins("the-robot-studio/so101")
        """
    ) == ["twins"]


def test_twin_singular_is_ok():
    assert broken_attrs(
        """
        cw = Cyberwave()
        arm = cw.twin("the-robot-studio/so101")
        """
    ) == []


def test_twins_manager_methods_are_ok():
    assert broken_attrs(
        """
        cw = Cyberwave()
        cw.twins.list()
        """
    ) == []


def test_set_joint_is_broken_and_joints_set_is_ok():
    assert broken_attrs(
        """
        cw = Cyberwave()
        arm = cw.twin("the-robot-studio/so101")
        arm.set_joint("1", 30)
        arm.joints.set("1", 30, degrees=True)
        """
    ) == ["set_joint"]


def test_use_controller_on_a_twin_is_broken():
    assert broken_attrs(
        """
        cw = Cyberwave()
        robot = cw.twin("unitree/go2")
        robot.use_controller("keyboard")
        robot.navigation.use_controller("policy-uuid")
        """
    ) == ["use_controller"]


def test_sensor_families_resolved_in_getattr_are_ok():
    assert broken_attrs(
        """
        cw = Cyberwave()
        robot = cw.twin("the-robot-studio/so101")
        robot.camera.read()
        """
    ) == []


def test_client_defined_in_an_earlier_block_carries_over():
    first = "cw = Cyberwave()\n"
    second = 'robot = cw.twins("unitree/go2")\nrobot.use_controller("keyboard")\n'
    assert broken_attrs(first, second) == ["twins", "use_controller"]


def test_unrelated_objects_are_ignored():
    assert calls_for("import math\nmath.radians(30)\n") == []
