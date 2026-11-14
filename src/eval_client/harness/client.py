"""NumPy msgpack/WebSocket harness client; imports no simulator or model code."""
from __future__ import annotations

import inspect
import math
from uuid import uuid4

import msgpack
import numpy as np
from PIL import Image
from websockets.sync.client import connect

ARMS = ("left", "right")
CAMERAS = ("cam_head", "cam_left_wrist", "cam_right_wrist")


class PolicyFailure(Exception):
    """A terminal model/protocol failure, never resampled."""


def pack_numpy(value):
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "VOc":
            raise ValueError("Unsupported array dtype")
        return {b"__ndarray__": True, b"data": value.tobytes(), b"dtype": value.dtype.str, b"shape": value.shape}
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot encode {type(value).__name__}")


def unpack_numpy(value):
    if b"__ndarray__" in value:
        return np.frombuffer(value[b"data"], dtype=value[b"dtype"]).reshape(value[b"shape"])
    if b"__npgeneric__" in value:
        return np.dtype(value[b"dtype"]).type(value[b"data"])
    return value


def extract_observation(raw, *, image_size, cameras):
    state, result = raw["state"], {}
    for arm in ARMS:
        pose = np.asarray(state[f"{arm}_ee_pose"], dtype=np.float32)
        joints = np.asarray(state[f"{arm}_arm_joint_state"], dtype=np.float32)
        opening = np.asarray(state[f"{arm}_ee_joint_state"], dtype=np.float32)
        if pose.shape != (7,) or joints.shape != (6,) or opening.shape != (1,):
            raise ValueError("Expected two X5 arms with 7D poses, 6 joints and scalar grippers")
        if not all(np.isfinite(a).all() for a in (pose, joints, opening)) or not 0 <= opening[0] <= 1:
            raise ValueError("Non-finite robot state or invalid gripper opening")
        norm = np.linalg.norm(pose[3:])
        if norm < 1e-8:
            raise ValueError("Observed quaternion has zero norm")
        result[arm] = dict(position=pose[:3].copy(), quaternion=pose[3:] / norm,
                           joint_positions=joints.copy(), gripper=float(1 - opening[0]))
    for camera in cameras:
        pixels = np.asarray(raw["vision"][camera]["color"])
        if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
            raise ValueError(f"{camera} must contain uint8 RGB pixels")
        image = Image.fromarray(pixels[:, :, :3])
        image.thumbnail((image_size, image_size), Image.Resampling.LANCZOS)
        result[camera] = np.asarray(image).copy()
    return result


def native_action(frame, *, joint):
    width = 7 if joint else 8
    result = {}
    for index, arm in enumerate(ARMS):
        row = frame[index * width:(index + 1) * width]
        result[f"{arm}_{'arm_joint_state' if joint else 'ee_pose'}"] = row[:-1].tolist()
        result[f"{arm}_ee_joint_state"] = [float(1 - row[-1])]
    return result


