<div align="center">

<img src="https://media.luminis-sim.com/media/challenge/posters/robodojo_logo.png"></img>

<h2 align="center">RoboDojo: A Unified Sim-and-Real Benchmark for Comprehensive Evaluation of Generalist Robot Manipulation Policies</h2>

<h2 align="center"><a href="https://robodojo-benchmark.com/">Webpage</a> | <a href="https://robodojo-benchmark.com/doc/">Document</a> | <a href="https://arxiv.org/abs/2607.04434">Paper</a> | <a href="https://robodojo-benchmark.com/community">Community</a> | <a href="https://robodojo-benchmark.com/leaderboard">Leaderboard</a></h2>

</div>

https://private-user-images.githubusercontent.com/88101805/619409345-cc074c5d-4567-4418-8a29-1385aaba9d5b.mp4

## 本机 `.venv` 配置

当前环境已配置完成，可直接执行下方“检查与运行”命令。以下为本机最小重建步骤，
依赖已有的 `/data/NTU_slab/draven/anaconda3/envs/RoboDojo` 环境，请保留它。
该环境提供 Python 3.11、Isaac Sim 5.1 和 PyTorch 2.7.0+cu128，避免重复安装大型依赖。

1. 创建仿真环境，并安装当前仓库的 IsaacLab、CuRobo：

   ```bash
   cd third_party/RoboDojo  # 从 codebase 根目录执行
   git submodule update --init
   uv venv .venv --system-site-packages --seed \
     --python /data/NTU_slab/draven/anaconda3/envs/RoboDojo/bin/python
   source scripts/activate_venv.sh
   uv pip install --python .venv/bin/python 'packaging==23.0' 'wheel==0.45.1'
   for pkg in third_party/IsaacLab/source/* third_party/curobo; do
     python -m pip install --no-deps --no-build-isolation --ignore-installed -e "$pkg"
   done
   ```

   当前工作区已适配 `.venv` 启动，并将 IsaacLab 的 Starlette 依赖改为 `0.45.3`，
   以兼容 Isaac Sim；重建时需保留这些修改。激活脚本同时配置导入路径和无界面渲染。

2. 创建示例策略环境，隔离 WebSockets 版本冲突（仿真器要求 12，策略服务端要求 ≥14）：

   ```bash
   uv venv .venv/policy-server --python .venv/bin/python
   uv pip install --python .venv/policy-server/bin/python \
     -r XPolicyLab/pyproject.toml 'numpy==1.26.0' \
     'opencv-python-headless==4.11.0.86' 'websockets==15.0.1'
   ```

3. 下载仿真资产并生成机器人路径配置（需安装 Git LFS，已有完整资产可跳过下载）：

   ```bash
   bash scripts/init_assets.sh
   python utils/update_embodiment_config_path.py
   ```

检查与运行（在 `third_party/RoboDojo` 目录下）：

```bash
source scripts/activate_venv.sh
python -m pip check
bash scripts/robodojo.sh doctor --skip-policy
bash scripts/robodojo.sh benchmark \
  --policy-dir XPolicyLab/policy/demo_policy \
  --ckpt demo --policy-env "$PWD/.venv/policy-server" \
  --action-type joint --only stack_bowls --eval-num 1
```

已验证全部 15,365 个资产文件完整，GPU 运算、物理步进、相机渲染及 `stack_bowls`
单轮评测通过。示例策略无需权重，只输出零动作，成功率为 0 属正常结果。
正式评测时替换策略目录、权重和策略环境；配置记录见 `.cache/setup/setup-summary.json`，
验证结果见 `smoke_results/venv_validation_final.json`。

## News

