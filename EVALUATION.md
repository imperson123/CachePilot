# CachePilot 评测文档

## 1. 实验环境模板

| 项目 | 填写 |
|------|------|
| 机器型号 / CPU | |
| 内存 | |
| GPU（如有） | |
| 操作系统 | |
| Python 版本 | ≥ 3.10 |
| Mooncake 版本 / commit | |
| MOONCAKE_ROOT | |
| 网络（TCP / RDMA） | |
| mooncake_master 启动参数 | 见 README |
| CachePilot commit | |

---

## 2. 指标定义

### 2.1 Store Benchmark

| 指标 | 含义 |
|------|------|
| req/s | 请求吞吐 |
| kv/s | KV 操作吞吐 |
| MiB/s | 有效带宽 |
| lat_mean / p50 / p95 / p99 | 延迟均值与分位 |
| misses | 未命中次数 |
| verify_failures | 校验失败次数 |
| errors | 错误次数 |
| return_code | 子进程退出码（0 成功） |

### 2.2 Prefix Reuse

| 指标 | 含义 |
|------|------|
| no_cache_ttft_ms | 无缓存 TTFT |
| prefix_cache_ttft_ms | 有 Prefix Cache 时的期望 TTFT |
| store_get_latency_ms | 从 Store 拉取 Prefix KV 的估计延迟 |
| ttft_reduction_ms / pct | 相对无缓存的绝对 / 相对收益 |

### 2.3 Retrieval Scheduler

| 指标 | 含义 |
|------|------|
| avg / p50 / p95 / p99 latency | 检索延迟 |
| remote_traffic_mb | 跨节点传输量 |
| hotspot_ratio | `max_source_load / mean_source_load` |
| avg_source_load / max_source_load | 源节点负载 |

---

## 3. Store Benchmark 结果表模板

| scenario | io_api | value_size | batch_size | req/s | MiB/s | lat_p50 | lat_p99 | return_code |
|----------|--------|------------|------------|-------|-------|---------|---------|-------------|
| read_perf | plain | 4096 | 1 | | | | | |
| read_perf | plain | 4096 | 4 | | | | | |
| read_perf | plain | 65536 | 8 | | | | | |
| ... | | | | | | | | |

数据源：`results/csv/store_benchmark.csv`。

---

## 4. Prefix Reuse 结果表模板

| prefix_tokens | cache_hit_ratio | no_cache_ttft_ms | prefix_cache_ttft_ms | ttft_reduction_pct |
|---------------|-----------------|------------------|----------------------|--------------------|
| 512 | 0.0 | | | |
| 512 | 0.5 | | | |
| 4096 | 0.75 | | | |
| 8192 | 0.9 | | | |

数据源：`results/csv/prefix_reuse.csv`。

---

## 5. Scheduler 结果表模板

| scheduler | avg_latency_ms | p99_latency_ms | remote_traffic_mb | hotspot_ratio |
|-----------|----------------|----------------|-------------------|---------------|
| Random | | | | |
| Nearest | | | | |
| Reuse-aware | | | | |
| CachePilot | | | | |

数据源：`results/csv/retrieval_scheduler.csv`。

---

## 6. 图表说明

| 文件 | 内容 |
|------|------|
| `store_bandwidth_by_value_size.png` | 不同 value size 下带宽（按 batch 分组） |
| `store_p99_by_batch_size.png` | 不同 batch size 下 p99 延迟 |
| `prefix_length_vs_ttft_reduction.png` | Prefix 长度 vs TTFT 降低比例 |
| `cache_hit_ratio_vs_ttft.png` | Hit ratio vs TTFT |
| `scheduler_latency.png` | 各策略延迟对比 |
| `scheduler_remote_traffic.png` | 各策略远程流量 |
| `scheduler_hotspot.png` | 各策略热点比 |

若 `store_benchmark.csv` 不存在或无成功行，Store 相关图会 warning 并跳过，不影响其余图。

---

## 7. 复现实验步骤

```bash
cd CachePilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# （可选）启动 Mooncake 并设置路径
export MOONCAKE_ROOT=/path/to/Mooncake
# mooncake_master ...

bash scripts/run_all.sh
```

验收产物（无 Mooncake 时最低要求）：

- `results/csv/prefix_reuse.csv`
- `results/csv/retrieval_scheduler.csv`
- `results/figures/prefix_length_vs_ttft_reduction.png`
- `results/figures/scheduler_latency.png`
- `results/logs/prefix_reuse.log`
- `results/logs/retrieval_scheduler.log`

有 Mooncake 且 master 已启动时额外期望：

- `results/csv/store_benchmark.csv`
- `results/logs/store_*.log`

---

## 8. 结果分析模板

### 8.1 Store

- 带宽是否随 value size 上升并在大对象接近平台上限？
- p99 是否随 batch size 恶化？是否存在明显拐点？
- verify_write 是否 `verify_failures=0`？

### 8.2 Prefix Reuse

- 固定 hit ratio 时，更长 prefix 的相对收益是否更大？
- hit ratio 从 0→0.9，TTFT 曲线是否近似线性下降？
- 将 `store_get_ms_per_mb` 换成实测 Store 延迟后，结论是否仍成立？

### 8.3 Scheduler

- CachePilot 相对 Random 的 p99 / remote traffic / hotspot 改善幅度？
- Nearest 是否已能显著降延迟？CachePilot 的额外收益来自哪里（复用 / 负载）？
- 调整 `alpha/beta/gamma` 后，热点与延迟的权衡如何变化？

### 8.4 结论（填写）

> 在本实验环境下，……（一句话结论）  
> 主要收益来自……  
> 主要瓶颈是……  
> 下一步建议……
