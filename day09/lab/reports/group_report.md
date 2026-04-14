# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** B6-C401
**Thành viên:**
| Tên | Vai trò | Email |
|-----|---------|-------|
| Lương Hữu Thành | Supervisor Owner | 26ai.thanhlh@vinuni.edu.vn |
| Vũ Như Đức | Worker Owner (Retrieval + Synthesis) | 26ai.ducvn@vinuni.edu.vn |
| Nguyễn Như Giáp | Worker Owner (Policy Tool + Contracts) | 26ai.giapnn@vinuni.edu.vn |
| Nguyễn Tiến Thắng | Trace & Docs Owner (eval_trace.py) | 26ai.thangnt@vinuni.edu.vn |
| Trần Anh Tú | Trace & Docs Owner (3 docs templates) | 26ai.tuta@vinuni.edu.vn |
| Hoàng Văn Bắc | MCP Owner (mcp_server.py + testing) | 26ai.bachv@vinuni.edu.vn |
| Vũ Phúc Thành | MCP Owner (MCP integration + env) | 26ai.thanhvp@vinuni.edu.vn |

**Ngày nộp:** 14/04/2026
**Repo:** https://github.com/fisherman611/Lecture-Day-09-B6-C401

---

## 1. Kiến trúc nhóm đã xây dựng

**Hệ thống tổng quan:**

Nhóm xây dựng hệ thống **Supervisor-Worker** bằng Python thuần (không dùng LangGraph) gồm 3 workers: `retrieval_worker`, `policy_tool_worker`, `synthesis_worker`. Supervisor (`graph.py`) phân tích task bằng keyword matching và route sang worker phù hợp. MCP server (`mcp_server.py`) expose 4 tools: `search_kb`, `get_ticket_info`, `check_access_permission`, `create_ticket`. Toàn bộ pipeline lưu trace JSON cho mỗi run vào `artifacts/traces/`.

**Routing logic cốt lõi:**

Supervisor dùng keyword matching theo 3 nhóm:
- Policy keywords (`hoàn tiền`, `refund`, `flash sale`, `cấp quyền`, `level 2/3`) → `policy_tool_worker`
- SLA keywords (`p1`, `sla`, `ticket`, `escalation`) → `retrieval_worker`
- Unknown error code (`err-`) → `human_review`
- Multi-hop (cả SLA lẫn policy keywords) → `policy_tool_worker` (cross-doc)

Routing accuracy trên 15 test questions: **9/9 loại câu route đúng**.

**MCP tools đã tích hợp:**

- `search_kb`: Semantic search ChromaDB, dùng trong policy_tool khi cần query expansion
- `get_ticket_info`: Tra cứu ticket mock (P1-LATEST), gọi khi task chứa "ticket/p1/jira"
- `check_access_permission`: Kiểm tra điều kiện cấp quyền theo level + emergency flag — key tool cho gq03 và gq09
- `create_ticket`: Tạo ticket mock (dùng cho future extension)

Ví dụ trace gq09: `mcp_tools_used = ["check_access_permission (level=2, is_emergency=True)", "search_kb (escalation emergency bypass)"]`

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định: Keyword-based routing vs LLM classifier cho supervisor**

**Bối cảnh vấn đề:**

Supervisor cần phân loại task vào đúng worker. Có 2 hướng: (1) gọi LLM để classify intent, (2) dùng keyword matching rule-based. Nhóm phải chọn trước Sprint 1.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| LLM classifier | Xử lý được paraphrase, alias | Thêm ~800ms latency, tốn token, có thể sai |
| Keyword matching | Nhanh (~2ms), deterministic, dễ debug | Miss nếu user dùng từ đồng nghĩa |
| Hybrid (keyword + LLM fallback) | Tốt nhất cả hai | Phức tạp hơn, khó test |

**Phương án đã chọn: Keyword matching**

Lý do: Với 5 tài liệu nội bộ có domain hẹp (SLA, refund, access control, HR, FAQ), keyword matching đủ chính xác. Trace 15 test questions cho thấy 9/9 loại câu route đúng. Latency supervisor chỉ ~2ms thay vì ~800ms nếu dùng LLM. Quan trọng hơn: `route_reason` luôn rõ ràng và traceable — đáp ứng yêu cầu SCORING.md "route_reason không được rỗng".

**Bằng chứng từ trace:**

```json
{
  "supervisor_route": "policy_tool_worker",
  "route_reason": "multi-hop: both SLA and policy keywords → policy_tool_worker for cross-doc",
  "workers_called": ["retrieval_worker", "policy_tool_worker", "synthesis_worker"],
  "latency_ms": 7669
}
```

---

## 3. Kết quả grading questions

**Tổng điểm raw ước tính: 92 / 96**

**Câu pipeline xử lý tốt nhất:**

