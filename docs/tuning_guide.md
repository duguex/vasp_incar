# OpenMX 性能调优手册索引

本文件索引手册中所有与计算性能、并行效率、调优相关的内容。
对应章节可直接用 `python3 omx-db section <编号>` 查看，或用 `omx-db rag <关键词>` 语义搜索。

---

## 1. 并行方案

| 方案 | 命令 | 章节 | 说明 |
|------|------|------|------|
| MPI 并行 | `mpirun -np N openmx input.dat` | §28.1 | 各方法适用进程数上限（见下表） |
| MPI/OpenMP 混合 | `mpirun -np N openmx input.dat -nt M` | §28.2 | MKL 可额外开线程，内存占用更低 |
| 全 3D 并行 | k 点 + 对角化双重并行 | §28.1.4 | 可用超 **k 点数**的 MPI 进程 |
| NEGF 并行 | | §46.8 | 支持 MKL OpenMP 混合 |
| NEB 并行 | 自动按进程数分配 | §51.7 | |
| kSpin 并行 | MPI 按 k 点并行 | §56.7 | |

### 各方法 MPI 进程数上限

| 计算方法 | `scf.EigenvalueSolver` | 最大 MPI 进程 | 并行对象 |
|----------|------------------------|--------------|----------|
| O(N) DC / DC-LNO / Krylov | `DC` | ≤ 原子数 | 原子级 |
| Cluster | `cluster` | ≤ 自旋数 | 自旋 |
| Band | `band` | ≤ k 点数 | k 点 |
| 3D 全并行 | `band` + 特殊设置 | 可远超 k 点数 | k 点 + 对角化 |

```
omx-db rag "MPI parallelization speedup limit available processes"
```

---

## 2. 大体系计算方法

| 方法 | 复杂度 | 推荐场景 | 章节 |
|------|--------|----------|------|
| DC (Divide-Conquer) | O(N) | 共价体系，512 原子 128 MPI 加速比 ~84 | §27.1 |
| DC-LNO | O(N) | **首选**，金属/绝缘体通用，并行效率最高 | §27.2 |
| O(N) Krylov 子空间 | O(N) | 极大体系，MPI 上限 = 原子数 | §27.3 |
| 常规对角化 | O(N³) | ≤ 1000 原子，192 MPI 核 | §29.1 |
| 低阶对角化 | O(N log² N) | 低维大体系 + 超多核，`scf.EigenvalueSolver cluster2` | §48 |
| O(N) + 常规混合 | | O(N) 得自洽密度 → 常规对角化得波函数 | §29.2 |

```
omx-db rag "large scale calculation 1000 atoms benchmark"
```

---

## 3. SCF 收敛调优

### 七种 Mixing 方法 (§16.1)

| 方法 | 混搭对象 | 适用 |
|------|----------|------|
| Simple | 密度矩阵 | 简单体系 |
| GR-Pulay | 密度矩阵 | |
| **RMM-DIIS** | **密度矩阵** | **常规首选** |
| Kerker | 傅里叶电子密度 | 金属（charge sloshing） |
| **RMM-DIISK** | **傅里叶电子密度** | **金属首选** |
| RMM-DIISV | Kohn-Sham 势 | 难收敛 |
| RMM-DIISH | Kohn-Sham 哈密顿量 | 难收敛 |

### 快速调优三步

```
1. 先用 RMM-DIISK，不指定 scf.Kerker.factor（自动估计）
2. 收敛慢 → 增加 scf.Mixing.History 到 30-40
3. 发散 → 减小 scf.Max.Mixing.Weight（如 0.1 → 0.01）
```

### 运行时动态调参 (§16.3)

不停止计算，写 `System.Name_SCF_keywords` 文件即可实时改：

```
scf.maxIter 100
scf.Min.Mixing.Weight 0.01
scf.Max.Mixing.Weight 0.10
scf.Kerker.factor 10.0
scf.Mixing.StartPulay 30
scf.criterion 1.0e-6
```

