import json
import logging
import os

import httpx

from app.api.response import ErrorCode
from app.models.snapshot_model import MemorySnapshot

logger = logging.getLogger(__name__)

AI_TIMEOUT = 10.0
AI_API_URL = os.environ.get("ASCEND_AI_API_URL", "")
AI_API_KEY = os.environ.get("ASCEND_AI_API_KEY", "")
AI_MODEL = os.environ.get("ASCEND_AI_MODEL", "ascend-default")

SYSTEM_PROMPT = """你是一位C语言内存教学助手。用户正在使用内存可视化调试工具学习C语言。
用户会在某个执行步骤提出问题，你需要结合当前代码和内存快照状态给出通俗易懂的教学解释。
要求：
1. 用简体中文回答
2. 面向初学者，避免过于晦涩的底层内核知识
3. 结合当前内存快照中的栈帧、堆对象、指针状态来解释
4. 解释要具体，指向当前快照中的实际数据
"""


class AIProxy:
    @staticmethod
    def build_prompt(source_code: str, snapshot: MemorySnapshot, question: str) -> str:
        snapshot_json = snapshot.model_dump_json(indent=2)
        prompt = f"""## 当前C代码
```c
{source_code}
```

## 当前执行步骤: {snapshot.step}
## 当前内存快照
```json
{snapshot_json}
```

## 学生提问
{question}
"""
        return prompt

    @staticmethod
    async def ask(source_code: str, snapshot: MemorySnapshot, question: str) -> tuple[ErrorCode, str]:
        if not question.strip():
            return ErrorCode.AI_QUESTION_EMPTY, ""

        prompt = AIProxy.build_prompt(source_code, snapshot, question)

        if not AI_API_URL or not AI_API_KEY:
            logger.warning("昇腾AI未配置，返回模拟回答")
            return ErrorCode.SUCCESS, _mock_answer(snapshot, question)

        try:
            async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
                resp = await client.post(
                    AI_API_URL,
                    headers={
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": AI_MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return ErrorCode.SUCCESS, answer
                else:
                    logger.error("AI服务返回错误: %d %s", resp.status_code, resp.text[:200])
                    return ErrorCode.AI_UNAVAILABLE, ""
        except httpx.TimeoutException:
            logger.warning("AI调用超时")
            return ErrorCode.AI_TIMEOUT, ""
        except Exception as e:
            logger.exception("AI调用异常: %s", e)
            return ErrorCode.AI_UNAVAILABLE, ""


def _mock_answer(snapshot: MemorySnapshot, question: str) -> str:
    lines = [f"当前执行到第{snapshot.step}步。"]
    if snapshot.stack_frames:
        funcs = " -> ".join(sf.function for sf in snapshot.stack_frames)
        lines.append(f"调用栈: {funcs}")
    if snapshot.heap_objects:
        active = [h for h in snapshot.heap_objects if not h.is_freed]
        lines.append(f"堆内存: {len(active)}个活跃对象")
    if snapshot.pointers:
        lines.append(f"指针: {len(snapshot.pointers)}个")
    lines.append(f"你的问题: {question}")
    lines.append("（注: 昇腾AI未配置，此为模拟回答。配置ASCEND_AI_API_URL和ASCEND_AI_API_KEY环境变量后可启用真实AI答疑。）")
    return "\n".join(lines)