# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Như Giáp
**Vai trò trong nhóm:** Worker Owner (Policy Tool Worker + Contracts)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/policy_tool.py`, `contracts/worker_contracts.yaml`
- Functions tôi implement: `_call_mcp_tool()`, `analyze_policy()`, `run()` — bao gồm toàn bộ exception detection logic, MCP integration, và query expansion

Tôi cũng chịu trách nhiệm cập nhật `contracts/worker_contracts.yaml` — đánh dấu `status: done` cho tất cả workers sau khi implement xong, và ghi notes về implementation details.

Kế thừa từ Day 08: tôi đã implement guardrails và prompt engineering cho grounded generation. Ở Day 09, tôi áp dụng tư duy tương tự cho policy analysis — rule-based exception detection thay vì để LLM tự suy luận, tránh hallucinate policy rules.

**Bằng chứng:** `workers/policy_tool.py` — comment `# Worker Owner: NguyenNhuGiap` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: Rule-based exception detection thay vì LLM-based policy analysis**

Trong `analyze_policy()`, tôi có 2 lựa chọn:
- **LLM-based**: Gửi task + chunks cho LLM, yêu cầu phân tích policy và detect exceptions
- **Rule-based**: Keyword matching để detect flash_sale, digital_product, activated_product exceptions

Tôi chọn rule-based vì:
1. Policy exceptions có pattern rõ ràng và finite — không cần LLM để detect "flash sale" hay "license key"
2. LLM-based tốn thêm 1 API call (~800ms) và có thể hallucinate exception không có trong docs
3. Rule-based deterministic — dễ test, dễ debug, dễ thêm exception mới

Trade-off quan trọng: thêm **negative detection** — không chỉ check "flash sale" mà còn check "không phải flash sale" để tránh false positive:

```python
if ("flash sale" in task_lower) and \
   not any(neg in task_lower for neg in ["không phải flash sale"]):
    exceptions_found.append(...)
```

**Bằng chứng:** gq02 ban đầu bị false positive flash_sale_exception vì task nói "không phải Flash Sale" — sau khi thêm negative detection, gq02 đạt FULL 10/10 với `policy_version_note` đúng.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: gq02 false positive exception — task nói "không phải Flash Sale" nhưng policy_tool vẫn detect flash_sale_exception**

**Symptom:** gq02 ("đơn 31/01/2026, không phải Flash Sale, không phải kỹ thuật số") bị `policy_result.exceptions_found = [flash_sale_exception, digital_product_exception]` — sai hoàn toàn. LLM nhận context sai → trả lời theo v4 thay vì flag temporal scoping.

**Root cause:** `analyze_policy()` check `"flash sale" in task_lower` — đúng là task có chứa "flash sale" (trong câu "không phải Flash Sale"), nhưng đây là negation, không phải affirmation.

**Cách sửa:**

```python
# Trước:
if "flash sale" in task_lower:
    exceptions_found.append(...)

# Sau:
if ("flash sale" in task_lower) and \
   not any(neg in task_lower for neg in ["không phải flash sale", "không flash sale"]):
    exceptions_found.append(...)
```

Tương tự cho digital_product exception.

**Bằng chứng trước/sau:**

Trước: `exceptions_found = [flash_sale_exception, digital_product_exception]`, answer trả lời theo v4 "được hoàn tiền".

Sau: `exceptions_found = []`, `policy_version_note = "Đơn hàng đặt trước 01/02/2026 áp dụng chính sách v3..."`. gq02 FULL 10/10.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** MCP integration trong `run()` — Step 4 gọi `check_access_permission` khi detect "level X" trong task, inject kết quả MCP vào `retrieved_chunks` như một chunk có score=0.95. Điều này giúp gq03 và gq09 đạt FULL mà không cần thay đổi synthesis worker.

**Tôi làm chưa tốt:** Query expansion trong Step 5 gọi nhiều MCP `search_kb` calls (3-4 calls/câu) → latency tăng đáng kể cho câu multi-hop. Nên cache kết quả search_kb hoặc batch queries.

**Nhóm phụ thuộc vào tôi:** `policy_result` và `mcp_tools_used` là output của tôi — Vũ Phúc Thành (synthesis) cần `policy_result.exceptions_found` và `policy_result.policy_version_note` để build context đúng. Nếu tôi detect sai exception, synthesis sẽ trả lời sai.

**Tôi phụ thuộc vào:** Hoàng Văn Bắc (mcp_server.py) — `_call_mcp_tool()` của tôi import `dispatch_tool` từ mcp_server. Nếu `check_access_permission` chưa implement, Step 4 sẽ fail.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ upgrade `analyze_policy()` sang **LLM-based analysis** cho temporal scoping. Trace gq02 cho thấy rule-based detect đúng "31/01" → set `policy_version_note`, nhưng LLM đôi khi vẫn trả lời theo v4 thay vì flag "không thể confirm theo v3". LLM-based analysis với explicit prompt "Nếu đơn hàng đặt trước effective date của tài liệu, phải nêu rõ không thể confirm" sẽ đáng tin cậy hơn.
