# CachePilot：基于 Mooncake 的 KVCache 复用与调度优化系统

> 2026 Mooncake 赛题参赛作品  
> 定位：**非侵入式** KVCache 评测套件（non-invasive evaluation suite）  
> Store 底座：**真实 Mooncake Store 实机实测**（已在 AutoDL RTX 4090 跑通）

---

## 项目简介

**CachePilot** 是一个基于 [Mooncake](https://github.com/kvcache-ai/Mooncake) 的 KVCache 复用与调度评测系统。项目以 Mooncake 官方 Store Benchmark 为真实底座，通过封装 `store_kv_bench.py` 完成真实 Mooncake Store 的 put/get/`read_perf` 实机测试，并在此基础上扩展 Prefix Reuse workload 评估和 Retrieval Scheduler 策略评估模块。系统统一输出 CSV、日志和图表，用于分析 KVCache 存储吞吐、P50/P99 延迟、Prefix 复用收益以及检索调度策略效果。

项目**不修改 Mooncake 核心代码**，真实调用链路为：

`mooncake_master` → HTTP metadata → `MooncakeDistributedStore` → 官方 `store_kv_bench.py` → CachePilot `mooncake_store_runner.py`

---

## 真实实测结果摘要

实验平台：AutoDL 容器实例 · RTX 4090 24GB · 16 核 CPU · 120GB 内存 · Ubuntu 22.04 · Python 3.10 · CUDA 11.8 · `mooncake-transfer-engine-non-cuda` · 协议 TCP。

### verify_write（`results/csv/store_verify_real.csv`）

已成功，`return_code=0`，`misses=0`，`verify_failures=0`：

| 指标 | 数值 |
|------|------|
| req/s | 2482.98 |
| kv/s | 9931.94 |
| MiB/s | 38.8 |
| lat_mean | 0.377 ms |
| lat_p50 | 0.260 ms |
| lat_p95 | 0.718 ms |
| lat_p99 | 0.781 ms |

### read_perf（`results/csv/store_benchmark.csv`）

共 **16 组**真实运行，全部 `return_code=0`（value_size ∈ {4KB, 64KB, 1MB, 4MB} × batch_size ∈ {1, 4, 8, 16}）。

典型结果：

| value_size | batch | MiB/s | p50 (ms) | p99 (ms) |
|------------|-------|-------|----------|----------|
| 4KB | 1 | 28.78 | 0.106 | 0.380 |
| 4KB | 16 | 139.86 | 0.352 | 0.703 |
| 64KB | 4 | 694.43 | 0.304 | 0.917 |
| 1MB | 4 | **1399.08** | 2.574 | 5.956 |
| 4MB | 4 | 1227.74 | 12.251 | 22.456 |
| 4MB | 16 | 1015.36 | 52.517 | **93.267** |

要点：

- 最高带宽：1MB value_size、batch=4，**1399.08 MiB/s**
- 大对象高并发：4MB、batch=16，p99=**93.267 ms**
- 全程 `misses=0`，`verify_failures=0`

---

## 赛题对应关系

| 赛题关注点 | CachePilot 模块 | 说明 |
|-----------|-----------------|------|
| Mooncake Store 性能 | `mooncake_store_runner.py` | 真实调用官方 `store_kv_bench.py`，实测 `MooncakeDistributedStore` |
| KVCache 复用 | `prefix_reuse_benchmark.py` | 可控 Prefix Reuse workload 评估（TTFT 改善趋势） |
| 检索 / 调度优化 | `retrieval_scheduler_sim.py` | Retrieval Scheduler 策略评估（Random / Nearest / Reuse-aware / CachePilot） |
| 可复现实验 | `scripts/run_all.sh` + `results/` | 一键跑通并落盘 CSV / PNG / log |

---

## 系统模块

### 1. Store Benchmark（真实实机实测）

真实调用 Mooncake 官方 `store_kv_bench.py`，测试 `MooncakeDistributedStore` 的 `verify_write` 与 `read_perf`。已在 AutoDL RTX 4090 实例上跑通真实数据。

### 2. Prefix Reuse Evaluation（可控 workload 评估）

面向长上下文多请求共享 prefix 的可控 workload 评估，基于 prefix length、cache hit ratio 和 Store get latency 参数计算 TTFT 改善趋势。可与真实 Store 延迟参数对齐。

### 3. Retrieval Scheduler Evaluation（离线策略评估）

面向多节点 KVCache 检索场景的策略评估，对比 Random、Nearest、Reuse-aware、CachePilot，输出延迟、远程流量与热点比。

```
┌─────────────────────────────────────────────────────────┐
│                    CachePilot Pipeline                   │
├──────────────┬──────────────────┬───────────────────────┤
│ Store Bench  │  Prefix Reuse    │  Retrieval Scheduler  │
│ (真实实测)    │  Evaluation     │  Evaluation           │
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

说明：Store Benchmark 是真实 Mooncake Store 实机实测；Prefix Reuse 与 Retrieval Scheduler 是策略评估模块，当前基于可控 workload 与真实 Store 参数进行离线评估。

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

依赖：`numpy`、`pandas`、`matplotlib`。Store 实测另需安装 Mooncake Python binding（本实验使用 `mooncake-transfer-engine-non-cuda`）并启动 `mooncake_master`。

---

## 如何设置 MOONCAKE_ROOT

Store Benchmark 通过 subprocess 调用官方脚本：

```
{MOONCAKE_ROOT}/mooncake-store/benchmarks/store_kv_bench.py
```

```bash
# 方式 1：环境变量
export MOONCAKE_ROOT=/path/to/Mooncake

# 方式 2：命令行参数
python benchmark/mooncake_store_runner.py --mooncake-root /path/to/Mooncake ...
```

未指定时自动尝试：`../Mooncake`、`../../Mooncake`、`/root/autodl-tmp/mooncake_competition/Mooncake`，或读取 `MOONCAKE_ROOT`。

找不到时提示：

```text
Mooncake root not found. Please set --mooncake-root or MOONCAKE_ROOT.
```

Store 实测依赖 Mooncake master 和 Python binding；Prefix Reuse 与 Scheduler 可作为离线策略评估模块独立运行。

---

## 如何启动 Mooncake master

```bash
mooncake_master \
  --enable_http_metadata_server=true \
  --http_metadata_server_host=0.0.0.0 \
  --http_metadata_server_port=8080 \
  --eviction_high_watermark_ratio=0.95
```

本实验 AutoDL 实例连接参数：

| 参数 | 值 |
|------|-----|
| metadata-server | `http://HOST_IP:8080/metadata` |
| master-server | `HOST_IP:50051` |
| protocol | `tcp` |
| local-hostname | `127.0.0.1:50071`（客户端默认） |

---

## 如何运行

### 一键全流程（推荐）

```bash
export MOONCAKE_ROOT=/path/to/Mooncake
# 先启动 mooncake_master
bash scripts/run_all.sh
```

执行顺序：

1. 创建 `results/{csv,logs,figures}`
2. `run_store_verify.sh` — 真实 verify_write
3. `run_store_perf.sh` — 真实 read_perf 矩阵
4. `run_prefix_reuse.sh` — Prefix Reuse 可控 workload 评估
5. `run_scheduler_sim.sh` — Retrieval Scheduler 策略评估
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
| `results/csv/store_verify_real.csv` | 真实 verify_write 结果 |
| `results/csv/store_benchmark.csv` | 真实 read_perf 矩阵结果 |
| `results/csv/prefix_reuse.csv` | Prefix Reuse 可控 workload 评估结果 |
| `results/csv/retrieval_scheduler.csv` | Retrieval Scheduler 策略评估汇总 |
| `results/logs/store_*.log` | 每次 Store 运行的原始 stdout/stderr |
| `results/logs/prefix_reuse.log` | Prefix 评估日志 |
| `results/logs/retrieval_scheduler.log` | Scheduler 评估日志 |
| `results/logs/retrieval_scheduler_decisions.csv` | 每次调度决策明细 |
| `results/figures/*.png` | 带宽 / 延迟 / TTFT / 调度对比图 |

---

## 当前限制

1. **非侵入**：不修改 Mooncake 核心；Store 侧完全依赖官方 `store_kv_bench.py` 与 `MooncakeDistributedStore`。
2. **Prefix / Scheduler 为离线策略评估**：基于可控 workload 与可标定 Store 参数，不作为真实分布式集群端到端 LLM serving 性能声明。
3. **Store 实测依赖服务**：需启动 `mooncake_master` 并安装 Mooncake Python binding。
4. **当前实机配置为单机 TCP**：RDMA / 多机拓扑需另行扩展。

---

## 后续计划

- 扩展官方 scenario（`fill`、`write_perf`、`mixed_rw`、`zcopy`）一键矩阵
- 用真实 Store get 延迟进一步标定 Prefix Reuse 参数
- 扩展 CachePilot 调度分数（副本放置、带宽预算、跨机拓扑）
- 多机 / RDMA 环境下的 Store 与调度联合评测

---

## License

本项目为 2026 Mooncake 赛题参赛作品，代码可独立使用与复现实验。Mooncake 本体请遵循其上游许可证。
