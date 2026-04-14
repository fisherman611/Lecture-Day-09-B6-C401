# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Môn:** AI in Action (AICB-P1)  
**Ngày:** 2026-04-14

> So sánh Day 08 (single-agent RAG) với Day 09 (supervisor-worker).
> Số liệu Day 09 lấy từ `artifacts/eval_report.json` sau khi chạy `python eval_trace.py`.
> Số liệu Day 08 lấy từ `eval.py` Day 08 (nếu có) hoặc ước tính từ baseline.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | ~0.72 | ~0.82 | +0.10 | Day 09 có policy check bổ sung |
| Avg latency (ms) | ~800ms | ~1400ms | +600ms | Day 09 gọi thêm workers + MCP |
| Abstain rate (%) | ~10% | ~13% | +3% | Day 09 abstain đúng hơn (ít hallucinate) |
| Multi-hop accuracy | ~40% | ~75% | +35% | Day 09 cross-doc retrieval tốt hơn |
| Routing visibility | ✗ Không có | ✓ Có route_reason | N/A | Key advantage của Day 09 |
| Debug time (estimate) | ~15 phút | ~5 phút | -10 phút | Trace rõ ràng giúp debug nhanh hơn |
| Exception detection | Manual/None | Tự động (rule-based) | N/A | flash_sale, digital_product, activated |

> **Lưu ý:** Số liệu Day 08 là ước tính baseline. Chạy `python eval.py` trong Day 08 lab để có số liệu chính xác.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | ~85% | ~85% |
| Latency | ~800ms | ~1400ms |
| Observation | Đủ dùng, nhanh hơn | Chậm hơn do overhead workers |

**Kết luận:** Multi-agent KHÔNG cải thiện câu đơn giản. Thậm chí chậm hơn ~600ms do overhead của supervisor + worker dispatch. Single agent Day 08 đủ tốt cho loại câu này.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | ~40% | ~75% |
| Routing visible? | ✗ | ✓ |
| Observation | Thường chỉ lấy được 1 doc | Gọi retrieval + policy_tool, cross-reference 2 docs |

**Kết luận:** Multi-agent cải thiện rõ rệt cho câu multi-hop. Câu gq09 (P1 + Level 2 access) là ví dụ điển hình: Day 08 thường chỉ trả lời được 1 trong 2 phần, Day 09 trả lời đủ cả hai nhờ `policy_tool_worker` gọi `check_access_permission` MCP tool.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | ~10% | ~13% |
| Hallucination cases | ~2/15 | ~1/15 |
| Observation | Đôi khi bịa thông tin khi context yếu | Confidence thấp → abstain rõ ràng hơn |

**Kết luận:** Day 09 abstain tốt hơn nhờ `_estimate_confidence()` trong synthesis worker. Khi `retrieved_chunks=[]`, synthesis luôn trả về "Không đủ thông tin" thay vì hallucinate.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai → đọc toàn bộ rag_answer() → không rõ lỗi ở retrieve hay generate
Không có trace → phải thêm print() thủ công để debug
Thời gian ước tính: ~15 phút để tìm ra 1 bug
```

### Day 09 — Debug workflow
```
Khi answer sai → đọc trace JSON → xem supervisor_route + route_reason
  → Nếu route sai → sửa keyword list trong supervisor_node()
  → Nếu retrieval sai → python workers/retrieval.py (test độc lập)
  → Nếu synthesis sai → python workers/synthesis.py (test độc lập)
Thời gian ước tính: ~5 phút để tìm ra 1 bug
```

**Ví dụ debug thực tế trong lab:**

Câu q12 (temporal scoping — đơn 31/01/2026): pipeline ban đầu trả lời theo policy v4 thay vì flag "cần xác nhận v3". Debug: xem trace → `policy_result.policy_version_note` có ghi "Đơn hàng đặt trước 01/02/2026 áp dụng chính sách v3" → synthesis không đọc field này. Fix: cập nhật `_build_context()` trong synthesis.py để include `policy_version_note` vào context block.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa `rag_answer()` và prompt | Thêm tool vào `mcp_server.py` + route rule |
| Thêm 1 domain mới | Phải retrain/re-prompt toàn bộ | Thêm 1 worker mới + contract |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa `workers/retrieval.py` độc lập |
| A/B test một phần | Phải clone toàn pipeline | Swap worker, giữ nguyên phần còn lại |

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 LLM calls | Day 09 LLM calls |
|---------|-------------|-------------|
| Simple query | 1 (generate) | 1 (synthesis) |
| Policy query | 1 (generate) | 1 (synthesis) + 0 MCP (rule-based) |
| Multi-hop query | 1 (generate) | 1 (synthesis) + MCP tool calls (no LLM) |

**Nhận xét về cost-benefit:**

Day 09 không tốn thêm LLM calls so với Day 08 trong hầu hết trường hợp. MCP tools là rule-based (không gọi LLM). Chi phí tăng chủ yếu ở latency (~600ms overhead) do Python function dispatch, không phải API cost. Với câu multi-hop, Day 09 tốt hơn đáng kể mà không tốn thêm token.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở:**

1. **Multi-hop queries** — cross-document reasoning tốt hơn rõ rệt (+35% accuracy)
2. **Debuggability** — trace rõ ràng, test worker độc lập, debug nhanh hơn ~3x
3. **Extensibility** — thêm MCP tool hoặc worker mới không ảnh hưởng phần còn lại
4. **Exception detection** — policy_tool_worker phát hiện flash_sale, digital_product tự động

**Multi-agent kém hơn hoặc không khác biệt ở:**

1. **Simple queries** — chậm hơn ~600ms do overhead, không cải thiện accuracy
2. **Cost** — không tốn thêm LLM calls, nhưng code phức tạp hơn để maintain

**Khi nào KHÔNG nên dùng multi-agent:**

Khi use case chỉ có câu hỏi đơn giản, single-document, không cần cross-reference. Ví dụ: FAQ chatbot đơn giản với 1 loại tài liệu. Single agent Day 08 đủ dùng và nhanh hơn.

**Nếu tiếp tục phát triển:**

Thêm LLM-based routing classifier thay vì keyword matching để xử lý được câu hỏi dùng từ đồng nghĩa hoặc paraphrase. Thêm confidence-based HITL: nếu `confidence < 0.4` → tự động trigger human review thay vì trả lời không chắc.
