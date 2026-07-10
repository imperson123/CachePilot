# CachePilot 设计文档

## 1. 背景

大模型推理中，长上下文 Prefill 成本高，KVCache 的跨请求复用与跨节点检索调度直接影响 TTFT 与集群带宽。Mooncake 提供了分布式 KVCache Store 与官方 benchmark（`store_kv_bench.py`），适合作为底层存储与性能基线。

CachePilot 的目标不是 fork Mooncake，而是在其之上构建一层**可复现的评测与调度实验系统**：

- 用官方 Store bench 建立真实 IO 基线；
- 用可控仿真量化 Prefix 复用收益；
- 用统一 workload 对比检索调度策略。

---

## 2. CachePilot 架构

```
                 ┌────────────────────┐
                 │   scripts/run_*.sh │
                 └─────────┬──────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
 ┌───────────────┐ ┌───────────────┐ ┌──────────────────┐
 │ Store Runner  │ │ Prefix Reuse  │ │ Retrieval Sched  │
 │ (subprocess)  │ │ (analytic)    │ │ (Monte Carlo)    │
 └───────┬───────┘ └───────┬───────┘ └────────┬─────────┘
         │                 │                  │
         ▼                 ▼                  ▼
   parse_store_output   metrics.py        metrics.py
         │                 │                  │
         └────────────┬────┴──────────────────┘
                      ▼
              results/csv/*.csv
                      │
                      ▼
              plot_results.py
                      │
                      ▼
              results/figures/*.png
```

设计原则：

1. **非侵入**：不改 Mooncake 源码；
2. **可独立运行**：无 Store 服务时仿真仍可完成；
3. **路径相对项目根**：脚本 `cd` 到仓库根再执行；
4. **失败隔离**：Store 失败写入 CSV/`return_code`，流水线继续。

---

## 3. Store Benchmark 设计

### 3.1 包装而非模拟

`mooncake_store_runner.py` 通过 `subprocess` 调用：

```text
{MOONCAKE_ROOT}/mooncake-store/benchmarks/store_kv_bench.py
```

不自行实现 put/get，避免与官方语义漂移。

### 3.2 Mooncake Root 解析

优先级：

1. `--mooncake-root`
2. 环境变量 `MOONCAKE_ROOT`
3. 候选路径：`../Mooncake`、`../../Mooncake`、`/root/autodl-tmp/mooncake_competition/Mooncake`

校验条件：存在 `mooncake-store/benchmarks/store_kv_bench.py`。

### 3.3 参数矩阵

遍历 `value_sizes × batch_sizes`，按 scenario 组装官方参数：

| scenario | 关键参数 |
|----------|----------|
| verify_write | `--verify --pattern 0xab`，较小 `nr-objects` |
| write_perf | `--runtime` |
| read_perf | `--prepare-mode auto --phase-gap-mode sleep --phase-gap-sec 1 --verify --pattern 0xee` |
| mixed_rw | `--prepare-mode auto --rwmixread 70` |

### 3.4 输出解析

`parse_store_output.py` 用正则提取 `req/s`、`kv/s`、`MiB/s`、延迟分位、`misses`、`verify_failures`、`errors`；缺失字段填 `None`，不崩溃。

---

## 4. Prefix Reuse 设计

目标：在给定 prefix 长度与 cache hit ratio 下，估计相对「无缓存 Prefill」的 TTFT 收益。

公式：

```text
prefix_kv_mb = prefix_tokens * kv_bytes_per_token / 1024 / 1024
no_cache_ttft = prefix_tokens * prefill_ms_per_token + decode_first_token_ms
cache_get_latency = store_get_base_ms + prefix_kv_mb * store_get_ms_per_mb
prefix_cache_ttft = hit_ratio * (cache_get_latency + decode_first_token_ms)
                  + (1 - hit_ratio) * no_cache_ttft
ttft_reduction_ms = no_cache_ttft - prefix_cache_ttft
ttft_reduction_pct = ttft_reduction_ms / no_cache_ttft * 100
```

含义：

- hit 时：从 Store 取回 Prefix KV + 首 token decode；
- miss 时：完整 Prefill + 首 token decode；
- `store_get_*` 参数可与真实 Store 延迟标定对齐。

---

## 5. Retrieval Scheduler 设计

### 5.1 Block Metadata

每个 KV block：

| 字段 | 含义 |
|------|------|
| block_id | 块 ID |
| prefix_id | 所属 prefix |
| reuse_count | 历史复用次数 |
| importance_score | 重要性 |
| location / source_node | 主副本节点 |
| replica_list | 可用副本节点 |
| estimated_fetch_latency_ms | 各副本拉取延迟 |
| size_mb | 块大小 |

### 5.2 策略

1. **Random**：在副本中均匀随机；
2. **Nearest**：优先本地副本，否则选最低延迟副本；
3. **Reuse-aware**：高复用块尽量本地命中，否则选最近；
4. **CachePilot**：

```text
score = alpha * importance_score
      + beta  * normalized_reuse_count
      - gamma * normalized_fetch_latency
      - load_penalty
      + local_bonus
```

选 score 最高的副本；`hotspot_ratio = max_source_load / mean_source_load`。

### 5.3 公平对比

- 固定 `--seed`；
- 同一批 blocks / requests 喂给所有策略；
- 输出 summary CSV + decision log。

---

## 6. 数据流

```text
run_all.sh
  ├─ store_verify / store_perf
  │    └─ logs/store_*.log → parse → csv/store_benchmark.csv
  ├─ prefix_reuse → csv/prefix_reuse.csv + logs/prefix_reuse.log
  ├─ scheduler_sim → csv/retrieval_scheduler.csv
  │                 + logs/retrieval_scheduler_decisions.csv
  └─ plot_results → figures/*.png
```

---

## 7. 和 Mooncake 的关系

| 项目 | 关系 |
|------|------|
| Mooncake Store | 外部依赖；通过官方 bench 测量 |
| mooncake_master | 运行 Store 实验的前置服务 |
| CachePilot | 独立仓库；评测 / 仿真 / 可视化层 |

CachePilot **不** vendoring Mooncake，也不 patch 其 wheel / C++ 代码。

---

## 8. 局限性

1. Prefix / Scheduler 为解析或蒙特卡洛仿真，未接入真实 LLM runtime。
2. Store 输出解析依赖官方日志文本格式；上游格式变更需更新正则。
3. CachePilot 分数中的 load_penalty / local_bonus 为启发式，需结合真实拓扑再标定。
4. 默认单机 TCP；RDMA、多网卡、跨机延迟模型未内建。
