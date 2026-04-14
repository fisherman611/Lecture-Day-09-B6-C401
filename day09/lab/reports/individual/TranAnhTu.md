# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Trần Anh Tú
**Vai trò trong nhóm:** Trace & Docs Owner (3 docs templates)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `docs/system_architecture.md`, `docs/routing_decisions.md`, `docs/single_vs_multi_comparison.md`
- Nội dung tôi viết: sơ đồ pipeline ASCII art, bảng Shared State Schema, phân tích 4 routing decisions thực tế từ trace, bảng metrics so sánh Day 08 vs Day 09

Kế thừa từ Day 08: tôi đã viết `architecture.md` và `tuning-log.md`. Ở Day 09, tôi áp dụng cùng approach — lấy thông tin trực tiếp từ code và trace thay vì mô tả chung chung. Điểm khác biệt: Day 09 có trace JSON nên tôi có thể trích dẫn `route_reason` thực tế thay vì phải ước tính.

**Bằng chứng:** 3 files docs đều có comment `# Documentation Owner: TranAnhTu` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: Dùng ASCII art thay vì Mermaid diagram cho system_architecture.md**

Ở Day 08, tôi dùng Mermaid diagram trong `architecture.md`. Ở Day 09, tôi chuyển sang ASCII art.

Lý do:
1. Mermaid cần renderer hỗ trợ — GitHub render được nhưng nhiều markdown viewer không render
2. ASCII art readable trực tiếp trong terminal và text editor — không cần tool ngoài
3. Với supervisor-worker pattern có 3 workers + MCP, ASCII art dễ thể hiện hơn Mermaid flowchart

```
User Request (task)
       │
       ▼
┌──────────────────────────────────────┐
│           Supervisor Node            │
│  - Phân tích task keywords           │
│  - Quyết định route                  │
└──────────────┬───────────────────────┘
               │
        [route_decision]
               │
    ┌──────────┼──────────────┐
    │          │              │
    ▼          ▼              ▼
retrieval  policy_tool    human_review
_worker    _worker        _node
```

Trade-off: ASCII art khó update khi thêm worker mới. Mermaid dễ maintain hơn về lâu dài.

**Bằng chứng:** `docs/system_architecture.md` — sơ đồ ASCII art được giảng viên review và không yêu cầu chỉnh sửa.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: routing_decisions.md ban đầu dùng giả định thay vì trace thực tế**

**Symptom:** Draft đầu tiên của `routing_decisions.md` tôi viết routing decisions dựa trên logic code (`supervisor_node()`) thay vì đọc trace files thực tế. SCORING.md yêu cầu "ít nhất 3 quyết định routing thực tế từ trace — không phải giả định".

**Root cause:** Tôi viết docs trước khi Nguyễn Tiến Thắng chạy xong `eval_trace.py` và có trace files.

**Cách sửa:** Chờ `artifacts/traces/` có đủ files, sau đó đọc trace bằng script:

```python
import json, os
traces_dir = 'artifacts/traces'
for f in os.listdir(traces_dir)[:4]:
    with open(f'{traces_dir}/{f}') as fp:
        t = json.load(fp)
    print(f'Task: {t["task"][:60]}')
    print(f'Route: {t["supervisor_route"]} | Reason: {t["route_reason"]}')
    print(f'Answer: {t["final_answer"][:80]}')
```

Sau đó điền 4 routing decisions thực tế vào `routing_decisions.md` — bao gồm cả câu multi-hop (gq09-like) với `route_reason: "multi-hop: both SLA and policy keywords"`.

**Bằng chứng trước/sau:**

Trước: routing_decisions.md có placeholder "___" và giả định.

Sau: 4 routing decisions với task thực tế, route_reason từ trace, confidence score, và nhận xét.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** `single_vs_multi_comparison.md` — bảng metrics có số liệu thực tế từ `artifacts/eval_report.json`, không ước tính. Phân tích debuggability (15 phút vs 5 phút) dựa trên kinh nghiệm thực tế debug gq03 trong lab.

**Tôi làm chưa tốt:** Số liệu Day 08 trong bảng so sánh là ước tính (~0.72 avg confidence) vì không có thời gian chạy lại `eval.py` từ Day 08. Nên ghi rõ "ước tính" thay vì để số liệu trông như đo thực tế.

**Nhóm phụ thuộc vào tôi:** 3 docs files là deliverable bắt buộc theo SCORING.md (10 điểm Group Documentation). Nếu tôi không điền xong trước 18:00, nhóm mất điểm docs.

**Tôi phụ thuộc vào:** Nguyễn Tiến Thắng (eval_trace.py) — cần trace files và `eval_report.json` để điền số liệu thực tế vào docs.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ chạy lại `eval.py` từ Day 08 với cùng 15 test questions của Day 09 để có số liệu so sánh chính xác. Trace gq09 Day 09 đạt FULL 16/16 — nếu có số liệu Day 08 thực tế cho câu tương đương (q13 trong Day 08 test questions), bảng so sánh multi-hop accuracy sẽ thuyết phục hơn nhiều thay vì ước tính "~40% vs ~95%".
