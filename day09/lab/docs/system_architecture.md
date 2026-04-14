# System Architecture — Lab Day 09

**Môn:** AI in Action (AICB-P1)  
**Ngày:** 2026-04-14  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker (Python thuần, không dùng LangGraph)

**Lý do chọn pattern này thay vì single agent:**

Day 08 dùng một hàm `rag_answer()` xử lý toàn bộ: retrieve → generate. Khi pipeline trả lời sai, không rõ lỗi ở retrieval hay generation. Day 09 tách thành các workers độc lập, mỗi worker có contract rõ ràng, test được riêng lẻ. Supervisor giữ routing logic tách biệt khỏi domain logic.

---

## 2. Sơ đồ Pipeline

```
User Request (task)
       │
       ▼
┌──────────────────────────────────────┐
│           Supervisor Node            │
│  - Phân tích task keywords           │
│  - Quyết định route                  │
│  - Set: supervisor_route,            │
│         route_reason, risk_high,     │
│         needs_tool                   │
└──────────────┬───────────────────────┘
               │
        [route_decision]
               │
    ┌──────────┼──────────────┐
    │          │              │
    ▼          ▼              ▼
retrieval  policy_tool    human_review
_worker    _worker        _node
    │          │              │
    │    (gọi retrieval       │
    │     trước, rồi          │
    │     check policy)       │
    │          │              │
    └──────────┴──────────────┘
               │
               ▼
      ┌─────────────────┐
      │ Synthesis Worker │
      │ - Gọi LLM        │
      │ - Grounded prompt│
      │ - Citation [src] │
      │ - Confidence est │
      └────────┬─────────┘
               │
               ▼
    Output: final_answer, sources,
            confidence, trace
```

**MCP Integration (trong policy_tool_worker):**
```
policy_tool_worker
       │
       ├── _call_mcp_tool("search_kb", ...)
       ├── _call_mcp_tool("get_ticket_info", ...)
       └── _call_mcp_tool("check_access_permission", ...)
              │
              ▼
         mcp_server.py
         dispatch_tool()
              │
         TOOL_REGISTRY
         ├── tool_search_kb()       → ChromaDB
         ├── tool_get_ticket_info() → Mock data
         ├── tool_check_access_permission() → Rule-based
         └── tool_create_ticket()   → Mock
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| Nhiệm vụ | Phân tích task, quyết định route, không tự trả lời domain |
| Input | `task` (câu hỏi từ user) |
| Output | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| Routing logic | Keyword matching: policy/access keywords → policy_tool_worker; SLA/ticket → retrieval_worker; unknown error → human_review |
| HITL condition | `risk_high=True` AND unknown error code (ERR-xxx) |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| Nhiệm vụ | Embed query, query ChromaDB, trả về top-k chunks |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (offline) |
| Top-k | 3 (mặc định) |
| Stateless | Yes — không giữ state giữa các lần gọi |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| Nhiệm vụ | Kiểm tra policy exceptions, gọi MCP tools khi cần |
| MCP tools gọi | `search_kb`, `get_ticket_info`, `check_access_permission` |
| Exception cases xử lý | flash_sale, digital_product (license key), activated_product, temporal scoping (v3 vs v4) |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| LLM model | `gpt-4o-mini` (OpenAI) hoặc `gemini-1.5-flash` (Gemini) |
| Temperature | 0.1 (low để grounded) |
| Grounding strategy | SYSTEM_PROMPT ép "chỉ dùng context được cung cấp" |
| Abstain condition | `retrieved_chunks=[]` → trả về "Không đủ thông tin trong tài liệu nội bộ" |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query`, `top_k` | `chunks`, `sources`, `total_found` |
| `get_ticket_info` | `ticket_id` | ticket details, notifications_sent |
| `check_access_permission` | `access_level`, `requester_role`, `is_emergency` | `can_grant`, `required_approvers`, `emergency_override` |
| `create_ticket` | `priority`, `title`, `description` | `ticket_id`, `url`, `created_at` |

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| `task` | str | Câu hỏi đầu vào | supervisor đọc |
| `supervisor_route` | str | Worker được chọn | supervisor ghi |
| `route_reason` | str | Lý do route (không được rỗng) | supervisor ghi |
| `risk_high` | bool | Flag rủi ro cao | supervisor ghi |
| `needs_tool` | bool | Cần gọi MCP tool | supervisor ghi |
| `hitl_triggered` | bool | Đã trigger HITL | human_review ghi |
| `retrieved_chunks` | list | Evidence từ retrieval | retrieval ghi, synthesis đọc |
| `retrieved_sources` | list | Unique source filenames | retrieval ghi |
| `policy_result` | dict | Kết quả kiểm tra policy | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list | Tool calls đã thực hiện | policy_tool ghi |
| `final_answer` | str | Câu trả lời cuối | synthesis ghi |
| `sources` | list | Sources được cite | synthesis ghi |
| `confidence` | float | Mức tin cậy 0.0-1.0 | synthesis ghi |
| `workers_called` | list | Danh sách workers đã gọi | mỗi worker append |
| `worker_io_logs` | list | Log I/O của từng worker | mỗi worker append |
| `history` | list | Lịch sử các bước | mọi node append |
| `latency_ms` | int | Thời gian xử lý | graph ghi |
| `run_id` | str | ID của run | khởi tạo khi tạo state |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở retrieval hay generation | Dễ hơn — test từng worker độc lập, xem trace |
| Thêm capability mới | Phải sửa toàn `rag_answer()` | Thêm MCP tool hoặc worker mới |
| Routing visibility | Không có | Có `route_reason` trong mỗi trace |
| Multi-hop queries | Một lần retrieve, có thể thiếu cross-doc | Có thể gọi retrieval + policy_tool tuần tự |
| Extend external API | Hard-code trong pipeline | Thêm tool vào `mcp_server.py` |

**Quan sát thực tế từ lab:**

Câu hỏi multi-hop như "Ticket P1 lúc 2am + cần cấp Level 2 access" yêu cầu cross-reference giữa `sla_p1_2026.txt` và `access_control_sop.txt`. Single agent Day 08 có thể bỏ sót một trong hai. Multi-agent Day 09 route sang `policy_tool_worker`, worker này gọi cả `search_kb` (lấy SLA context) lẫn `check_access_permission` (kiểm tra access rule), rồi synthesis tổng hợp cả hai.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Routing dùng keyword matching** — dễ bị miss nếu user dùng từ đồng nghĩa. Cải tiến: dùng LLM classifier cho routing.
2. **Confidence estimation đơn giản** — dựa vào average chunk score, không phải LLM-as-Judge. Cải tiến: dùng LLM để đánh giá faithfulness thực sự.
3. **MCP là mock in-process** — không phải HTTP server thật. Cải tiến: implement FastAPI server với `mcp` library để test real MCP protocol.
