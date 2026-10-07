from types import SimpleNamespace

import pytest

from src.models.experiments import ScenarioSpec
from src.simulation.carla_scenarios import LaneChanges, same_direction_driving


def test_highway_requires_supported_map():
    with pytest.raises(ValueError, match="requires Town04"):
        ScenarioSpec(map="Town01", route_kind="highway")
    assert ScenarioSpec(map="Town04", route_kind="highway").route_kind == "highway"


def test_opposite_direction_or_other_road_is_not_a_lane_change_target():
    carla = SimpleNamespace(LaneType=SimpleNamespace(Driving="driving"))
    origin = SimpleNamespace(road_id=45, lane_id=-2)
    same = SimpleNamespace(road_id=45, lane_id=-1, lane_type="driving")
    opposite = SimpleNamespace(road_id=45, lane_id=1, lane_type="driving")
    other_road = SimpleNamespace(road_id=44, lane_id=-1, lane_type="driving")
    assert same_direction_driving(origin, same, carla)
    assert not same_direction_driving(origin, opposite, carla)
    assert not same_direction_driving(origin, other_road, carla)


def test_observed_lane_change_is_separate_from_requested_change():
    adjacent = SimpleNamespace(road_id=45, lane_id=-1, lane_type="driving")
    waypoint = SimpleNamespace(road_id=45, lane_id=-2, lane_change=1, is_junction=False,
                              get_left_lane=lambda: adjacent, get_right_lane=lambda: None)
    actor = SimpleNamespace(id=7, get_location=lambda: None,
                            get_velocity=lambda: SimpleNamespace(x=10, y=0, z=0))
    road_map = SimpleNamespace(get_waypoint=lambda location: waypoint)
    requests = []
    manager = SimpleNamespace(force_lane_change=lambda vehicle, right: requests.append(right))
    carla = SimpleNamespace(LaneType=SimpleNamespace(Driving="driving"),
                            LaneChange=SimpleNamespace(Left=1, Right=2))
    tracking = LaneChanges([actor], road_map, manager, 2.5, carla)
    tracking.tick(0)
    tracking.tick(2.5)
    assert len(tracking.requests) == 1 and len(tracking.observed) == 0
    waypoint.lane_id = -1
    tracking.tick(3)
    assert tracking.observed[0]["from_lane"] == -2
    assert tracking.observed[0]["to_lane"] == -1
