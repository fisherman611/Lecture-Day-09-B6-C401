# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Lương Hữu Thành
**Vai trò trong nhóm:** Supervisor Owner
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`
- Functions tôi implement: `AgentState`, `make_initial_state()`, `supervisor_node()`, `route_decision()`, `human_review_node()`, `build_graph()`, `run_graph()`, `save_trace()`

Tôi thiết kế toàn bộ orchestration layer: shared state schema, routing logic, và graph runner. Công việc của tôi là nền tảng để các Worker Owner (Vũ Như Đức, Nguyễn Như Giáp, Vũ Phúc Thành) implement workers và kết nối vào. Nếu `AgentState` thiếu field hoặc `supervisor_node` route sai, toàn bộ pipeline downstream bị ảnh hưởng.

Kế thừa từ Day 08: tôi đã quen với luồng RAG end-to-end, nên việc tách thành supervisor-worker pattern khá tự nhiên — supervisor thay thế vai trò "điều phối" mà trước đây nằm trong `rag_answer()`.

**Bằng chứng:** `graph.py` — toàn bộ file do tôi viết, comment `# Supervisor Owner: LuongHuuThanh` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: Dùng Python thuần (if/else orchestration) thay vì LangGraph**

Nhóm cân nhắc 2 hướng:
- **LangGraph**: StateGraph với conditional edges, built-in checkpointing, interrupt_before cho HITL
- **Python thuần**: if/else routing trong `build_graph()`, không dependency ngoài

Tôi chọn Python thuần vì 3 lý do:
1. LangGraph thêm ~200MB dependency và learning curve trong 4 giờ lab
2. Với 3 workers và routing đơn giản, StateGraph là overkill
3. Python thuần dễ debug hơn — có thể print state bất kỳ lúc nào

Trade-off chấp nhận: không có built-in checkpointing và HITL thật. Nhưng với lab này, HITL placeholder đủ để demo.

**Bằng chứng từ trace:**

```python
# build_graph() trong graph.py
def run(state: AgentState) -> AgentState:
    state = supervisor_node(state)
    route = route_decision(state)
    if route == "policy_tool_worker":
        state = retrieval_worker_node(state)
        state = policy_tool_worker_node(state)
    else:
        state = retrieval_worker_node(state)
    state = synthesis_worker_node(state)
    return state
```

Trace gq01: `latency_ms=16056` — nếu dùng LangGraph, overhead sẽ thêm ~200-500ms mà không có benefit thực tế cho lab này.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: Multi-hop routing — câu có cả SLA lẫn policy keywords bị route sai**

**Symptom:** Câu "Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor" ban đầu route về `retrieval_worker` thay vì `policy_tool_worker`. Answer chỉ trả lời được phần SLA, bỏ sót phần Level 2 access.

**Root cause:** Routing logic dùng `if/elif` — policy keywords check trước, nhưng câu này có cả SLA keyword ("p1") lẫn policy keyword ("level 2"). Khi "p1" match SLA branch trước, policy branch không được check.

**Cách sửa:** Thêm multi-hop detection sau tất cả checks:

```python
has_sla = any(kw in task for kw in sla_keywords)
has_policy = any(kw in task for kw in policy_keywords)
if has_sla and has_policy:
    route = "policy_tool_worker"
    route_reason = "multi-hop: both SLA and policy keywords → cross-doc"
    needs_tool = True
```

**Bằng chứng trước/sau:**

Trước: `supervisor_route: "retrieval_worker"`, answer thiếu Level 2 access info.

Sau: `supervisor_route: "policy_tool_worker"`, `route_reason: "multi-hop: both SLA and policy keywords"`, answer đầy đủ cả SLA lẫn access control. gq09 đạt FULL 16/16.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** Thiết kế `AgentState` schema đầy đủ ngay từ đầu — 18 fields bao gồm `workers_called`, `worker_io_logs`, `mcp_tools_used`, `route_reason`. Điều này giúp các thành viên khác implement workers mà không cần sửa schema sau.

**Tôi làm chưa tốt:** Routing logic ban đầu thiếu multi-hop detection — phải sửa sau khi test gq09. Nếu thiết kế kỹ hơn từ đầu, tiết kiệm được ~30 phút debug.

**Nhóm phụ thuộc vào tôi:** `graph.py` là entry point — nếu `run_graph()` chưa xong, Nguyễn Tiến Thắng không thể chạy `eval_trace.py`, và Trần Anh Tú không có trace để điền `routing_decisions.md`.

**Tôi phụ thuộc vào:** Vũ Như Đức (retrieval.py), Nguyễn Như Giáp (policy_tool.py), Vũ Phúc Thành (synthesis.py) — cần 3 workers implement xong để thay placeholder nodes.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **LLM-based routing classifier** thay keyword matching. Trace gq06 cho thấy câu "probation period muốn làm remote" route đúng về `retrieval_worker` nhưng answer thiếu "Team Lead phê duyệt" — LLM classifier có thể detect intent "HR policy + approval condition" và truyền context hint vào state để synthesis worker biết cần liệt kê đủ điều kiện phê duyệt.