class HarnessClient:
    def __init__(self, url, *, timeout=6000):
        self.timeout = timeout
        options = dict(compression=None, max_size=None, open_timeout=30)
        if "proxy" in inspect.signature(connect).parameters:
            options["proxy"] = None
        self.connection = connect(url, **options)
        try:
            self.metadata = self._receive()
            m = self.metadata
            if (m.get("policy") != "harness" or m.get("benchmark") != "robodojo"
                    or m.get("protocol") != "robodojo_harness" or m.get("protocol_version") != 1
                    or m.get("robot") != "dual_x5" or m.get("arm_order") != list(ARMS)
                    or m.get("joint_dims") != [6, 6]):
                raise ValueError("Server does not implement the RoboDojo dual X5 harness protocol")
            self.action_format = m["action_format"]
            if self.action_format not in ("eef_absolute", "eef_delta", "joint_absolute", "joint_delta", "EEF_final"):
                raise ValueError("Unsupported action format")
            self.joint = self.action_format.startswith("joint_")
            self.width = 14 if self.joint else 16
            representation = ("robodojo_absolute_joint_position_closedness" if self.joint
                              else "robodojo_env_absolute_xyz_quat_wxyz_closedness")
            if m.get("action_dim") != self.width or m.get("action_representation") != representation:
                raise ValueError("Incompatible harness action representation")
            if m.get("views") not in ("single", "multi"):
                raise ValueError("Invalid camera view selection")
            self.cameras = (CAMERAS[0],) if m["views"] == "single" else CAMERAS
            if m.get("cameras") != list(self.cameras):
                raise ValueError("Incompatible camera metadata")
            self.image_size = m["image_size"]
            if type(self.image_size) is not int or self.image_size <= 0:
                raise ValueError("Invalid image_size")
        except BaseException:
            self.close()
            raise
        self.episode_id = None
        self.ended = True
        self.last_episode = {}

    def _receive(self):
        raw = self.connection.recv(timeout=self.timeout)
        if isinstance(raw, str):
            raise RuntimeError(f"Harness service failed: {raw}")
        try:
            value = msgpack.unpackb(raw, object_hook=unpack_numpy)
            if not isinstance(value, dict):
                raise ValueError("Response must be an object")
            return value
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            raise PolicyFailure(f"Invalid response: {error}") from error

    def _query(self, request):
        self.connection.send(msgpack.packb(request, default=pack_numpy))
        value = self._receive()
        if "error" in value:
            self.ended = True
            error = value["error"]
            if (value.get("episode_id") != self.episode_id or not isinstance(error, dict)
                    or error.get("kind") != "policy_execution"):
                raise PolicyFailure("Invalid harness error response")
            raise PolicyFailure(f"{error.get('type')}: {error.get('message')}")
        return value

    def reset(self):
        if not self.ended:
            raise RuntimeError("Previous episode has not ended")

    def begin(self, *, instruction, max_steps, control_dt):
        self.reset()
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("A nonempty native task instruction is required")
        if type(max_steps) is not int or max_steps < 1 or not math.isfinite(control_dt) or control_dt <= 0:
            raise ValueError("Invalid episode limits")
        self.episode_id = uuid4().hex
        self.instruction, self.max_steps, self.control_dt = instruction, max_steps, control_dt
        self.decision_step = 0
        self.ended = False
        self.last_episode = {"harness_episode_id": self.episode_id}

    def request(self, raw, control_step, *, reason=None):
        return dict(type="end_episode" if reason else "infer", episode_id=self.episode_id,
                    env_id=0, decision_step=self.decision_step, control_step=int(control_step),
                    instruction=self.instruction, max_steps=self.max_steps, control_dt=self.control_dt,
                    observation=extract_observation(raw, image_size=self.image_size, cameras=self.cameras),
                    **({"reason": reason} if reason else {}))

    def infer(self, raw, control_step):
        if self.ended:
            raise RuntimeError("Episode has ended")
        result = self._query(self.request(raw, control_step))
        try:
            actions = np.asarray(result["actions"], dtype=np.float32)
            if (actions.ndim != 2 or actions.shape[1] != self.width
                    or not 1 <= len(actions) <= self.max_steps - control_step or not np.isfinite(actions).all()):
                raise ValueError("Invalid action chunk dimensions or values")
            half = self.width // 2
            if not np.isin(actions[:, [half - 1, self.width - 1]], [0, 1]).all():
                raise ValueError("Grippers must be binary")
            if not self.joint:
                for start in (3, 11):
                    if not np.allclose(np.linalg.norm(actions[:, start:start + 4], axis=1), 1, atol=1e-4):
                        raise ValueError("Action quaternions must be normalized")
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self.ended = True
            raise PolicyFailure(str(error)) from error
        self.decision_step += 1
        return [native_action(frame, joint=self.joint) for frame in actions]

    def end(self, raw, control_step, reason):
        if self.ended:
            return
        try:
            if self.decision_step:
                result = self._query(self.request(raw, control_step, reason=reason))
                if result.get("ended") is not True:
                    raise PolicyFailure("Missing end_episode acknowledgement")
        finally:
            self.ended = True

    def close(self):
        self.connection.close()


def rollout(env, client):
    """Execute native control steps, including early termination inside a chunk."""
    raw = env.get_obs()
    client.begin(instruction=str(raw["instruction"]), max_steps=int(env.step_lim),
                 control_dt=float(env.dt * env.obs_manager.collect_interval))
    reason = "native_terminal"
    try:
        while not env.is_episode_end():
            for action in client.infer(raw, env.take_action_cnt[0]):
                env.take_action(action)
                if env.is_episode_end():
                    break
                # Preserve native video/camera capture at every control step.
                raw = env.get_obs()
            raw = env.get_obs_batch(env_idx_list=[0], last_frame=True)[0]
        if env.take_action_cnt[0] >= env.step_lim:
            reason = "time_limit"
        client.end(raw, env.take_action_cnt[0], reason)
    except PolicyFailure as error:
        reason = "execution_error"
        env.success[0], env.end_flag[0] = False, True
        client.last_episode.update(error_kind="policy_execution", error=str(error))
        client.ended = True
    client.last_episode.update(reason=reason, control_steps=int(env.take_action_cnt[0]))
