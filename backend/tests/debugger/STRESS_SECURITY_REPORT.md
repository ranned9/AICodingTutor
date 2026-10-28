# GDB迁移阶段5：代表性案例集与压力/安全测试汇总

## 1. 代表性C案例集

### 1.1 基础功能案例（6个，来自引擎对比测试）

| 案例名 | 覆盖特性 | 断点行 | 状态 |
|--------|---------|--------|------|
| simple_return | 基本变量赋值与返回 | 2 | ✅ |
| array_sum | 数组初始化+循环求和 | 3 | ✅ |
| struct_access | 结构体字段访问 | 2 | ✅ |
| function_call | 函数调用与返回值 | 3 | ✅ |
| global_var | 全局变量读取 | 2 | ✅ |
| pointer_deref | 指针解引用 | 3 | ✅ |

### 1.2 变量展开案例（13个，来自变量展开测试）

| 案例名 | 覆盖特性 | 状态 |
|--------|---------|------|
| array_expansion | 一维数组完整展开 | ✅ |
| 2d_array_expansion | 二维数组嵌套展开 | ✅ |
| struct_expansion | 结构体字段展开 | ✅ |
| nested_struct_expansion | 嵌套结构体递归展开 | ✅ |
| struct_array_expansion | 结构体数组展开 | ✅ |
| pointer_expansion | 指针指向目标展开 | ✅ |
| null_pointer | 空指针安全处理 | ✅ |
| circular_linked_list | 循环链表检测 | ✅ |
| large_array_truncation | 大数组预算截断 | ✅ |
| deep_nesting_truncation | 深嵌套预算截断 | ✅ |
| varobj_cleanup_no_accumulation | varobj清理不累积 | ✅ |
| variable_out_of_scope | 变量作用域隔离 | ✅ |
| recursive_call_same_var_different_frames | 递归调用同变量不同帧 | ✅ |

### 1.3 引擎功能案例（11个，来自引擎测试）

| 案例名 | 覆盖特性 | 状态 |
|--------|---------|------|
| engine_start_step_continue_stop | 全链路start→step→continue→stop | ✅ |
| engine_step_into | 步入函数调用 | ✅ |
| engine_continue_to_breakpoint | continue到断点 | ✅ |
| engine_compile_error | 编译错误处理 | ✅ |
| engine_session_not_found | 不存在会话处理 | ✅ |
| engine_multiple_breakpoints | 多断点设置 | ✅ |
| engine_shutdown_cleanup | shutdown清理 | ✅ |
| engine_global_variables | 全局变量读取 | ✅ |
| engine_step_after_exit | 退出后step处理 | ✅ |
| engine_stop_idempotent | stop幂等性 | ✅ |
| engine_via_session_manager | 通过SessionManager调用 | ✅ |

## 2. 压力测试结果

**测试文件**: `backend/tests/debugger/test_stress.py` — 15个测试，全部通过

### 2.1 并发会话（3个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| concurrent_sessions_independent | 5个GDB会话并发启动，会话ID唯一 | ✅ |
| concurrent_step_on_different_sessions | 2个会话并发单步，各自独立前进 | ✅ |
| session_limit_enforced | max_sessions=2时第3个会话被拒绝 | ✅ |

### 2.2 大数组（2个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| large_array_snapshot | 500元素数组，max_children=100，快照含arr变量 | ✅ |
| large_array_truncated | 2000元素数组，max_children=50，截断不崩溃 | ✅ |

### 2.3 深链表/深递归（2个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| deep_linked_list | 20节点链表，max_depth=5，遍历不崩溃 | ✅ |
| deep_recursion_stack | fib(10)递归，step_into进入fib函数 | ✅ |

### 2.4 超时（2个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| infinite_loop_timeout | 死循环continue超时，返回TIMEOUT错误 | ✅ |
| long_running_program_completes | 10万次循环，continue正常完成 | ✅ |

### 2.5 信号（3个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| sigsegv_handling | 空指针解引用SIGSEGV，GDB捕获信号 | ✅ |
| sigabrt_handling | abort()触发SIGABRT，GDB捕获信号 | ✅ |
| normal_exit_signal | 正常return，stop reason为exited | ✅ |

