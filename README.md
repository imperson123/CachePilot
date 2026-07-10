# CachePilot：基于 Mooncake 的 KVCache 复用与调度优化系统

> 2026 Mooncake 赛题参赛作品  
> 定位：**非侵入式** KVCache benchmark / evaluation 项目

---

## 项目简介

**CachePilot** 是一个基于 [Mooncake](https://github.com/kvcache-ai/Mooncake) 的非侵入式 KVCache 评测与调度实验系统。它**不修改 Mooncake 核心代码**，而是通过：

1. **包装** Mooncake 官方 `store_kv_bench.py`，复现 Store 读写性能；
2. **模拟** 长上下文 Prefix Cache 复用对 TTFT 的影响；
3. **模拟** 多节点 KVCache 检索调度策略（含 CachePilot 评分策略）；

形成一个可复现、可独立运行的实验流水线。

即使本机未启动 Mooncake 服务，Prefix Reuse 与 Scheduler 仿真仍可完整跑通并产出图表。

---

## 赛题对应关系

| 赛题关注点 | CachePilot 模块 | 说明 |
|-----------|-----------------|------|
| Mooncake Store 性能 | `mooncake_store_runner.py` | 调用官方 `store_kv_bench.py`，输出 req/s、MiB/s、延迟分位等 |
| KVCache 复用 | `prefix_reuse_benchmark.py` | 模拟不同 prefix 长度与 hit ratio 下的 TTFT 收益 |
| 检索 / 调度优化 | `retrieval_scheduler_sim.py` | 对比 Random / Nearest / Reuse-aware / CachePilot |
| 可复现实验 | `scripts/run_all.sh` + `results/` | 一键跑通并落盘 CSV / PNG / log |

---

## 系统模块

```
┌─────────────────────────────────────────────────────────┐
│                    CachePilot Pipeline                   │
├──────────────┬──────────────────┬───────────────────────┤
│ Store Bench  │  Prefix Reuse    │  Retrieval Scheduler  │
│ (官方包装)    │  (TTFT 仿真)      │  (策略对比仿真)         │
│              │                  │                       │
│ store_kv_    │  hit ratio ×     │  Random / Nearest /   │
│ bench.py     │  prefix length   │  Reuse-aware /        │
│              │  → TTFT 收益      │  CachePilot           │
└──────┬───────┴────────┬─────────┴───────────┬───────────┘
       │                │                     │
       ▼                ▼                     ▼
              results/csv + results/figures
                         │
                         ▼
                  plot_results.py
```

---

## 目录结构

```
CachePilot/
├── README.md
├── DESIGN.md
├── EVALUATION.md
├── requirements.txt
├── benchmark/
│   ├── __init__.py
│   ├── metrics.py
│   ├── mooncake_store_runner.py
│   ├── parse_store_output.py
│   ├── prefix_reuse_benchmark.py
│   ├── retrieval_scheduler_sim.py
│   └── plot_results.py
├── scripts/
│   ├── run_all.sh
│   ├── run_store_verify.sh
│   ├── run_store_perf.sh
│   ├── run_prefix_reuse.sh
│   ├── run_scheduler_sim.sh
│   └── plot_all.sh
└── results/
    ├── csv/
    ├── logs/
    └── figures/
```

---

## 安装方式

```bash
cd CachePilot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

依赖仅包含：`numpy`、`pandas`、`matplotlib`。

---

## 如何设置 MOONCAKE_ROOT

Store Benchmark **不模拟** Mooncake Store API，而是通过 subprocess 调用：

```
{MOONCAKE_ROOT}/mooncake-store/benchmarks/store_kv_bench.py
```

设置方式（任选其一）：

```bash
# 方式 1：环境变量
export MOONCAKE_ROOT=/path/to/Mooncake

# 方式 2：命令行参数
python benchmark/mooncake_store_runner.py --mooncake-root /path/to/Mooncake ...
```

若未指定，将按顺序自动尝试：

- `../Mooncake`
- `../../Mooncake`
- `/root/autodl-tmp/mooncake_competition/Mooncake`
- 环境变量 `MOONCAKE_ROOT`

找不到时会报错：

```text
Mooncake root not found. Please set --mooncake-root or MOONCAKE_ROOT.
```

在 `run_all.sh` 中（带 `--skip-on-fail`）该错误**不会中断**后续 Prefix / Scheduler / Plot 实验。

---

## 如何启动 Mooncake master

若要跑真实 Store Benchmark，需先启动 master（含 HTTP metadata）：

```bash
mooncake_master \
  --enable_http_metadata_server=true \
  --http_metadata_server_host=0.0.0.0 \
  --http_metadata_server_port=8080 \
  --eviction_high_watermark_ratio=0.95
```

默认连接参数与官方一致：

| 参数 | 默认值 |
|------|--------|
| local-hostname | `127.0.0.1:50071` |
| metadata-server | `http://127.0.0.1:8080/metadata` |
| master-server | `127.0.0.1:50051` |
| protocol | `tcp` |

---

## 如何运行

### 一键全流程（推荐）

```bash
bash scripts/run_all.sh
```

执行顺序：

1. 创建 `results/{csv,logs,figures}`
2. `run_store_verify.sh`（失败继续）
3. `run_store_perf.sh`（失败继续）
4. `run_prefix_reuse.sh`
5. `run_scheduler_sim.sh`
6. `plot_all.sh`
7. 打印生成的 CSV / PNG / log 路径

### 分步运行

```bash
bash scripts/run_store_verify.sh
bash scripts/run_store_perf.sh
bash scripts/run_prefix_reuse.sh
bash scripts/run_scheduler_sim.sh
bash scripts/plot_all.sh
```

---

## 输出文件说明

| 路径 | 说明 |
|------|------|
| `results/csv/store_benchmark.csv` | Store 官方 bench 解析结果（需 Mooncake 服务） |
| `results/csv/prefix_reuse.csv` | Prefix 复用 TTFT 仿真结果 |
| `results/csv/retrieval_scheduler.csv` | 调度策略汇总指标 |
| `results/logs/store_*.log` | 每次 Store 运行的原始 stdout/stderr |
| `results/logs/prefix_reuse.log` | Prefix 实验日志 |
| `results/logs/retrieval_scheduler.log` | Scheduler 实验日志 |
| `results/logs/retrieval_scheduler_decisions.csv` | 每次调度决策明细 |
| `results/figures/*.png` | 带宽 / 延迟 / TTFT / 调度对比图 |

无 Mooncake 时至少应生成：

- `results/csv/prefix_reuse.csv`
- `results/csv/retrieval_scheduler.csv`
- `results/figures/prefix_length_vs_ttft_reduction.png`
- `results/figures/scheduler_latency.png`
- `results/logs/prefix_reuse.log`
- `results/logs/retrieval_scheduler.log`

---

## 当前限制

1. **非侵入**：不修改 Mooncake 核心；Store 侧完全依赖官方 `store_kv_bench.py`。
2. **Prefix / Scheduler 为仿真**：用于策略对比与趋势分析，不等同于线上真实 LLM serving 延迟。
3. **Store 依赖外部服务**：未启动 `mooncake_master` 时 Store 实验会失败，但不阻塞其余流水线。
4. **单机默认配置**：默认 TCP + 本机 metadata/master；RDMA / 多机需自行改参数。

---

## 后续计划

- 接入更多官方 scenario（`fill`、`write_perf`、`mixed_rw`、`zcopy`）的一键矩阵
- 将仿真参数与真实 Store get 延迟标定对齐
- 扩展 CachePilot 调度分数（副本放置、带宽预算、跨机拓扑）
- 增加 CI 冒烟：无 Mooncake 时校验仿真与绘图产物

---

## License

本项目为 2026 Mooncake 赛题参赛作品，代码可独立使用与复现实验。Mooncake 本体请遵循其上游许可证。
