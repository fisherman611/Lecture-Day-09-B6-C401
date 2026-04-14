# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Vũ Phúc Thành
**Vai trò trong nhóm:** MCP Owner (Synthesis Worker + Environment Setup)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/synthesis.py`, `.env` setup, ChromaDB index build script
- Functions tôi implement: `_call_llm()`, `_build_context()`, `_estimate_confidence()`, `synthesize()`, `run()`

Tôi cũng chịu trách nhiệm **build ChromaDB index** từ 5 tài liệu trong `data/docs/` — đây là prerequisite để toàn bộ pipeline chạy được. Kế thừa từ Day 08: tôi đã setup `.env`, ChromaDB config, và dependency management. Ở Day 09, tôi áp dụng cùng approach nhưng thêm chunking strategy tốt hơn — tách FAQ theo từng Q&A riêng thay vì chunk theo paragraph.

**Bằng chứng:** `workers/synthesis.py` — comment `# MCP Owner: VuPhucThanh` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: Đưa `policy_version_note` lên đầu context thay vì cuối**

Trong `_build_context()`, tôi có 2 cách sắp xếp context:
- **Cuối**: Chunks trước, policy notes sau
- **Đầu**: Policy notes trước, chunks sau

Tôi chọn đưa `policy_version_note` lên đầu với warning rõ ràng:

```python
if policy_result and policy_result.get("policy_version_note"):
    parts.append(
        f"⚠️ LƯU Ý QUAN TRỌNG VỀ PHIÊN BẢN CHÍNH SÁCH:\n"
        f"{policy_result['policy_version_note']}\n"
        f"→ Phải nêu rõ điều này trong câu trả lời."
    )
```

Lý do: LLM có xu hướng đọc phần đầu context kỹ hơn phần cuối ("lost in the middle" problem). Nếu `policy_version_note` ở cuối, LLM có thể bỏ qua và trả lời theo v4.

Trade-off: Context dài hơn một chút, nhưng đảm bảo LLM đọc được warning quan trọng.

**Bằng chứng:** gq02 ban đầu trả lời theo v4 "được hoàn tiền" dù `policy_version_note` đã được set. Sau khi đưa note lên đầu context, gq02 đạt FULL 10/10 với answer "không thể xác nhận theo chính sách v3".

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: `_call_llm()` không load `.env` → OPENAI_API_KEY không được đọc → SYNTHESIS ERROR**

**Symptom:** `graph.py` gọi `load_dotenv()` ở đầu file, nhưng `workers/synthesis.py` import trước khi `load_dotenv()` chạy. Kết quả: `os.getenv("OPENAI_API_KEY")` trả về `None` → `_call_llm()` trả về `"[SYNTHESIS ERROR] Không thể gọi LLM"`.

**Root cause:** Python module import order — `synthesis.py` được import khi `graph.py` load, trước khi `load_dotenv()` được gọi trong `if __name__ == "__main__"` block.

**Cách sửa:** Thêm `load_dotenv()` trực tiếp vào đầu `workers/synthesis.py`:

```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env ngay khi module được import

WORKER_NAME = "synthesis_worker"
```

**Bằng chứng trước/sau:**

Trước: Tất cả 3 test queries trong `graph.py` trả về `"[SYNTHESIS ERROR] Không thể gọi LLM. Kiểm tra API key trong .env."`, confidence=0.0.

Sau: `graph.py` chạy đúng, answer thật từ GPT-4o-mini, confidence=0.57-0.68.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** ChromaDB index build với chunking strategy tốt — tách FAQ theo từng Q&A riêng (13 chunks từ `it_helpdesk_faq.txt`) thay vì chunk theo paragraph. Điều này giúp gq08 (mật khẩu 90 ngày) retrieve đúng chunk Q&A thay vì chunk section header.

**Tôi làm chưa tốt:** `_estimate_confidence()` dùng average chunk score — không phản ánh đúng quality của answer. Câu gq06 confidence=0.68 nhưng answer thiếu "Team Lead phê duyệt" — confidence cao nhưng completeness thấp.

**Nhóm phụ thuộc vào tôi:** ChromaDB index là prerequisite — nếu tôi chưa build index, `retrieve_dense()` của Vũ Như Đức trả về empty, toàn bộ pipeline abstain. Tôi cũng là người duy nhất biết collection name (`day09_docs`) và chunking strategy.

**Tôi phụ thuộc vào:** Nguyễn Như Giáp (policy_tool.py) — `policy_result` và `policy_version_note` là input của `_build_context()`. Nếu policy_tool detect sai exception, context tôi build sẽ sai.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **LLM-as-Judge confidence scoring** thay vì average chunk score. Trace gq06 cho thấy confidence=0.68 nhưng answer thiếu "Team Lead phê duyệt" — LLM judge có thể đánh giá completeness thực sự và trả về confidence thấp hơn, trigger HITL hoặc retry với prompt cụ thể hơn. Evidence: SCORING.md bonus +1 cho "confidence score thực tế (không hard-code)".
