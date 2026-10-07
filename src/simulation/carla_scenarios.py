"""Python 3.7 compatible highway placement and observed lane-change telemetry."""

import math


def same_direction_driving(origin, other, carla):
    return (other is not None and other.lane_type == carla.LaneType.Driving
            and origin.lane_id * other.lane_id > 0 and origin.road_id == other.road_id)


def driving_lane_count(waypoint, carla):
    count = 1
    for method in ("get_left_lane", "get_right_lane"):
        adjacent = getattr(waypoint, method)()
        for _ in range(8):
            if not same_direction_driving(waypoint, adjacent, carla):
                break
            count += 1
            adjacent = getattr(adjacent, method)()
    return count


def highway_placement(road_map, index, carla):
    points = road_map.generate_waypoints(16)
    lengths = {}
    for point in points:
        lengths[point.road_id] = max(lengths.get(point.road_id, 0), point.s)
    candidates = []
    for spawn_index, transform in enumerate(road_map.get_spawn_points()):
        waypoint = road_map.get_waypoint(transform.location)
        if (not waypoint.is_junction and driving_lane_count(waypoint, carla) >= 3
                and lengths[waypoint.road_id] >= 300):
            candidates.append((spawn_index, waypoint))
    if index >= len(candidates):
        raise ValueError("Highway route index is outside verified multilane spawn candidates")
    spawn_index, origin = candidates[index]
    lane_points = [p for p in points if p.road_id == origin.road_id and p.lane_id == origin.lane_id
                   and not p.is_junction and driving_lane_count(p, carla) >= 3]
    anchor = min(lane_points, key=lambda p: abs(p.s - lengths[origin.road_id] * 0.4))
    nearby = [p for p in points if same_direction_driving(anchor, p, carla) and not p.is_junction
              and abs(p.s - anchor.s) <= 110
              and p.transform.location.distance(anchor.transform.location) >= 12]
    nearby.sort(key=lambda p: (p.transform.location.distance(anchor.transform.location), p.lane_id, p.s))

    def transform(point):
        pose = point.transform
        pose.location.z += 0.5
        return pose

    return transform(anchor), [transform(p) for p in nearby], {
        "policy": "Town04 non-junction road >=300m with >=3 same-direction driving lanes",
        "original_spawn_index": spawn_index, "road_id": anchor.road_id,
        "lane_id": anchor.lane_id, "s": anchor.s,
        "same_direction_lanes": driving_lane_count(anchor, carla),
        "road_length_m": lengths[anchor.road_id],
    }


class LaneChanges:
    def __init__(self, actors, road_map, manager, interval, carla):
        self.actors, self.map, self.manager = actors, road_map, manager
        self.interval, self.carla = interval, carla
        self.requests, self.observed, self.previous = [], [], {}
        self.next_request = interval
        self.pending = {}

    def tick(self, elapsed):
        current = {}
        for actor in self.actors:
            waypoint = self.map.get_waypoint(actor.get_location())
            key = (waypoint.road_id, waypoint.lane_id)
            old = self.previous.get(actor.id)
            if old is not None and old[0] == key[0] and old[1] != key[1]:
                self.observed.append({"time": elapsed, "actor_id": actor.id,
                                      "road_id": key[0], "from_lane": old[1], "to_lane": key[1]})
            self.previous[actor.id] = key
            current[actor.id] = waypoint
        if elapsed < self.next_request:
            return
        self.next_request += self.interval
        for actor in self.actors:
            waypoint = current[actor.id]
            velocity = actor.get_velocity()
            speed = math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)
            if waypoint.is_junction or speed < 2:
                continue
            pending = self.pending.get(actor.id)
            if pending and (waypoint.road_id, waypoint.lane_id) != pending[0] and elapsed - pending[1] < 2*self.interval:
                continue
            sides = [(False, "get_left_lane", self.carla.LaneChange.Left),
                     (True, "get_right_lane", self.carla.LaneChange.Right)]
            if len([r for r in self.requests if r["actor_id"] == actor.id]) % 2:
                sides.reverse()
            for right, method, permission in sides:
                adjacent = getattr(waypoint, method)()
                if (same_direction_driving(waypoint, adjacent, self.carla)
                        and int(waypoint.lane_change) & int(permission)):
                    self.manager.force_lane_change(actor, right)
                    self.pending[actor.id] = ((adjacent.road_id, adjacent.lane_id), elapsed)
                    self.requests.append({"time": elapsed, "actor_id": actor.id,
                                          "road_id": waypoint.road_id, "from_lane": waypoint.lane_id,
                                          "target_lane": adjacent.lane_id, "right": right})
                    break
