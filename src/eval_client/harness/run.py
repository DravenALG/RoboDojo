"""Run one task against a harness; process recovery belongs to the batch launcher.

Launch from the RoboDojo root with its Python environment. No parent codebase
imports are required, avoiding the two projects' identically named src packages.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "XPolicyLab"))


class InvalidLayout(Exception):
    """Ask the supervisor for a clean simulator without consuming a retry."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=6000)
    parser.add_argument("--episode-length-scale", type=float, default=1.)
    parser.add_argument("--seed", type=int, default=0)
    from isaaclab.app import AppLauncher
    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args()
    if args.runs <= 0 or not math.isfinite(args.episode_length_scale) or args.episode_length_scale <= 0:
        parser.error("runs and episode-length-scale must be positive")
    manifest = json.loads(args.manifest.read_text())
    layouts = manifest["layouts"][args.task]
    from src.eval_client.harness.state import EpisodeStore, atomic_json
    store = EpisodeStore(args.output, args.task, args.runs, layouts)
    if not store.pending():
        return

    # Share the native monitor and rendering synchronization, but let the
    # supervisor retry the entire uncommitted episode after fatal failures.
    from src.eval_client.physx_warning_monitor import get_monitor, PhysXBrokenError
    monitor = get_monitor()
    monitor.start(enabled=True)
    from env.camera_manager.capture.render_sync import add_zero_delay_kit_args
    add_zero_delay_kit_args(args)
    app = AppLauncher(args).app
    env = None
    try:
        from omegaconf import OmegaConf
        from utils.load_file import load_yaml
        from utils.pipeline_utils import process_config, process_randomization
        from utils.cluttered_generator import UnStableError
        from task.RoboDojo.task_registry import task_config_path
        from src.eval_client.eval_env import create_eval_env
        from src.eval_client.harness.client import HarnessClient, rollout

        cfg_root = ROOT / "env_cfg"
        evaluation = load_yaml(str(cfg_root / "arx_x5.yml"))
        evaluation.update(task_name=args.task, num_envs=1, device_id=0, eval_batch=False,
                          policy_name="harness", additional_info="", seed=args.seed,
                          eval_num=args.runs, physx_monitor_enabled=True,
                          output_dir=str(args.output / "native"))
        config = OmegaConf.create({
            **{section: load_yaml(str(cfg_root / section / (evaluation["config"][section] + ".yml")))
               for section in ("sim", "scene", "robot", "camera")},
            "task_env": load_yaml(str(task_config_path(ROOT / "task/RoboDojo/config", args.task))),
            "eval_cfg": evaluation,
            "deploy_cfg": dict(policy_name="harness", host=args.host, port=args.port),
        })
        config = process_randomization(config)
        config, _ = process_config(config, args.task)
        config.sim.scene.num_envs = 1
        # Preserve the native physics device (CPU by default). The renderer
        # and IK use the selected visible GPU; native reward code expects CPU
        # tensor views and cannot run unchanged on a forced CUDA physics device.
        config.sim.seed = [0]
        config.camera.default_frequency = evaluation["observation"]["collect_freq"]
        rows = [store.records[i] for i in sorted(store.records)]
        resume = dict(save_dir=str(args.output / "native"),
                      success_nums=sum(r["success"] for r in rows),
                      fail_nums=sum(not r["success"] for r in rows),
                      total_score=sum(r["score"] for r in rows),
                      details={i: {k: row[k] for k in ("layout_id", "success", "score")}
                               for i, row in enumerate(rows)})
        current = {}

        def commit(native):
            if 0 in native.unstable_envs:
                return
            detail = native.eval_result["details"][max(native.eval_result["details"])]
            store.commit(current["episode"], {
                **detail, **native.model_client.last_episode,
                "wall_seconds": time.monotonic() - current["started"],
                "video_dir": str(args.output / "native"),
            })

        env = create_eval_env(config, app, resume_state=resume,
                              client_factory=lambda url: HarnessClient(url, timeout=args.timeout),
                              episode_runner=rollout, result_callback=commit)
        actual_layouts = [str(Path(env.seed_manager.seed_info[i]["scene_layout"]).resolve())
                          for i in sorted(env.seed_manager.seed_info)]
        if actual_layouts != layouts:
            raise ValueError("Native layout inventory differs from the saved batch manifest")
        native_limit = int(env.step_lim)
        for episode in store.pending():
            while episode not in store.records:
                selected = store.assignment(episode)
                current.update(episode=episode, started=time.monotonic())
                monitor.reset()
                try:
                    env.reset(seed=[selected["layout_id"]])
                    env.step_lim = max(1, math.ceil(native_limit * args.episode_length_scale))
                    env.run_eval()
                    if 0 in env.unstable_envs:
                        store.invalidate(episode, "native unstable episode")
                    elif episode not in store.records:
                        raise RuntimeError("Native rollout exited without committing an episode")
                except (UnStableError, PhysXBrokenError) as error:
                    store.invalidate(episode, str(error))
                    # Restart the process after broken physics. The replacement
                    # is persisted, so a retry cannot reuse the rejected layout.
                    raise InvalidLayout(f"Invalid layout; replacement required: {error}") from error
                if env.model_client.last_episode.get("error_kind"):
                    # Malformed responses may leave the protocol connection unusable.
                    # The committed failure stays committed when the supervisor restarts.
                    return
    except BaseException as error:
        # Kit's default fast shutdown exits the process with status 0, even
        # while a Python exception is unwinding. Publish the traceback first
        # and preserve the supervisor's recovery status in a fresh process.
        import traceback
        trace = traceback.format_exc()
        atomic_json(args.output / "failures" / f"{time.time_ns()}.json",
                    dict(error_type=type(error).__name__, error=str(error), traceback=trace))
        # The PhysX monitor forwards stderr on a background thread. Persist the
        # full error independently so immediate process exit cannot lose it.
        print(trace, file=sys.stderr, flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(75 if isinstance(error, InvalidLayout) else 130 if isinstance(error, KeyboardInterrupt) else 1)
    finally:
        try:
            if env is not None:
                env.close()
        finally:
            app.close()


if __name__ == "__main__":
    try:
        main()
    except InvalidLayout as error:
        print(str(error), file=sys.stderr, flush=True)
        sys.exit(75)
