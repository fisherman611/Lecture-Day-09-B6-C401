# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Tiến Thắng
**Vai trò trong nhóm:** Trace & Docs Owner (eval_trace.py)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `eval_trace.py`
- Functions tôi implement: `run_test_questions()`, `run_grading_questions()`, `analyze_traces()`, `compare_single_vs_multi()`, `save_eval_report()`, CLI argument parsing

Tôi cũng chịu trách nhiệm đảm bảo trace format đúng theo SCORING.md — tất cả required fields (`run_id`, `task`, `supervisor_route`, `route_reason`, `workers_called`, `mcp_tools_used`, `retrieved_sources`, `final_answer`, `confidence`, `hitl_triggered`, `latency_ms`) phải có trong mỗi trace file.

Kế thừa từ Day 08: tôi đã thiết kế test questions và LLM-as-Judge scoring. Ở Day 09, tôi chuyển sang trace-based evaluation — thay vì chấm điểm từng metric, tôi đọc trace để phân tích routing distribution, MCP usage, và so sánh với Day 08.

**Bằng chứng:** `eval_trace.py` — comment `# Trace Owner: NguyenTienThang` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: JSONL format cho grading_run thay vì JSON array**

Khi thiết kế `run_grading_questions()`, tôi chọn JSONL (1 JSON object mỗi dòng) thay vì JSON array cho `artifacts/grading_run.jsonl`.

Lý do:
1. **Streaming write**: Mỗi câu xong là ghi ngay — nếu pipeline crash ở câu 8/10, 7 câu trước vẫn được lưu. JSON array phải ghi toàn bộ khi kết thúc.
2. **Incremental read**: Giảng viên có thể đọc từng dòng mà không cần parse toàn bộ file
3. **SCORING.md yêu cầu JSONL** — đây là format bắt buộc

Trade-off: JSONL không valid JSON nếu đọc toàn bộ file — phải dùng `json.loads(line)` thay vì `json.load(f)`.

**Bằng chứng từ code:**

```python
with open(output_file, "w", encoding="utf-8") as out:
    for q in questions:
        result = run_graph(q["question"])
        record = { "id": q["id"], "question": ..., "answer": ..., ... }
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"✓ {q['id']}: {q['question'][:60]}...")
```

Khi test pipeline crash ở gq07, 6 câu trước (gq01-gq06) vẫn được lưu đầy đủ trong JSONL.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: `analyze_traces()` đọc cả trace cũ từ các lần chạy trước, làm sai metrics**

**Symptom:** Sau nhiều lần chạy `eval_trace.py`, `artifacts/traces/` tích lũy 38+ trace files. `analyze_traces()` đọc tất cả → `total_traces=38` thay vì 15 (số câu test questions). Routing distribution bị sai vì tính cả trace cũ.

**Root cause:** `analyze_traces()` không filter theo run session — đọc tất cả `.json` files trong thư mục.

**Cách sửa:** Thêm `run_id` prefix filter và chỉ đọc traces từ run hiện tại:

```python
# Trong run_test_questions(), lưu run_id
session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M')}"

# Trong analyze_traces(), filter theo session
trace_files = [f for f in os.listdir(traces_dir)
               if f.endswith(".json") and session_id in f]
```

Hoặc đơn giản hơn: truyền `trace_files` list từ `run_test_questions()` sang `analyze_traces()` thay vì scan toàn bộ thư mục.

**Bằng chứng trước/sau:**

Trước: `total_traces=38`, routing distribution sai.

Sau: `total_traces=15`, routing distribution đúng: `retrieval_worker: 8/15 (53%), policy_tool_worker: 7/15 (47%)`.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** `run_grading_questions()` với error handling — khi pipeline crash, ghi `"answer": "PIPELINE_ERROR: [mô tả lỗi]"` thay vì crash toàn bộ script. Điều này đảm bảo nộp được partial results trước deadline 18:00.

**Tôi làm chưa tốt:** `compare_single_vs_multi()` dùng số liệu Day 08 ước tính thay vì chạy thực tế — không có thời gian chạy lại `eval.py` từ Day 08 để lấy baseline chính xác.

**Nhóm phụ thuộc vào tôi:** `artifacts/grading_run.jsonl` là deliverable chính để nộp điểm. Nếu tôi không chạy xong trước 18:00, nhóm mất 30 điểm grading questions.

**Tôi phụ thuộc vào:** Lương Hữu Thành (graph.py) — `run_graph()` là function tôi gọi trong mỗi iteration. Nếu graph chưa kết nối workers thật, tôi chỉ có placeholder answers.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **LLM-as-Judge scoring** cho grading questions — tương tự Day 08 nhưng adapted cho multi-agent. Trace gq06 cho thấy answer đúng về nội dung nhưng thiếu "Team Lead phê duyệt" — LLM judge có thể detect partial completeness này và cho điểm PARTIAL thay vì FULL, giúp nhóm biết chính xác điểm nào cần cải thiện trước khi nộp.
