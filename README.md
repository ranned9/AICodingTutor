# C 语言内存时序可视化调试实训平台

面向 C 语言初学者的交互式调试教学平台。平台调用 GCC 编译用户代码，并通过 GDB/MI 控制真实程序执行；前端以代码行、调用栈、变量和堆对象快照展示执行过程。

## 当前功能

- **真实编译与调试**：使用 GCC 编译、GDB 执行；支持单步、步入、继续到断点和停止。
- **执行过程回看**：完整执行模式自动逐步运行，可拖动时间线查看已有快照；完整执行超过 30 秒会自动停止。
- **栈与变量视图**：显示用户代码的调用栈、局部变量、全局变量及数组/结构体变量树。
- **堆内存视图**：追踪用户代码中的 `malloc`、`calloc`、`realloc` 和 `free`；对有类型信息的指针展示已分配块及其元素，并标记释放状态。
- **案例库**：内置基础变量、函数调用栈、`malloc/free`、指针、数组、结构体、野指针风险和全局变量案例。
- **AI 教学问答**：可针对当前快照提问。配置昇腾 AI 接口后调用真实服务；未配置时返回模拟答复。
- **工具链诊断**：启动页面会检查 GCC/GDB 配置，后端提供诊断接口。

## 环境要求

- Python 3.10 或更高版本
- GCC 和 GDB
- 支持 `-Wl,--wrap` 的 GNU 链接器（堆内存追踪使用）
- Windows 推荐使用 MinGW-w64 GCC/GDB；Linux 使用 GCC/GDB 和 GNU binutils

## 安装与启动

在项目根目录执行以下命令。

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

$env:GCC_PATH = 'D:\mingw64\bin\gcc.exe'
$env:GDB_PATH = 'D:\mingw64\bin\gdb.exe'
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

将 `GCC_PATH`、`GDB_PATH` 替换为本机实际路径。PowerShell 执行虚拟环境激活脚本受策略限制时，也可以直接运行 `.venv\Scripts\python.exe -m pip ...` 和 `.venv\Scripts\python.exe -m uvicorn ...`。

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt

export GCC_PATH="$(command -v gcc)"
export GDB_PATH="$(command -v gdb)"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

服务启动后访问 <http://127.0.0.1:8000>。FastAPI 同时托管 `frontend/` 静态页面和 `/api` 接口。

如果未设置工具链环境变量，程序会优先使用默认路径：Windows 默认 GCC 为 `D:\Dve-cpp\MinGW32\bin\gcc.exe`、GDB 为同目录下的 `gdb.exe`；Linux 默认从 `PATH` 查找 `gcc` 和 `gdb`。可通过 `GET /api/debug/diagnose` 检查最终采用的路径。

## 使用方式

1. 在案例下拉框中加载示例，或在编辑区输入 C 代码。
2. 选择调试模式：
   - `full`：从 `main` 开始自动逐步执行，最长 30 秒；
   - `step`：在 `main` 或首个有效断点处暂停，使用“单步”/“步入”控制；
   - `breakpoint`：运行到所设断点后暂停，可继续运行到后续断点。
3. 查看当前源码行和内存快照；执行结束后可拖动时间线回看。
4. 选择快照后，可在 AI 教学助手区域提问。

## 堆追踪与已知限制

堆追踪通过编译时链接 `backend/app/debugger/heap_tracker.c` 实现，不会改写编辑器中的用户源码。追踪从程序停在 `main` 后开始，以排除 C 运行库启动阶段的内部申请。

- 局部指针变量本身仍显示在栈区；只有指向追踪到的动态分配块时，堆区才会显示对应对象。指向栈变量的指针不会产生堆对象。
- `void *` 没有元素类型，平台只能显示地址和分配大小，无法推断元素值。超大数组/对象的子项显示受调试器展开上限限制。
- 释放后的对象会标记为已释放，但 C 的释放后访问属于未定义行为，不保证每次都触发异常或在访问处停止。本项目当前工具链不启用 AddressSanitizer。
- GDB 展示的未初始化变量值是栈内存残留，不代表稳定或随机生成的有效值；应以对应初始化语句执行后的快照为准。
- 用户代码由本机编译并在本机执行。当前实现不是强隔离的沙箱，请勿运行来源不可信的代码。

## AI 配置

AI 接口采用兼容 Chat Completions 的请求格式。设置以下环境变量后，后端会调用配置的服务：

| 环境变量 | 说明 |
|---|---|
| `ASCEND_AI_API_URL` | AI 服务请求地址 |
| `ASCEND_AI_API_KEY` | API 密钥 |
| `ASCEND_AI_MODEL` | 模型名称；默认 `ascend-default` |

如果未设置 URL 或密钥，问答接口会返回本地模拟答复，不代表真实模型推理。

## API 概览

除静态页面外，API 返回统一结构：`{ "code": 0, "message": "...", "data": ... }`；`code = 0` 表示成功。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 服务健康检查 |
| `GET` | `/api/debug/diagnose` | 检查 GCC/GDB 配置 |
| `GET` | `/api/cases` | 获取案例列表 |
| `GET` | `/api/cases/{case_id}` | 获取案例代码 |
| `POST` | `/api/debug/start` | 编译并启动调试会话 |
| `POST` | `/api/debug/{session_id}/step` | 单步（step over） |
| `POST` | `/api/debug/{session_id}/step_into` | 步入 |
| `POST` | `/api/debug/{session_id}/continue` | 继续执行 |
| `POST` | `/api/debug/{session_id}/stop` | 停止会话 |
| `GET` | `/api/debug/{session_id}/snapshots` | 获取快照数量和事件索引 |
| `GET` | `/api/debug/{session_id}/snapshots/{step}` | 获取指定快照 |
| `POST` | `/api/debug/{session_id}/ask` | 针对指定快照提问 |

启动请求示例：

```json
{
  "code": "int main(void) { int x = 42; return x; }",
  "mode": "full",
  "breakpoints": [],
  "engine": "gdb"
}
```

当前只支持 `gdb` 引擎。`mode` 可选 `full`、`step`、`breakpoint`。问答请求体为 `{"step": 0, "question": "这里的指针指向哪里？"}`。

## 测试

安装开发测试依赖并运行：

```bash
python -m pip install pytest
python -m pytest tests/ -v
python -m pytest backend/tests/debugger/ -v
```

后端调试器集成测试需要本机 GCC/GDB；缺少工具链时，相关测试会跳过或失败。`pytest.ini` 默认的 `testpaths` 是 `tests`，因此要运行新调试器测试，需显式指定 `backend/tests/debugger/`。

## 项目结构

```text
backend/app/
  api/                 FastAPI 路由（案例、调试、快照、AI）
  debugger/            GCC/GDB-MI 编译、执行、变量和堆追踪
    heap_tracker.c     malloc/calloc/realloc/free 链接包装器
    probe/             工具链能力探针及 MI fixtures
  models/              请求、会话和内存快照模型
  services/            案例库、会话管理、AI 代理、快照存储
backend/tests/         新 GDB 调试器测试
frontend/              原生 HTML/CSS/JavaScript 前端
tests/                 基础 API、模型和案例测试
data/                  本地运行时数据目录
GDB_MI_MIGRATION_PLAN.md  GDB/MI 架构迁移计划
```

## 当前实现说明

调试会话和快照当前保存在后端进程内存中，后端重启后会话不会保留。`data/` 作为运行时数据目录保留；不要将本地密钥或不可信代码提交到版本库。
