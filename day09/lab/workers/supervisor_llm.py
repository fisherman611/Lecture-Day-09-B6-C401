"""
supervisor_llm.py — LLM-based Supervisor (Production version)

Thay thế keyword matching trong graph.py bằng LLM classifier.
LLM phân tích intent và trả về structured JSON routing decision.

Dùng:
    from workers.supervisor_llm import llm_route
    route_decision = llm_route(task)
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

# Worker descriptions — LLM dùng để chọn route
WORKER_DESCRIPTIONS = {
    "retrieval_worker": (
        "Dùng khi câu hỏi cần tra cứu thông tin đơn giản từ tài liệu: "
        "SLA timeline, quy trình, FAQ, HR policy, số liệu cụ thể. "
        "Không cần kiểm tra exception hay cross-document logic."
    ),
    "policy_tool_worker": (
        "Dùng khi câu hỏi cần: (1) kiểm tra exception/ngoại lệ của policy "
        "(Flash Sale, digital product, activated product), (2) access control "
        "với emergency bypass, (3) temporal scoping (đơn hàng trước/sau ngày hiệu lực), "
        "(4) cross-document reasoning từ 2+ tài liệu."
    ),
    "human_review": (
        "Dùng khi câu hỏi chứa mã lỗi không rõ, thông tin không đủ context, "
        "hoặc yêu cầu quyết định có rủi ro cao cần human approval."
    ),
}

ROUTING_PROMPT = """Bạn là supervisor của hệ thống multi-agent IT Helpdesk.
Phân tích câu hỏi và chọn worker phù hợp nhất.

Workers có sẵn:
{worker_descriptions}

Trả về JSON với format:
{{
  "route": "<tên worker>",
  "reason": "<giải thích ngắn tại sao chọn worker này>",
  "needs_tool": <true nếu cần gọi MCP tool, false nếu không>,
  "risk_high": <true nếu câu hỏi có rủi ro cao cần cẩn thận>
}}

Câu hỏi: {task}"""


def llm_route(task: str) -> dict:
    """
    Dùng LLM để phân tích intent và quyết định route.

    Returns:
        dict với keys: route, reason, needs_tool, risk_high
    """
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key or openai_key.startswith("sk-..."):
        # Fallback về keyword routing nếu không có key
        return _fallback_route(task)

    worker_desc_text = "\n".join(
        f"- {name}: {desc}"
        for name, desc in WORKER_DESCRIPTIONS.items()
    )

    prompt = ROUTING_PROMPT.format(
        worker_descriptions=worker_desc_text,
        task=task,
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",   # dùng mini cho routing — nhanh + rẻ
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        result = json.loads(response.choices[0].message.content)

        # Validate route value
        valid_routes = list(WORKER_DESCRIPTIONS.keys())
        if result.get("route") not in valid_routes:
            result["route"] = "retrieval_worker"

        return result

    except Exception as e:
        print(f"  [supervisor_llm] LLM routing failed: {e}, falling back to keyword")
        return _fallback_route(task)


def _fallback_route(task: str) -> dict:
    """Keyword-based fallback khi LLM không available."""
    task_lower = task.lower()

    policy_kws = ["flash sale", "license key", "kỹ thuật số", "subscription",
                  "đã kích hoạt", "store credit", "cấp quyền", "access level",
                  "level 3", "level 2", "level 1", "hoàn tiền không",
                  "được hoàn tiền", "31/01", "30/01"]
    error_kws = ["err-", "error code", "mã lỗi không rõ"]

    if any(kw in task_lower for kw in error_kws):
        return {"route": "human_review", "reason": "unknown error code", "needs_tool": False, "risk_high": True}
    if any(kw in task_lower for kw in policy_kws):
        return {"route": "policy_tool_worker", "reason": "policy keyword detected", "needs_tool": True, "risk_high": False}
    return {"route": "retrieval_worker", "reason": "default retrieval", "needs_tool": False, "risk_high": False}


if __name__ == "__main__":
    tests = [
        "SLA ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì lỗi nhà sản xuất — được không?",
        "Cần cấp Level 3 access khẩn cấp lúc 2am. Quy trình?",
        "ERR-403-AUTH là lỗi gì?",
        "Nhân viên probation có được làm remote không?",
        "Đơn hàng ngày 31/01/2026 áp dụng chính sách nào?",
    ]

    print("LLM Supervisor Routing Test")
    print("=" * 60)
    for q in tests:
        result = llm_route(q)
        print(f"Q: {q[:60]}")
        print(f"   route={result['route']} | needs_tool={result['needs_tool']}")
        print(f"   reason={result['reason']}")
        print()
