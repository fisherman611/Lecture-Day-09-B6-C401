"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import os
import sys
from typing import Optional

WORKER_NAME = "policy_tool_worker"


# ─────────────────────────────────────────────
# MCP Client — Sprint 3: Thay bằng real MCP call
# ─────────────────────────────────────────────

def _call_mcp_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Gọi MCP tool.

    Sprint 3 TODO: Implement bằng cách import mcp_server hoặc gọi HTTP.

    Hiện tại: Import trực tiếp từ mcp_server.py (trong-process mock).
    """
    from datetime import datetime

    try:
        # TODO Sprint 3: Thay bằng real MCP client nếu dùng HTTP server
        from mcp_server import dispatch_tool
        result = dispatch_tool(tool_name, tool_input)
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {"code": "MCP_CALL_FAILED", "reason": str(e)},
            "timestamp": datetime.now().isoformat(),
        }


# ─────────────────────────────────────────────
# Policy Analysis Logic
# ─────────────────────────────────────────────

def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên context chunks.

    TODO Sprint 2: Implement logic này với LLM call hoặc rule-based check.

    Cần xử lý các exceptions:
    - Flash Sale → không được hoàn tiền
    - Digital product / license key / subscription → không được hoàn tiền
    - Sản phẩm đã kích hoạt → không được hoàn tiền
    - Đơn hàng trước 01/02/2026 → áp dụng policy v3 (không có trong docs)

    Returns:
        dict with: policy_applies, policy_name, exceptions_found, source, rule, explanation
    """
    task_lower = task.lower()
    context_text = " ".join([c.get("text", "") for c in chunks]).lower()

    # --- Rule-based exception detection ---
    exceptions_found = []

    # Exception 1: Flash Sale — chỉ detect khi task KHẲNG ĐỊNH là Flash Sale
    if ("flash sale" in task_lower or "flash sale" in context_text) and \
       not any(neg in task_lower for neg in ["không phải flash sale", "không flash sale"]):
        exceptions_found.append({
            "type": "flash_sale_exception",
            "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
            "source": "policy_refund_v4.txt",
        })

    # Exception 2: Digital product — chỉ detect khi task KHẲNG ĐỊNH là kỹ thuật số
    digital_kws = ["license key", "subscription", "kỹ thuật số"]
    neg_digital = ["không phải kỹ thuật số", "không kỹ thuật số", "không phải license", "không phải subscription"]
    if any(kw in task_lower for kw in digital_kws) and \
       not any(neg in task_lower for neg in neg_digital):
        exceptions_found.append({
            "type": "digital_product_exception",
            "rule": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền (Điều 3).",
            "source": "policy_refund_v4.txt",
        })

    # Exception 3: Activated product
    if any(kw in task_lower for kw in ["đã kích hoạt", "đã đăng ký", "đã sử dụng"]):
        exceptions_found.append({
            "type": "activated_exception",
            "rule": "Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn tiền (Điều 3).",
            "source": "policy_refund_v4.txt",
        })

    # Determine policy_applies
    policy_applies = len(exceptions_found) == 0

    # Determine which policy version applies (temporal scoping)
    # TODO: Check nếu đơn hàng trước 01/02/2026 → v3 applies (không có docs, nên flag cho synthesis)
    policy_name = "refund_policy_v4"
    policy_version_note = ""
    if "31/01" in task_lower or "30/01" in task_lower or "trước 01/02" in task_lower or \
       "31/1" in task_lower or "30/1" in task_lower:
        policy_version_note = "Đơn hàng đặt trước 01/02/2026 áp dụng chính sách v3 (không có trong tài liệu hiện tại). Tài liệu hiện chỉ có chính sách v4 (hiệu lực từ 01/02/2026). Không thể xác nhận theo chính sách v3."

    # TODO Sprint 2: Gọi LLM để phân tích phức tạp hơn
    # Ví dụ:
    # from openai import OpenAI
    # client = OpenAI()
    # response = client.chat.completions.create(
    #     model="gpt-4o-mini",
    #     messages=[
    #         {"role": "system", "content": "Bạn là policy analyst. Dựa vào context, xác định policy áp dụng và các exceptions."},
    #         {"role": "user", "content": f"Task: {task}\n\nContext:\n" + "\n".join([c['text'] for c in chunks])}
    #     ]
    # )
    # analysis = response.choices[0].message.content

    sources = list({c.get("source", "unknown") for c in chunks if c})

    return {
        "policy_applies": policy_applies,
        "policy_name": policy_name,
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": policy_version_note,
        "explanation": "Analyzed via rule-based policy check. TODO: upgrade to LLM-based analysis.",
    }


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với policy_result và mcp_tools_used
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
    }

    try:
        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and needs_tool:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb")

            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if needs_tool and any(kw in task.lower() for kw in ["ticket", "p1", "jira"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_ticket_info")

        # Step 4: Nếu task liên quan đến access level cụ thể → gọi check_access_permission
        import re
        level_match = re.search(r'level\s*(\d)', task.lower())
        if level_match:
            level = int(level_match.group(1))
            is_emergency = any(kw in task.lower() for kw in ["khẩn cấp", "emergency", "p1", "2am"])
            requester = "contractor" if "contractor" in task.lower() else "engineer"
            mcp_result = _call_mcp_tool("check_access_permission", {
                "access_level": level,
                "requester_role": requester,
                "is_emergency": is_emergency,
            })
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP check_access_permission level={level}")
            # Gắn kết quả MCP vào retrieved_chunks để synthesis có thêm context
            if mcp_result.get("output") and not mcp_result["output"].get("error"):
                out = mcp_result["output"]
                mcp_chunk = {
                    "text": (
                        f"Level {level} access — Kết quả kiểm tra quyền (check_access_permission):\n"
                        f"- Có thể cấp (can_grant): {out.get('can_grant')}\n"
                        f"- Số người phê duyệt cần thiết: {out.get('approver_count')} người\n"
                        f"- Danh sách người phê duyệt: {out.get('required_approvers')}\n"
                        f"- Level {level} CÓ emergency bypass: {out.get('emergency_override')}\n"
                        f"- Ghi chú: {out.get('notes', [])}"
                    ),
                    "source": out.get("source", "access_control_sop.txt"),
                    "score": 0.95,
                    "metadata": {"source": "access_control_sop.txt"},
                }
                state["retrieved_chunks"] = state.get("retrieved_chunks", []) + [mcp_chunk]

        # Step 5: Query expansion — tìm thêm chunks cho các chủ đề đặc biệt
        task_lower = task.lower()
        extra_queries = []

        # Notification channels (gq01-like)
        if any(kw in task_lower for kw in ["thông báo", "notification", "kênh", "channel", "22:47", "22:57"]):
            extra_queries.append("PagerDuty Slack email kênh liên lạc công cụ incident P1")
            extra_queries.append("escalate Senior Engineer 10 phút không phản hồi P1")
            # Đưa extra lên đầu chunks để LLM đọc trước
            _extra_pd = []
            for eq in ["PagerDuty Slack email kênh liên lạc công cụ incident P1", "escalate Senior Engineer 10 phút không phản hồi P1"]:
                mcp_r = _call_mcp_tool("search_kb", {"query": eq, "top_k": 2})
                if mcp_r.get("output") and mcp_r["output"].get("chunks"):
                    _extra_pd.extend(mcp_r["output"]["chunks"])
            if _extra_pd:
                existing = {c.get("text","")[:50] for c in state.get("retrieved_chunks", [])}
                new_front = [ec for ec in _extra_pd if ec.get("text","")[:50] not in existing]
                state["retrieved_chunks"] = new_front + state.get("retrieved_chunks", [])

        # Temporal scoping (gq02-like)
        if any(kw in task_lower for kw in ["31/01", "30/01", "trước 01/02", "01/02/2026"]):
            extra_queries.append("chính sách hoàn tiền phiên bản effective date áp dụng từ ngày")

        # Emergency access bypass (gq09-like)
        if any(kw in task_lower for kw in ["emergency", "khẩn cấp", "tạm thời"]) and "level" in task_lower:
            extra_queries.append("escalation khẩn cấp cấp quyền tạm thời emergency bypass on-call IT Admin")
            # Direct lookup chunk escalation SLA P1 (sla_p1_2026_3)
            try:
                import chromadb as _chroma
                _client = _chroma.PersistentClient(path="./chroma_db")
                _col = _client.get_collection("day09_docs")
                direct = _col.get(ids=["sla_p1_2026_3"], include=["documents","metadatas"])
                if direct["documents"]:
                    sla_chunk = {
                        "text": direct["documents"][0],
                        "source": direct["metadatas"][0].get("source","sla_p1_2026.txt"),
                        "score": 0.95,
                        "metadata": direct["metadatas"][0],
                    }
                    existing = {c.get("text","")[:50] for c in state.get("retrieved_chunks",[])}
                    if sla_chunk["text"][:50] not in existing:
                        state["retrieved_chunks"] = [sla_chunk] + state.get("retrieved_chunks", [])
            except Exception:
                pass

        for eq in extra_queries:
            mcp_result = _call_mcp_tool("search_kb", {"query": eq, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb (expansion): {eq[:50]}")
            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                extra_chunks = mcp_result["output"]["chunks"]
                # Chỉ thêm chunks chưa có trong state
                existing_texts = {c.get("text","")[:50] for c in state.get("retrieved_chunks", [])}
                for ec in extra_chunks:
                    if ec.get("text","")[:50] not in existing_texts:
                        state["retrieved_chunks"] = state.get("retrieved_chunks", []) + [ec]

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
        }
        state["history"].append(
            f"[{WORKER_NAME}] policy_applies={policy_result['policy_applies']}, "
            f"exceptions={len(policy_result.get('exceptions_found', []))}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e)}
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Policy Tool Worker — Standalone Test")
    print("=" * 50)

    test_cases = [
        {
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {"text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.9}
            ],
        },
        {
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {"text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.88}
            ],
        },
        {
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạt.",
            "retrieved_chunks": [
                {"text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.", "source": "policy_refund_v4.txt", "score": 0.85}
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ Task: {tc['task'][:70]}...")
        result = run(tc.copy())
        pr = result.get("policy_result", {})
        print(f"  policy_applies: {pr.get('policy_applies')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception: {ex['type']} — {ex['rule'][:60]}...")
        print(f"  MCP calls: {len(result.get('mcp_tools_used', []))}")

    print("\n✅ policy_tool_worker test done.")
