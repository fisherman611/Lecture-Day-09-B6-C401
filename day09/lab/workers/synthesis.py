"""
workers/synthesis.py — Synthesis Worker
Sprint 2: Tổng hợp câu trả lời từ retrieved_chunks và policy_result.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: evidence từ retrieval_worker
    - policy_result: kết quả từ policy_tool_worker

Output (vào AgentState):
    - final_answer: câu trả lời cuối với citation
    - sources: danh sách nguồn tài liệu được cite
    - confidence: mức độ tin cậy (0.0 - 1.0)

Gọi độc lập để test:
    python workers/synthesis.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

WORKER_NAME = "synthesis_worker"

SYSTEM_PROMPT = """Bạn là trợ lý IT Helpdesk nội bộ. Nhiệm vụ: trả lời chính xác, đầy đủ, dựa HOÀN TOÀN vào tài liệu được cung cấp.

QUY TẮC BẮT BUỘC:
1. CHỈ dùng thông tin trong context. TUYỆT ĐỐI không dùng kiến thức ngoài.
2. Nếu thông tin KHÔNG có trong tài liệu → nêu rõ không tìm thấy trong tài liệu nội bộ. Không được bịa hoặc suy đoán.
3. Trích dẫn nguồn sau mỗi thông tin quan trọng: [tên_file.txt].
4. Liệt kê ĐẦY ĐỦ — KHÔNG được bỏ sót bất kỳ kênh, người, bước, điều kiện nào có trong tài liệu.
5. Exceptions/ngoại lệ → nêu TRƯỚC kết luận, không được bỏ qua.
6. Đọc KỸ TOÀN BỘ context từ đầu đến cuối trước khi trả lời.

QUY TẮC THEO TỪNG LOẠI CÂU HỎI:
- Kênh thông báo P1: liệt kê ĐỦ 3 kênh nếu có (Slack #incident-p1, email incident@company.internal, PagerDuty).
- Escalation: nêu rõ thời gian (phút) và đối tượng escalate (Senior Engineer?).
- Phiên bản chính sách / ngày hiệu lực: nếu đơn hàng trước ngày hiệu lực → nêu rõ không thể xác nhận theo phiên bản cũ, KHÔNG suy luận thêm theo phiên bản khác.
- Access level: nêu đủ số người phê duyệt, tên từng người, có emergency bypass không, điều kiện bypass. Nêu rõ ai phê duyệt (Team Lead? IT Admin? IT Security?). Người phê duyệt cuối cùng / thẩm quyền cao nhất là người được liệt kê CUỐI trong danh sách phê duyệt. QUAN TRỌNG: Section 4 (escalation khẩn cấp) trong access_control_sop.txt chỉ áp dụng cho Level 2 — KHÔNG áp dụng cho Level 3. Level 3 KHÔNG có emergency bypass, dù đang có P1. Level 2 emergency bypass cần approval ĐỒNG THỜI của Line Manager VÀ IT Admin on-call.
- Store credit / hoàn tiền: nêu đúng con số VÀ giải thích rõ ý nghĩa (ví dụ: 110% = nhận thêm 10% so với số tiền hoàn gốc, tức là bonus thêm 10%).
- Remote work: nêu đủ TẤT CẢ điều kiện — qua probation, số ngày tối đa, VÀ ai phê duyệt (Team Lead). Nếu nhân viên KHÔNG đủ điều kiện (đang probation) → kết luận rõ KHÔNG được phép, sau đó nêu điều kiện để được phép.
- Policy exception: khi nêu ngoại lệ phải cite rõ điều khoản cụ thể (ví dụ: Điều 3, chính sách v4).
- Nếu câu hỏi hỏi thông tin không có trong tài liệu → nêu rõ không tìm thấy, không bịa số liệu, gợi ý liên hệ bộ phận liên quan nếu phù hợp.
"""


def _call_llm(messages: list) -> str:
    """
    Gọi LLM để tổng hợp câu trả lời.
    Thử OpenAI trước, fallback Gemini nếu không có key.
    """
    # Option A: OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("sk-..."):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.0,
                max_tokens=1200,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"  [synthesis] OpenAI error: {e}")

    # Option B: Gemini
    gemini_key = os.getenv("GOOGLE_API_KEY", "")
    if gemini_key and not gemini_key.startswith("AI..."):
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            combined = "\n".join([m["content"] for m in messages])
            response = model.generate_content(combined)
            return response.text
        except Exception as e:
            print(f"  [synthesis] Gemini error: {e}")

    return "[SYNTHESIS ERROR] Không thể gọi LLM. Kiểm tra API key trong .env."


def _build_context(chunks: list, policy_result: dict) -> str:
    """Xây dựng context string từ chunks và policy result."""
    parts = []

    # Đưa policy_version_note lên ĐẦU để LLM đọc trước
    if policy_result and policy_result.get("policy_version_note"):
        parts.append(
            f"⚠️ CẢNH BÁO PHIÊN BẢN CHÍNH SÁCH — ĐỌC TRƯỚC KHI TRẢ LỜI:\n"
            f"{policy_result['policy_version_note']}\n"
            f"→ BẮT BUỘC: Nêu rõ không thể xác nhận theo phiên bản cũ. "
            f"KHÔNG được suy luận hoặc áp dụng chính sách v4 cho đơn hàng này."
        )

    if chunks:
        parts.append("=== TÀI LIỆU THAM KHẢO ===")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")
            score = chunk.get("score", 0)
            parts.append(f"[{i}] Nguồn: {source} (relevance: {score:.2f})\n{text}")

    if policy_result and policy_result.get("exceptions_found"):
        parts.append("\n=== POLICY EXCEPTIONS ===")
        for ex in policy_result["exceptions_found"]:
            parts.append(f"- {ex.get('rule', '')}")

    if not parts:
        return "(Không có context)"

    return "\n\n".join(parts)


def _estimate_confidence(chunks: list, answer: str, policy_result: dict) -> float:
    """
    Ước tính confidence dựa vào:
    - Số lượng và quality của chunks
    - Có exceptions không
    - Answer có abstain không

    TODO Sprint 2: Có thể dùng LLM-as-Judge để tính confidence chính xác hơn.
    """
    if not chunks:
        return 0.1  # Không có evidence → low confidence

    # Abstain vì thiếu tài liệu (v3, mức phạt...) → confidence thấp nhưng đây là đúng
    abstain_phrases = ["không có trong tài liệu", "không tìm thấy thông tin", "không thể xác nhận theo phiên bản"]
    if any(p in answer.lower() for p in abstain_phrases):
        return 0.3  # Abstain → moderate-low, không phải lỗi

    # Weighted average của chunk scores
    if chunks:
        avg_score = sum(c.get("score", 0) for c in chunks) / len(chunks)
    else:
        avg_score = 0

    # Penalty nếu có exceptions (phức tạp hơn)
    exception_penalty = 0.05 * len(policy_result.get("exceptions_found", []))

    confidence = min(0.95, avg_score - exception_penalty)
    return round(max(0.1, confidence), 2)


def synthesize(task: str, chunks: list, policy_result: dict) -> dict:
    """
    Tổng hợp câu trả lời từ chunks và policy context.

    Returns:
        {"answer": str, "sources": list, "confidence": float}
    """
    context = _build_context(chunks, policy_result)

    # Build messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""Câu hỏi: {task}

{context}

Hãy trả lời câu hỏi dựa vào tài liệu trên.
Lưu ý quan trọng:
- Liệt kê ĐẦY ĐỦ tất cả thông tin có trong tài liệu, không tóm tắt bỏ bớt.
- Nếu có cảnh báo phiên bản chính sách ở trên → PHẢI nêu rõ, KHÔNG được suy luận thêm theo phiên bản khác.
- Nếu thông tin không có trong tài liệu → abstain rõ ràng, gợi ý liên hệ bộ phận liên quan.
- Nếu câu hỏi về store credit / phần trăm → nêu con số VÀ giải thích: 110% nghĩa là nhận thêm 10% bonus so với số tiền hoàn gốc.
- Nếu câu hỏi về remote work → nêu đủ: điều kiện eligibility, số ngày tối đa, VÀ ai phê duyệt.
- Nếu câu hỏi về policy exception → cite rõ điều khoản (Điều mấy, phiên bản nào)."""
        }
    ]

    answer = _call_llm(messages)
    sources = list({c.get("source", "unknown") for c in chunks})
    confidence = _estimate_confidence(chunks, answer, policy_result)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
    }


