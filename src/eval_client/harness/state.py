"""Durable, GPU-independent episode identities. Standard library only.

An atomically published episodes/<index>.json is the sole completion marker.
Videos, native exports, and in-progress assignments never commit an episode.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, allow_nan=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_records(directory, task, runs):
    records = {}
    for path in sorted((Path(directory) / "episodes").glob("*.json")):
        row = json.loads(path.read_text())
        index = row.get("episode")
        if (type(index) is not int or not 0 <= index < runs or row.get("env_name") != task
                or type(row.get("success")) is not bool or row.get("benchmark") != "robodojo"
                or path.stem != f"{index:07d}" or index in records):
            raise ValueError(f"Invalid or conflicting committed episode: {path}")
        score = row.get("score")
        if (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1
                or type(row.get("layout_id")) is not int or row["layout_id"] < 0
                or type(row.get("cycle")) is not int or row["cycle"] < 0):
            raise ValueError(f"Invalid committed score or layout identity: {path}")
        records[index] = row
    return records


class EpisodeStore:
    def __init__(self, directory, task, runs, layouts):
        self.directory, self.task, self.runs = Path(directory), task, runs
        if type(runs) is not int or runs <= 0 or not layouts:
            raise ValueError("Positive runs and at least one layout are required")
        self.layouts = layouts
        self.records = read_records(directory, task, runs)
        self.path = self.directory / "layout_state.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "schema_version": 1, "task": task, "runs": runs, "layouts": layouts,
            "cursor": 0, "assignments": {}, "invalid": {},
        }
        if (self.state.get("schema_version") != 1 or self.state.get("task") != task
                or self.state.get("runs") != runs or self.state.get("layouts") != layouts):
            raise ValueError("Saved task, runs or layout inventory changed")

    def pending(self):
        return [i for i in range(self.runs) if i not in self.records]

    def assignment(self, episode):
        if episode in self.records or not 0 <= episode < self.runs:
            raise ValueError("Episode is already committed or outside the plan")
        key = str(episode)
        if key not in self.state["assignments"]:
            for _ in self.layouts:
                cursor = self.state["cursor"]
                self.state["cursor"] += 1
                layout_id = cursor % len(self.layouts)
                if str(layout_id) not in self.state["invalid"]:
                    self.state["assignments"][key] = {
                        "layout_id": layout_id, "layout_file": self.layouts[layout_id],
                        "cycle": cursor // len(self.layouts),
                    }
                    atomic_json(self.path, self.state)
                    break
            else:
                atomic_json(self.path, self.state)
                raise RuntimeError(f"No valid layouts remain for {self.task}")
        selected = self.state["assignments"][key]
        atomic_json(self.directory / "active_episode.json", {"episode": episode, **selected})
        return selected

    def invalidate(self, episode, reason):
        selected = self.state["assignments"].pop(str(episode))
        self.state["invalid"][str(selected["layout_id"])] = dict(episode=episode, reason=str(reason), **selected)
        atomic_json(self.path, self.state)

    def commit(self, episode, result):
        if episode in self.records or (self.directory / "episodes" / f"{episode:07d}.json").exists():
            raise ValueError("Episode already committed")
        row = {**result, **self.state["assignments"][str(episode)],
               "benchmark": "robodojo", "policy": "harness", "env_id": 0,
               "env_name": self.task, "task_name": self.task, "episode": episode, "run": episode}
        atomic_json(self.directory / "episodes" / f"{episode:07d}.json", row)
        self.records[episode] = row
        return row
