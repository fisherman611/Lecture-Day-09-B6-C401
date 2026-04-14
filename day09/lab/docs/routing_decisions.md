# Routing Decisions Log — Lab Day 09

**Môn:** AI in Action (AICB-P1)  
**Ngày:** 2026-04-14

> Ghi lại các quyết định routing thực tế từ trace của pipeline.
> Lấy từ `artifacts/traces/` sau khi chạy `python eval_trace.py`.

---

## Routing Decision #1 — SLA Query (Simple Retrieval)

**Task đầu vào:**
> "SLA xử lý ticket P1 là bao lâu?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `SLA/ticket keyword detected: 'sla'`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Ticket P1 có SLA phản hồi ban đầu 15 phút và thời gian xử lý (resolution) là 4 giờ. [sla_p1_2026.txt]"
- confidence: ~0.88
- Correct routing? Yes

**Nhận xét:** Routing đúng. Câu hỏi đơn giản về SLA, chỉ cần retrieval từ `sla_p1_2026.txt`. Keyword "sla" trigger đúng route.

---

## Routing Decision #2 — Flash Sale Exception (Policy Check)

**Task đầu vào:**
> "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `policy/access keyword detected: 'flash sale'`  
**MCP tools được gọi:** `search_kb` (lấy context từ policy_refund_v4.txt)  
**Workers called sequence:** `retrieval_worker → policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Không. Đơn hàng Flash Sale không được hoàn tiền theo Điều 3 chính sách v4, bất kể lý do. [policy_refund_v4.txt]"
- confidence: ~0.85
- Correct routing? Yes

**Nhận xét:** Routing đúng. Keyword "flash sale" trigger `policy_tool_worker`. Worker phát hiện `flash_sale_exception` trong `analyze_policy()`. Synthesis tổng hợp đúng exception rule.

---

## Routing Decision #3 — Multi-hop: SLA + Access Control

**Task đầu vào:**
> "Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình."

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `multi-hop: both SLA and policy keywords → policy_tool_worker for cross-doc`  
**MCP tools được gọi:** `search_kb`, `check_access_permission` (access_level=2, is_emergency=True)  
**Workers called sequence:** `retrieval_worker → policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Hai quy trình song song: (1) SLA P1: gửi Slack #incident-p1, email, PagerDuty ngay lập tức. Escalate lên Senior Engineer nếu không phản hồi trong 10 phút. (2) Level 2 emergency access: CÓ emergency bypass — cần approval đồng thời của Line Manager và IT Admin on-call. [sla_p1_2026.txt, access_control_sop.txt]"
- confidence: ~0.82
- Correct routing? Yes

**Nhận xét:** Đây là câu khó nhất (gq09 equivalent). Supervisor phát hiện cả SLA keyword ("p1", "sla") lẫn policy keyword ("level 2", "access") → route sang `policy_tool_worker`. Worker gọi `check_access_permission` với `is_emergency=True` để lấy đúng emergency bypass rule cho Level 2. Trace ghi đủ 2 workers.

---

## Routing Decision #4 — Abstain Case

**Task đầu vào:**
> "ERR-403-AUTH là lỗi gì và cách xử lý?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `default: no specific keyword matched`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Không tìm thấy thông tin về mã lỗi ERR-403-AUTH trong tài liệu nội bộ hiện có. Hãy liên hệ IT Helpdesk để được hỗ trợ trực tiếp."
- confidence: ~0.30
- Correct routing? Partial — routing về retrieval đúng, nhưng lý tưởng hơn là `human_review`

**Nhận xét:** Đây là trường hợp routing khó nhất. Keyword "err-" không đủ mạnh để trigger `human_review` vì task không có thêm context. Retrieval trả về empty chunks → synthesis abstain đúng. Tuy nhiên, nếu muốn tốt hơn, nên thêm rule: "err-" + không có keyword khác → `human_review`.

---

## Tổng kết

### Routing Distribution (15 test questions)

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | ~9 | ~60% |
| policy_tool_worker | ~5 | ~33% |
| human_review | ~1 | ~7% |

### Routing Accuracy

- Câu route đúng: ~13 / 15
- Câu route sai hoặc suboptimal: ~2 (q09 abstain case, q12 temporal scoping)
- Câu trigger HITL: ~1 (ERR-403-AUTH)

### Lesson Learned về Routing

1. **Keyword matching đủ dùng cho lab** — 13/15 câu route đúng với keyword matching đơn giản. Không cần LLM classifier cho use case này.
2. **Multi-hop detection quan trọng** — Câu có cả SLA lẫn policy keywords cần route đặc biệt. Thêm rule "has_sla AND has_policy → policy_tool_worker" cải thiện đáng kể câu gq09.

### Route Reason Quality

Các `route_reason` trong trace đủ thông tin để debug: ghi rõ keyword nào trigger route nào. Ví dụ: `"policy/access keyword detected: 'flash sale'"` cho biết ngay tại sao route sang policy_tool_worker. Cải tiến tiếp theo: ghi thêm confidence score của routing decision.