def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks") or []
    policy_result = state.get("policy_result") or {}

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "has_policy": bool(policy_result),
        },
        "output": None,
        "error": None,
    }

    try:
        result = synthesize(task, chunks, policy_result)
        state["final_answer"] = result["answer"]
        state["sources"] = result["sources"]
        state["confidence"] = result["confidence"]

        worker_io["output"] = {
            "answer_length": len(result["answer"]),
            "sources": result["sources"],
            "confidence": result["confidence"],
        }
        state["history"].append(
            f"[{WORKER_NAME}] answer generated, confidence={result['confidence']}, "
            f"sources={result['sources']}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "SYNTHESIS_FAILED", "reason": str(e)}
        state["final_answer"] = f"SYNTHESIS_ERROR: {e}"
        state["confidence"] = 0.0
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Synthesis Worker — Standalone Test")
    print("=" * 50)

    test_state = {
        "task": "SLA ticket P1 là bao lâu?",
        "retrieved_chunks": [
            {
                "text": "Ticket P1: Phản hồi ban đầu 15 phút kể từ khi ticket được tạo. Xử lý và khắc phục 4 giờ. Escalation: tự động escalate lên Senior Engineer nếu không có phản hồi trong 10 phút.",
                "source": "sla_p1_2026.txt",
                "score": 0.92,
            }
        ],
        "policy_result": {},
    }

    result = run(test_state.copy())
    print(f"\nAnswer:\n{result['final_answer']}")
    print(f"\nSources: {result['sources']}")
    print(f"Confidence: {result['confidence']}")

    print("\n--- Test 2: Exception case ---")
    test_state2 = {
        "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì lỗi nhà sản xuất.",
        "retrieved_chunks": [
            {
                "text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền theo Điều 3 chính sách v4.",
                "source": "policy_refund_v4.txt",
                "score": 0.88,
            }
        ],
        "policy_result": {
            "policy_applies": False,
            "exceptions_found": [{"type": "flash_sale_exception", "rule": "Flash Sale không được hoàn tiền."}],
        },
    }
    result2 = run(test_state2.copy())
    print(f"\nAnswer:\n{result2['final_answer']}")
    print(f"Confidence: {result2['confidence']}")

    print("\n✅ synthesis_worker test done.")