- **September 16–17, 2026**
  - Fixed a single-frame discrepancy in `get_obs` and updated both the code and Hugging Face data. Rerunning evaluations across multiple models showed that the experimental results remain essentially unchanged.
  - Together with RoboTwin, fixed the channel ordering of the RGB data byte stream to keep both projects consistent. Please use this update with XPolicyLab commit [`bb9a0b5`](https://github.com/XPolicyLab/XPolicyLab/commit/bb9a0b5f5136a74503b679af830bfd0a3a837d5c) or later.
  - Updated the simulation assets for the `swap_T` task to make the objects less prone to slipping.
- **July 6, 2026** — Released the [RoboDojo paper](https://arxiv.org/abs/2607.04434) and open-sourced the code.

## ✨ Highlights

<p align="center">
  <img src="https://media.luminis-sim.com/media/home/teaser.png" width="70%"></img>
</p>

<p align="center"><em>Overview of RoboDojo. RoboDojo unifies efficient simulation evaluation and reproducible real-world testing for generalist robot manipulation, covering 42 simulation tasks, 18 real-world tasks, heterogeneous parallel simulation, RoboDojo-RealEval, XPolicyLab, and a continuously updated leaderboard.</em></p>

> RoboDojo is **eval-only** in this release: it provides the simulator client, benchmark tasks, asset/config validation, and result artifacts. Policy integration and policy servers are owned by [XPolicyLab](https://github.com/XPolicyLab/XPolicyLab/blob/main/README.md).

- 🌐 **Unified sim-and-real benchmark** — 42 simulation tasks and 18 real-world tasks across 3 robot embodiments for generalist robot manipulation.
- 🧭 **Five capability dimensions** — Generalization, Memory, Precision, Long-Horizon, and Open, designed to probe different skills rather than simple object or layout reskins.
- 🧗 **Challenging by design** — intentionally hard, diverse, long-horizon tasks that expose failures hidden by simpler benchmarks.
- ⚡ **Heterogeneous parallel simulation** — runs different tasks, scenes, and processes concurrently on Isaac Sim for fast, scalable feedback.
- 🧱 **Physically grounded assets** — rigid, articulated, and deformable objects in a single configuration-driven scene.
- 🤖 **Integrate once, evaluate everywhere** — [XPolicyLab](https://github.com/XPolicyLab/XPolicyLab/blob/main/README.md) unifies 40+ policies behind one interface for both simulation and real-world runs.
- 📊 **Reproducible & leaderboard-ready** — seed-controlled layouts and one-command `summarize` aggregation into a leaderboard table.

## 📚 Documentation

The [RoboDojo documentation](https://robodojo-benchmark.com/doc/) is the canonical reference. Key sections:

| Section | Description |
| :-- | :-- |
| [Usage Overview](https://robodojo-benchmark.com/doc/usage/) | End-to-end walkthrough of the evaluation workflow. |
| [Installation & Downloading (Assets and Data)](https://robodojo-benchmark.com/doc/usage/install-and-download/) | Environment setup and downloading robot/object/layout assets/training data. |
| [Quick Evaluation](https://robodojo-benchmark.com/doc/usage/quick-evaluation/) | Quickly dispatch XPolicyLab to run a policy for testing. |
| [XPolicyLab](https://robodojo-benchmark.com/doc/usage/xpolicylab/) | Integrates a large collection of policies and defines how to integrate new ones. |
| [Simulation Tasks Details](https://robodojo-benchmark.com/doc/sim-tasks/) | The 42 Isaac Sim tasks across five capability dimensions. |
| [Real Robot Tasks Details](https://robodojo-benchmark.com/doc/real-tasks/) | The 18 real-world tasks on Piper X, Piper, and ARX X5. |
| [Configurations](https://robodojo-benchmark.com/doc/usage/configurations/) | Simulator, scene, robot, and camera configuration options. |
| [Common Issues](https://robodojo-benchmark.com/doc/common-issue/) | Troubleshooting for installation, assets, GPU memory, and evaluation. |

## 🗂️ Repository Structure

```text
env/                   simulator backbone and managers
env_cfg/               simulator, scene, robot, and camera configs
task/RoboDojo/         task logic and task YAML configs
scripts/robodojo.sh    public RoboDojo-side eval entry
scripts/eval_policy.sh simulator client launched by XPolicyLab eval.sh
XPolicyLab/            policy server and policy integrations
Assets/                downloaded robot, object, material, and layout assets
```

## 🔌 Policy Integration

Policies live in [XPolicyLab](https://github.com/XPolicyLab/XPolicyLab/blob/main/README.md), which owns policy structure, dependencies, checkpoint layout, and server behavior. RoboDojo only assumes a policy directory provides:

```text
XPolicyLab/policy/<POLICY_NAME>/eval.sh
XPolicyLab/policy/<POLICY_NAME>/deploy.yml
```

`eval.sh` starts the policy server and calls back into RoboDojo through `scripts/eval_policy.sh`; `deploy.yml` declares the server host, port, action mode, and policy-specific runtime settings.

## 🏆 Leaderboard

View live rankings on the [RoboDojo Leaderboard](https://robodojo-benchmark.com/leaderboard).

**Simulation.** The full evaluation stack is open source, so you can debug locally and iterate on scores. Official RoboDojo-endorsed listings are submitted through the cloud evaluation pipeline with anti-cheating verification.

**Real world.** Real-robot leaderboard entries are accepted through the same cloud evaluation process; see the public documentation for protocol, rules, and submission details.

## 📝 Citation

```bibtex
% RoboDojo
@article{chen2026robodojo,
  title={{RoboDojo}: A Unified Sim-and-Real Benchmark for Comprehensive Evaluation of Generalist Robot Manipulation Policies},
  author={Chen, Tianxing and Chen, Yue and Li, Zixuan and Tang, Junyuan and Su, Kailun and Wan, Weijie and Chen, Baijun and Lu, Haoran and Yan, Haowen and Su, Honghao and others},
  journal={arXiv preprint arXiv:2607.04434},
  year={2026}
}

% XPolicyLab
@article{community2026xpolicylab,
  title={{XPolicyLab}: A Unified Standard and Open Ecosystem for Robot Policy Evaluation and Deployment},
  author={Community, XPolicyLab and Chen, Tianxing and Chen, Yue and Nian, Tian and Cai, Zijian and Chen, Guangyu and Lin, Wenwei and Liang, Qiwei and Xiang, Peicheng and Su, Kailun and others},
  journal={arXiv preprint arXiv:2608.09892},
  year={2026}
}
```

## 🙏 Acknowledgements

RoboDojo builds on [Isaac Sim](https://developer.nvidia.com/isaac/sim), [IsaacLab](https://github.com/isaac-sim/IsaacLab), [IsaacLab-Arena](https://github.com/isaac-sim/IsaacLab-Arena), [RoboTwin 2.0](https://github.com/robotwin-Platform/robotwin), [XPolicyLab](https://github.com/XPolicyLab/XPolicyLab), and [MagicSim](https://arxiv.org/abs/2606.17511). We thank the authors and maintainers for their open-source contributions to the robotics community.

Contact [Tianxing Chen](https://tianxingchen.github.io/) or [Yue Chen](https://yuechen0614.github.io/) if you have questions or suggestions.

## 🏫 Affiliations

RoboDojo is operated by **AI MMLab Club**, a non-profit, vendor-neutral organization, and is jointly maintained and supported by a global consortium of academic institutional partners. To preserve the fairness, neutrality, and independence of the official evaluation, RoboDojo does not involve commercial companies in its governance, operation, funding, sponsorship, compute, hardware, or other forms of project support. For inquiries from academic or non-profit partners regarding project collaboration or resource support, please contact [RoboDojoCommittee@gmail.com](mailto:RoboDojoCommittee@gmail.com).

<img src="https://media.luminis-sim.com/media/home/partners/affiliations.png"></img>

## ⚖️ License

Released under the [MIT License](LICENSE).


<p align="center">
  <img alt="Python 3.11" src="https://img.shields.io/badge/Python-3.11-475569?style=flat-square&logo=python&logoColor=white&labelColor=64748b" height="22"/>&nbsp;
  <img alt="Isaac Sim 5.1" src="https://img.shields.io/badge/Isaac_Sim-5.1-475569?style=flat-square&logo=nvidia&logoColor=76B900&labelColor=64748b" height="22"/>&nbsp;
  <img alt="Isaac Lab 2.3" src="https://img.shields.io/badge/Isaac_Lab-2.3-475569?style=flat-square&logo=nvidia&logoColor=76B900&labelColor=64748b" height="22"/>&nbsp;
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-475569?style=flat-square&labelColor=64748b" height="22"/>
</p>