### 2.6 资源清理（2个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| shutdown_cleans_all_sessions | shutdown后所有会话NOT_FOUND | ✅ |
| temp_dir_cleaned_after_stop | stop后临时目录被删除 | ✅ |

### 2.7 混合引擎（1个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| manager_concurrent_mixed_engines | SessionManager同时管理legacy+gdb会话 | ✅ |

## 3. 安全测试结果

**测试文件**: `backend/tests/debugger/test_security.py` — 12个测试，全部通过

### 3.1 OS级隔离（3个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| gdb_runs_in_separate_process | GDB在独立子进程运行，PID不同于主进程 | ✅ |
| each_session_isolated_temp_dir | 每个会话独立临时目录 | ✅ |
| no_source_modification | GDB引擎不插桩，源文件与原始代码一致 | ✅ |

### 3.2 资源限制（5个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| session_count_limit | max_sessions=3时第4个被拒，释放后可新建 | ✅ |
| cleanup_releases_resources | stop后GDB进程终止+临时目录删除 | ✅ |
| double_stop_safe | 重复stop返回NOT_FOUND，不抛异常 | ✅ |
| step_nonexistent_session | 不存在会话step返回NOT_FOUND | ✅ |
| compiler_no_user_flags | 编译参数由配置固定，不接受用户输入 | ✅ |

### 3.3 并发控制（2个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| concurrent_step_same_session_serialized | 同一会话3线程并发step，串行化不崩溃 | ✅ |
| shutdown_idempotent | shutdown可重复调用 | ✅ |

### 3.4 编译安全（2个）

| 测试名 | 场景 | 结果 |
|--------|------|------|
| compiler_rejects_empty_source | 空源码编译失败 | ✅ |
| compiler_reports_syntax_error | 语法错误产生结构化诊断 | ✅ |

## 4. 测试统计汇总

| 类别 | 测试数 | 通过 | 跳过 | 失败 |
|------|--------|------|------|------|
| MI解析器单测 | 19 | 19 | 0 | 0 |
| C源码测试 | 8 | 8 | 0 | 0 |
| 编译器测试 | 4 | 4 | 0 | 0 |
| 快照适配器测试 | 4 | 4 | 0 | 0 |
| 探针集成测试 | 3 | 2 | 1 | 0 |
| 集成测试 | 14 | 14 | 0 | 0 |
| 引擎测试 | 11 | 11 | 0 | 0 |
| 变量展开测试 | 13 | 13 | 0 | 0 |
| 引擎对比测试 | 10 | 10 | 0 | 0 |
| **压力测试** | **15** | **15** | **0** | **0** |
| **安全测试** | **12** | **12** | **0** | **0** |
| **debugger模块合计** | **113** | **112** | **1** | **0** |
| 旧链路测试 | 50 | 50 | 0 | 0 |
| **总计** | **163** | **162** | **1** | **0** |

## 5. 不变量验证

| 不变量 | 验证方式 | 状态 |
|--------|---------|------|
| 不插桩 | test_no_source_modification: 源文件无SNAPSHOT标记 | ✅ |
| 不直接返回MI原文 | SnapshotAdapter转换结构化数据 | ✅ |
| 不在命令响应后立即采样 | 等待*stopped事件 | ✅ |
| 不并发执行命令 | test_concurrent_step_same_session_serialized | ✅ |
| 不无上限展开数组 | test_large_array_truncated + max_children | ✅ |
| 不接受用户编译参数 | test_compiler_no_user_flags | ✅ |
| 不假设断点行能停住 | 读取GDB返回的实际解析位置 | ✅ |
| 旧链路零改动 | 50个旧测试全部通过 | ✅ |

## 6. 回滚办法

当前 `default_engine = "legacy"`，回滚方式：
1. 将 `backend/app/debugger/config.py` 中 `default_engine` 改回 `"legacy"`
2. 或在API请求中不传 `engine` 参数（默认使用legacy）
3. 旧链路代码（Instrumenter/SandboxExecutor/SnapshotCollector）完整保留