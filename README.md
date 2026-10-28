# C语言内存时序可视化调试实训平台

面向 C 语言内存教学的调试实训平台。后端对用户代码做插桩，采集执行过程中的栈帧、堆对象与全局变量快照，前端按时间轴回放内存变化。

## 环境要求

- Python 3.10+（开发使用 3.12）
- GCC（MinGW32），用于编译插桩后的 C 代码

## 安装

```bash
pip install -r backend/requirements.txt
```

## 配置

编译器路径通过 `GCC_PATH` 环境变量指定，默认取 PATH 中的 `gcc`：

```bash
# Windows 示例
set GCC_PATH=D:\Dve-cpp\MinGW32\bin\gcc.exe
```

## 启动

```bash
cd D:\code\CodeArtsAgentProject\AICodingTutor
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

启动后访问 <http://127.0.0.1:8000>，前端由后端以静态资源方式挂载在根路径。健康检查：`GET /api/health`。

## 测试

```bash
pytest
```

`pytest.ini` 已配置 `pythonpath = backend` 与 `testpaths = tests`，无需额外设置。

## 目录结构

```
backend/app/
  api/       路由：case / debug / snapshot / ai
  core/      核心逻辑：插桩、编译执行、事件检测、快照采集
  models/    数据模型
  services/  会话管理、案例库、AI 代理、快照存储
frontend/    原生 HTML/CSS/JS 前端
tests/       pytest 用例
data/        运行时数据（会话快照），不入版本库
```

## 文档

- [GDB_MI_MIGRATION_PLAN.md](GDB_MI_MIGRATION_PLAN.md)：GDB/MI 接入的迁移计划
