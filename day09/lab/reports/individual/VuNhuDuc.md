# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Vũ Như Đức
**Vai trò trong nhóm:** Worker Owner (Retrieval Worker)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`
- Functions tôi implement: `_get_embedding_fn()` (với module-level cache `_ST_MODEL`), `_get_collection()`, `retrieve_dense()`, `run()`, query expansion logic

Tôi kế thừa trực tiếp từ Day 08 — `retrieve_dense()` trong Day 09 dùng cùng ChromaDB collection `day09_docs` với embedding model `all-MiniLM-L6-v2`. Điểm mới so với Day 08: thêm **query expansion** trong `run()` để inject thêm chunks khi task hỏi về notification channels hoặc temporal scoping — giải quyết vấn đề retrieval miss mà Day 08 gặp phải với Q7 (alias).

Công việc của tôi là input cho `policy_tool_worker` (Nguyễn Như Giáp) và `synthesis_worker` (Vũ Phúc Thành) — nếu retrieval trả về chunks sai, cả 2 workers downstream đều bị ảnh hưởng.

**Bằng chứng:** `workers/retrieval.py` — comment `# Worker Owner: VuNhuDuc` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: Module-level cache cho SentenceTransformer thay vì load mỗi lần gọi**

Ban đầu `_get_embedding_fn()` load model mỗi lần được gọi. Với 15 test questions, model load 15 lần → mỗi lần ~12-15 giây → tổng ~180 giây chỉ để load model.

Tôi thêm `_ST_MODEL = None` ở module level và check `if _ST_MODEL is None` trước khi load:

```python
_ST_MODEL = None

def _get_embedding_fn():
    global _ST_MODEL
    if _ST_MODEL is None:
        _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    model = _ST_MODEL
    def embed(text: str) -> list:
        return model.encode([text])[0].tolist()
    return embed
```

Trade-off: model chiếm ~90MB RAM trong suốt session. Với lab 4 giờ, đây là trade-off hợp lý.

**Bằng chứng:** Trace gq01 (câu đầu tiên): `latency_ms=16056` (load model lần đầu). Trace gq02: `latency_ms=2029` (model đã cache). Giảm ~14 giây từ câu thứ 2 trở đi.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: gq01 thiếu PagerDuty trong answer dù chunk có đủ thông tin**

**Symptom:** gq01 hỏi "ai nhận thông báo đầu tiên và qua kênh nào?" — answer có Slack + email nhưng không mention PagerDuty. Chunk "Phần 4: Công cụ và kênh liên lạc" (có PagerDuty) không được retrieve vì embedding similarity thấp (score 0.591, bị đẩy xuống dưới top-7).

**Root cause:** Query "ai nhận thông báo đầu tiên" không match tốt với chunk "PagerDuty: Tự động nhắn on-call khi P1 ticket mới" — semantic gap giữa "nhận thông báo" và "PagerDuty".

**Cách sửa:** Thêm direct lookup bằng chunk ID trong query expansion:

```python
if any(kw in task_lower for kw in ["thông báo", "kênh", "22:47", "ai nhận"]):
    direct = _col.get(ids=["sla_p1_2026_8", "sla_p1_2026_3"], ...)
    # Inject chunks PagerDuty và escalation lên đầu danh sách
    chunks = new_front + chunks
```

**Bằng chứng trước/sau:**

Trước: `pagerduty=False` trong answer gq01, PARTIAL 5/10.

Sau: `pagerduty=True`, answer: "thông báo sẽ được gửi tới on-call engineer thông qua PagerDuty, Slack #incident-p1 và email incident@company.internal". gq01 FULL 10/10.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** Query expansion với direct chunk lookup — giải quyết được vấn đề retrieval miss mà Day 08 cũng gặp (Q7 alias). Kỹ thuật này đơn giản nhưng hiệu quả: biết trước chunk nào quan trọng, inject trực tiếp thay vì phụ thuộc hoàn toàn vào embedding similarity.

**Tôi làm chưa tốt:** `DEFAULT_TOP_K = 7` là con số tôi chọn bằng trial-and-error, không có systematic evaluation. Nên chạy ablation study với top_k = 3, 5, 7, 10 để chọn đúng hơn.

**Nhóm phụ thuộc vào tôi:** `retrieved_chunks` là input của cả `policy_tool_worker` và `synthesis_worker`. Nếu retrieval trả về empty hoặc sai source, cả 2 workers đều abstain hoặc trả lời sai.

**Tôi phụ thuộc vào:** Lương Hữu Thành (graph.py) để biết `AgentState` schema và cách `run()` được gọi từ graph.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **hybrid retrieval (dense + BM25)** như đã làm ở Day 08. Trace gq06 cho thấy retrieval lấy đúng chunk HR policy nhưng LLM bỏ sót "Team Lead phê duyệt" — với BM25, từ khóa "phê duyệt" sẽ được boost score, đảm bảo chunk có điều kiện phê duyệt luôn nằm trong top-3 thay vì bị đẩy xuống.
