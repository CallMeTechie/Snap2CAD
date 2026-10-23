import math

import pytest

from app import geom


def test_length_with_factors():
    assert geom.compute("length", [[0, 0], [100, 0]]) == 100
    assert geom.compute("length", [[0, 0], [100, 0]], fx=0.995) == pytest.approx(99.5)
    assert geom.compute("length", [[0, 0], [0, 50]], fy=1.01) == pytest.approx(50.5)


def test_circle():
    pts = [[10, 0], [0, 10], [-10, 0]]
    assert geom.compute("diameter", pts) == pytest.approx(20)
    assert geom.compute("radius", pts) == pytest.approx(10)
    assert geom.compute("diameter", [[0, 0], [1, 1], [2, 2]]) is None  # kollinear


def test_angle():
    assert geom.compute("angle", [[10, 0], [0, 0], [0, 10]]) == pytest.approx(90)
    v = geom.compute("angle", [[10, 0], [0, 0], [10, 10]])
    assert v == pytest.approx(45)


def test_not_enough_points():
    assert geom.compute("length", [[0, 0]]) is None
    assert not math.isnan(geom.compute("height", [[0, 0], [0, 3]]))


def test_factors():
    assert geom.factors({"ctrl_x": 99.5}, 100.0, 230) == (0.995, 0.995)
    fx, fy = geom.factors({"ctrl_x": 100.2, "ctrl_y": 229.0}, 100.0, 230)
    assert fx == pytest.approx(1.002) and fy == pytest.approx(229 / 230)
    assert geom.factors({"ctrl_x": 49.8}, 50.0, 80) == (pytest.approx(0.996), pytest.approx(0.996))
    assert geom.factors({"ctrl_x": 99.8}, 50.0, 80) == (1.0, 1.0)
    assert geom.factors({"ctrl_x": 49.9, "ctrl_y": 229.0}, 50.0, 80) == (pytest.approx(0.998), pytest.approx(0.998))
    assert geom.ctrl_stale({"ctrl_x": 99.8}, 50.0, 80) and not geom.ctrl_stale({"ctrl_x": 49.8}, 50.0, 80) \
        and not geom.ctrl_stale({}, 100.0, 230)