```
omx-db rag "SCF convergence tuning mixing Kerker RMM-DIISK"
```

---

## 4. 编译优化

| 关注点 | 章节 | 说明 |
|--------|------|------|
| MPI 编译 | §4.3 | 设置 CC、FC、LIB |
| MPI/OpenMP 混合编译 | §4.4 | 添加 OpenMP 编译器选项 |
| FFTW3 | §4.5 | 可链接外部 FFTW3 库 |
| `-Dnosse` 等选项 | §4.6 | O(N) Krylov 方法可关闭 SSE 优化 |
| 已知问题 | §4.8 | ScaLAPACK/BLACS/FFTW3 链接常见错误 |
| `make` 目标 | §4.9 | `make install`, `make all`, `make clean` |

```
omx-db section 4.4
omx-db rag "installation compilation MPI OpenMP FFTW"
```

---

## 5. 内存分析

| 功能 | 章节 | 用法 |
|------|------|------|
| 内存逐数组输出 | §75 | `memory.usage.fileout on` → 输出 `*.memory0` 文件 |
| Memory leak 自动检测 | §73 | 运行时内存泄漏检查 |
| Memory leak 工具（开发者） | §74 | `leakdetect.cpp` / `leakdetect.h` |
| 大文件二进制输出 | §76 | IO 密集型计算的加速 |

**§75 示例输出**（`met.memory0`）:

```
Memory: SetPara_DFT: Spe_PAO_RWF   0.57 MBytes
Memory: Set_Density_Grid: AtomDen_Grid  0.78 MBytes
Memory: Force: Hx   0.00 MBytes
...
Memory: total  261.08 MBytes
```

每条数组的占用都列出，可用于定位大体系内存瓶颈。

```
omx-db rag "memory analysis usage memory leak large system"
```

---

## 6. Benchmark 数据

| 数据 | 章节 | 内容 |
|------|------|------|
| Si 介质函数 | §62.4 | 512/1000 原子，不同 k 点、核数实测 |
| O(N) 加速比 | §28.1.1 | CRAY-XC30 实测图 |
| 1000 原子 benchmark | §29.1 | AMD 集群 192 MPI 进程 |
| 自动测试 | §6-7 | `-runtest`, `-runtestL`, `-runtestL2` |
| 本机实测 | `benchmark_results.md` | v3.9 GNU vs Intel 容器对比 |

### 运行 benchmark

```bash
# 标准自动测试（14 个算例）
mpirun -np 8 openmx -runtest

# 大规模自动测试（性能检查）
mpirun -np 112 openmx -runtestL -nt 2

# 1000 原子系统
mpirun -np 128 openmx -runtestL2 -nt 4
```

```
omx-db rag "benchmark computational time elapsed speedup"
```

---

## 7. 精度 vs 效率权衡

| 调优对象 | 章节 | 影响 |
|----------|------|------|
| 基组选择 | §12.3-12.4 | 优化基组减少基函数数 |
| Cutoff energy | §14 | `scf.energycutoff` 越高越准但越慢 |
| k 点采样 | §15 | `scf.Kgrid` 越密越准 |
| 基组过完备 | §79 | 高密 bulk 体系有过完备风险，建议用优化小基组 |
| ELPA 求解器 | §28.1 | `scf.eigen.lib elpa1`/`elpa2`，性能接近 |

---

## 8. 不支持

- **GPU 加速**：手册无任何 GPU 相关内容

---

## 语义检索快捷命令

```bash
# 并行
python3 omx-db rag "MPI parallelization speedup efficiency"

# SCF 收敛
python3 omx-db rag "SCF convergence mixing RMM-DIISK Kerker"

# 大体系
python3 omx-db rag "large scale calculation 1000 atoms O(N)"

# 内存
python3 omx-db rag "memory usage analysis allocation"

# 编译优化
python3 omx-db rag "compilation optimization FFTW ScaLAPACK"
```
