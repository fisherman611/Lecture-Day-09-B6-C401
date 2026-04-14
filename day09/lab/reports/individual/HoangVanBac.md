# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hoàng Văn Bắc
**Vai trò trong nhóm:** MCP Owner (mcp_server.py + testing)
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `mcp_server.py`
- Functions tôi implement: `tool_search_kb()`, `tool_get_ticket_info()`, `tool_check_access_permission()`, `tool_create_ticket()`, `dispatch_tool()`, `list_tools()`, `TOOL_SCHEMAS`, `TOOL_REGISTRY`, `MOCK_TICKETS`, `ACCESS_RULES`

Tôi cũng chịu trách nhiệm **standalone testing** cho tất cả workers — verify từng worker chạy độc lập được trước khi kết nối vào graph. Kế thừa từ Day 08: tôi đã làm QA/testing, nên ở Day 09 tôi áp dụng cùng approach — test từng component riêng lẻ trước khi integration test.

Điểm quan trọng nhất của `mcp_server.py`: `check_access_permission` với `ACCESS_RULES` dict — đây là tool được gọi nhiều nhất trong grading questions (gq03, gq09) và quyết định answer có đúng không.

**Bằng chứng:** `mcp_server.py` — comment `# MCP Owner: HoangVanBac` ở đầu file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định: Implement `check_access_permission` với `emergency_can_bypass` per-level thay vì global flag**

Khi thiết kế `ACCESS_RULES`, tôi có 2 cách:
- **Global emergency flag**: `EMERGENCY_BYPASS = True` — tất cả levels đều có bypass khi emergency
- **Per-level flag**: Mỗi level có `emergency_can_bypass` riêng

Tôi chọn per-level vì đây là yêu cầu thực tế trong `access_control_sop.txt`:
- Level 2: CÓ emergency bypass (Line Manager + IT Admin on-call)
- Level 3: KHÔNG có emergency bypass (phải follow quy trình chuẩn)
- Level 4: KHÔNG có emergency bypass

```python
ACCESS_RULES = {
    2: {
        "required_approvers": ["Line Manager", "IT Admin"],
        "emergency_can_bypass": True,
        "emergency_bypass_note": "Level 2 có thể cấp tạm thời với approval đồng thời...",
    },
    3: {
        "required_approvers": ["Line Manager", "IT Admin", "IT Security"],
        "emergency_can_bypass": False,
        "note": "Admin access — không có emergency bypass",
    },
}
```

**Bằng chứng:** gq03 (Level 3, emergency=True): `emergency_override=False` → answer đúng "không có emergency bypass". gq09 (Level 2, emergency=True): `emergency_override=True` → answer đúng "CÓ emergency bypass". Cả 2 đạt FULL.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi: `dispatch_tool()` raise exception thay vì trả về error dict khi tool không tồn tại**

**Symptom:** Khi Nguyễn Như Giáp gọi `_call_mcp_tool("nonexistent_tool", {})` trong policy_tool.py, `dispatch_tool()` raise `KeyError` → policy_tool worker crash → toàn bộ pipeline fail.

**Root cause:** Ban đầu `dispatch_tool()` không có error handling:

```python
# Trước (lỗi):
def dispatch_tool(tool_name, tool_input):
    tool_fn = TOOL_REGISTRY[tool_name]  # KeyError nếu không tồn tại!
    return tool_fn(**tool_input)
```

**Cách sửa:** Thêm check và trả về error dict thay vì raise:

```python
# Sau (đúng):
def dispatch_tool(tool_name, tool_input):
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Tool '{tool_name}' không tồn tại. Available: {list(TOOL_REGISTRY.keys())}"}
    try:
        return TOOL_REGISTRY[tool_name](**tool_input)
    except Exception as e:
        return {"error": f"Tool '{tool_name}' execution failed: {e}"}
```

**Bằng chứng trước/sau:**

Trước: `dispatch_tool("nonexistent", {})` → `KeyError: 'nonexistent'` → pipeline crash.

Sau: `dispatch_tool("nonexistent", {})` → `{"error": "Tool 'nonexistent' không tồn tại..."}` → pipeline tiếp tục, log error vào trace.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất:** `ACCESS_RULES` với per-level emergency bypass — quyết định thiết kế này trực tiếp giúp gq03 và gq09 đạt FULL. Nếu tôi dùng global flag, gq03 sẽ trả lời sai "Level 3 có emergency bypass".

**Tôi làm chưa tốt:** `tool_search_kb()` delegate sang `workers/retrieval.py` — tạo circular dependency tiềm ẩn. Nên implement ChromaDB query trực tiếp trong mcp_server thay vì import từ workers.

**Nhóm phụ thuộc vào tôi:** Nguyễn Như Giáp (policy_tool.py) import `dispatch_tool` từ mcp_server. Nếu `check_access_permission` chưa implement hoặc trả về sai, gq03 và gq09 sẽ fail.

**Tôi phụ thuộc vào:** Vũ Như Đức (retrieval.py) — `tool_search_kb()` gọi `retrieve_dense()` từ retrieval worker. Nếu ChromaDB chưa có data, search_kb trả về empty.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **real MCP HTTP server** bằng FastAPI để nhận bonus +2 điểm. Trace gq09 cho thấy `check_access_permission` được gọi 1 lần với latency ~50ms (in-process mock). Với HTTP server thật, latency sẽ tăng ~20-50ms nhưng architecture sẽ đúng MCP protocol — workers có thể chạy trên máy khác và gọi MCP server qua network.