- **gq09 (16 điểm, multi-hop)** — FULL 16/16. Pipeline route sang `policy_tool_worker`, gọi `check_access_permission(level=2, is_emergency=True)` qua MCP, đồng thời retrieve SLA P1 escalation. Trace ghi đủ 2 workers. Answer nêu đủ cả SLA notification (Slack, email, PagerDuty, 10 phút → Senior Engineer) lẫn Level 2 emergency bypass (Line Manager + IT Admin on-call).
- **gq07 (10 điểm, abstain)** — FULL 10/10. Pipeline abstain đúng "Không đủ thông tin trong tài liệu nội bộ", không hallucinate con số phạt.
- **gq10 (10 điểm, Flash Sale exception)** — FULL 10/10. Policy worker detect `flash_sale_exception` đúng, không bị đánh lừa bởi "lỗi nhà sản xuất".

**Câu pipeline partial:**

- **gq06 (8 điểm)** — PARTIAL 4/8. Answer nêu đúng "không được remote trong probation" và "2 ngày/tuần" nhưng bỏ sót "cần Team Lead phê duyệt". Root cause: LLM tóm tắt bỏ điều kiện phê duyệt dù chunk có đủ thông tin.

**Câu gq07 (abstain):** Pipeline trả về "Không đủ thông tin trong tài liệu nội bộ" — đúng hoàn toàn. Confidence = 0.30 (abstain threshold). Không hallucinate bất kỳ con số phạt nào.

**Câu gq09 (multi-hop):** Trace ghi đủ 2 workers (`retrieval_worker` + `policy_tool_worker`). MCP `check_access_permission` được gọi với `is_emergency=True` → trả về `emergency_override=True` cho Level 2. Answer đầy đủ cả 2 phần.

---

## 4. So sánh Day 08 vs Day 09

**Metric thay đổi rõ nhất:**

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) |
|--------|----------------------|---------------------|
| Multi-hop accuracy | ~40% | ~95% (gq09 FULL) |
| Routing visibility | Không có | Có `route_reason` mỗi trace |
| Debug time (ước tính) | ~15 phút/bug | ~5 phút/bug |
| Avg latency | ~800ms | ~3-7s (overhead workers) |

**Điều nhóm bất ngờ nhất:**

Multi-agent không tốn thêm LLM calls so với Day 08 — MCP tools đều rule-based, không gọi LLM. Chi phí tăng chủ yếu ở latency Python dispatch (~600ms overhead), không phải API cost. Với câu multi-hop, Day 09 tốt hơn rõ rệt mà không tốn thêm token.

**Trường hợp multi-agent không giúp ích:**

Câu đơn giản single-document (gq04, gq05, gq08) — Day 09 chậm hơn ~600ms do overhead supervisor + worker dispatch, nhưng accuracy không cải thiện so với Day 08 RAG đơn giản.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Lương Hữu Thành | graph.py — AgentState, supervisor_node, routing logic, build_graph | 1 |
| Vũ Như Đức | workers/retrieval.py — retrieve_dense, query expansion, ChromaDB | 2 |
| Nguyễn Như Giáp | workers/policy_tool.py — analyze_policy, MCP calls, exception detection | 2, 3 |
| Nguyễn Tiến Thắng | eval_trace.py — run_test_questions, analyze_traces, grading runner | 4 |
| Trần Anh Tú | docs/ — system_architecture.md, routing_decisions.md, single_vs_multi_comparison.md | 4 |
| Hoàng Văn Bắc | mcp_server.py — 4 tools, dispatch_tool, TOOL_SCHEMAS, standalone testing | 3 |
| Vũ Phúc Thành | workers/synthesis.py — _call_llm, _build_context, .env setup, ChromaDB index | 2 |

**Điều nhóm làm tốt:**

- Phân công rõ ràng theo module — mỗi người có file riêng, không conflict
- MCP `check_access_permission` giải quyết được câu gq09 (câu khó nhất, 16 điểm)
- Trace format đầy đủ tất cả required fields theo SCORING.md

**Điều nhóm làm chưa tốt:**

- gq06 bị partial vì LLM tóm tắt bỏ "Team Lead phê duyệt" — cần thêm instruction cụ thể hơn trong SYSTEM_PROMPT
- Latency cao (~7s cho câu multi-hop) do nhiều MCP calls — cần cache hoặc batch

**Nếu làm lại:**

Implement ChromaDB index từ đầu buổi thay vì build on-the-fly, tiết kiệm ~30 phút setup.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

1. **LLM-based routing classifier** thay keyword matching — trace gq06 cho thấy câu "probation period muốn làm remote" route về `retrieval_worker` đúng nhưng thiếu context phê duyệt. LLM classifier có thể detect intent "HR policy + approval condition" và route với context richer hơn.

2. **Confidence-based HITL** — khi `confidence < 0.4`, tự động trigger human review thay vì trả lời không chắc. Evidence: gq07 confidence=0.30 abstain đúng, nhưng gq06 confidence=0.68 vẫn thiếu chi tiết → threshold cần tinh chỉnh.
