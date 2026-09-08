# Kịch bản trình bày SQL MVP

Bản audit 17 slide trong `208.pdf` so với code và số liệu benchmark thật, kèm script nói cho từng slide sau khi đã sửa.

- Nguồn code: `src/branch_sql_MVP`
- Số liệu: `data/eval/sql_mvp/benchmark`
- Thời lượng đề xuất: 12–14 phút

---

## Tình trạng chung

Phần pipeline offline (slide 3–7, 12–13) chỉ lệch ở mức chi tiết. Phần GraphRAG (slide 8–11) đang mô tả một hệ thống khác với hệ thống đã viết. Phần kết quả (slide 14–15) đang dùng số của lần chạy cũ.

| | Số lượng | Nội dung |
|---|---|---|
| Lệch nặng | 4 | Role extract, chế độ chunk General, Leiden phân cấp, Global Query |
| Số liệu sai | 2 | Slide 14 và 15 đang trích kết quả trước khi đổi luật chấm |
| Sửa nhỏ | 7 | Sai tên thư viện, sai đường dẫn output, thiếu tham số thật |
| Nên thêm | 2 | Rerank và giao thức chấm leave-one-out đang bị bỏ trắng |

### Bốn chỗ phải sửa trước khi trình bày

Đây là những chỗ nếu bị hỏi sâu sẽ không trả lời được, vì trong repo không có đoạn code nào tương ứng.

| Slide nói | Code thật | Ở đâu |
|---|---|---|
| Extract gán 6 `role` ngữ nghĩa | Chỉ 3 loại: heading / table / text | `offline/extract.py` |
| Chunk có chế độ General và Parent-Child | Chỉ một luồng parent-child | `offline/chunk.py` |
| Hierarchical Leiden ra community phân cấp | `greedy_modularity`, một tầng phẳng | `offline/graph.py:209` |
| Global Query map-reduce community report | Chưa có; graph chỉ là collection thứ ba | `online/retrieval.py` |

---

## Số liệu thật để thay vào slide 14–15

Điểm tổng của luồng Normal là `union_f1`, tính trên hợp của hai vế docs và SQL. Điểm graph là trung bình có trọng số của ba tỉ lệ cấu trúc.

### Normal · Dev · 33 case · knowledge p1

| Cấu hình | docs@5 | sql@3 | union recall | union prec | điểm |
|---|---|---|---|---|---|
| **hybrid · rrf_k=5 · 0.1/0.9** | **0.467** | **0.949** | **0.960** | **0.440** | **0.578** |
| hybrid · rrf_k=5 · 0.3/0.7 | 0.477 | 0.914 | 0.970 | 0.436 | 0.574 |
| keyword | 0.486 | 0.949 | 0.960 | 0.423 | 0.559 |
| semantic | 0.396 | 0.929 | 0.960 | 0.370 | 0.514 |

Dòng in đậm là cấu hình được khoá và ghi vào `normal_locked.json`.

### Normal · Test · 14 case · cấu hình đã khoá

| Knowledge | docs@5 | sql@3 | union recall | union prec | điểm |
|---|---|---|---|---|---|
| p1 — DOCX + testcase | 0.405 | 0.970 | 0.988 | 0.505 | 0.653 |
| p2 — PDF + testcase | 0.506 | 0.970 | 0.988 | 0.415 | 0.561 |

### GraphRAG · Dev · 33 case · 195 node, 196 cạnh

| Thuật toán | community | node cô lập | complete | connected | same comm. | điểm |
|---|---|---|---|---|---|---|
| **greedy_modularity** | **60** | **51** | **1.000** | **1.000** | **0.394** | **0.818** |
| louvain r=0.5 | 57 | 51 | 1.000 | 1.000 | 0.212 | 0.764 |
| louvain r=1.0 | 59 | 51 | 1.000 | 1.000 | 0.212 | 0.764 |
| louvain r=1.5 | 62 | 51 | 1.000 | 1.000 | 0.212 | 0.764 |
| louvain r=2.0 | 64 | 51 | 1.000 | 1.000 | 0.212 | 0.764 |

Dev chỉ dùng graph tài liệu, không nạp graph SQL sample, để câu dev không tự tìm thấy chính mình.

### GraphRAG · Test · 14 case · graph docs + SQL

| Knowledge | node | cạnh | community | cô lập | connected | same comm. | điểm |
|---|---|---|---|---|---|---|---|
| p1 — DOCX | 392 | 562 | 66 | 47 | 0.786 | 0.071 | 0.657 |
| p2 — PDF | 401 | 553 | 59 | 41 | 0.786 | 0.071 | 0.657 |

`graph_score = 0.4·complete + 0.3·connected + 0.3·same_community`. Cả hai knowledge đều đạt table_coverage 1.0.

---

## Script từng slide

Mỗi slide gồm phần cần sửa trên slide và phần lời nói. Phần lời nói viết để đọc thành tiếng, có thể cắt bớt câu cuối nếu cháy giờ.

---

### Slide 1 — Tiêu đề · 0:40 · sửa phụ đề

**Cần chỉnh**

- **Sửa** — Ba mục dưới tiêu đề nên là ba phần thật của bài: Pipeline offline, Hybrid retrieval, Hai luồng đánh giá. Chữ "Knowledge Base" không xuất hiện lại ở slide nào.
- **Thêm** — Ghi rõ phạm vi là retrieval, không phải sinh SQL. Hệ thống hiện dừng ở việc lấy đúng ngữ cảnh.

**Script**

Em trình bày đề tài xây dựng và đánh giá hệ thống retrieval cho bài toán Text-to-SQL. Đầu vào là tài liệu mô tả bảng bất động sản, cùng một file testcase SQL. Đầu ra là ngữ cảnh được lấy ra để đưa cho mô hình sinh câu lệnh.

Cần nói rõ ngay từ đầu: phạm vi của MVP này là vế retrieval. Em không đo chất lượng câu SQL sinh ra, mà đo xem hệ thống có lấy đúng bảng và đúng mẫu SQL liên quan hay không. Bài gồm ba phần: pipeline offline bảy bước, cơ chế hybrid retrieval, và hai luồng đánh giá độc lập.

---

### Slide 2 — Slide trống, nên làm sơ đồ tổng quan · 0:30

**Cần chỉnh**

- **Thêm** — Vẽ đúng thứ tự trong `offline/pipeline.py`: preprocess → extract → link → chunk → **graph** → embed → index. Graph nằm giữa chunk và embed, không nằm sau index.
- **Thêm** — Tách nhánh online ở cuối: query → hybrid → rerank → ba vế docs / sql / graph.

**Script**

Đây là toàn cảnh hệ thống. Bên trái là luồng offline chạy một lần cho mỗi tài liệu, gồm bảy bước, mỗi bước ghi ra một artifact riêng nên có thể chạy lại từng bước mà không phải làm lại từ đầu.

Điểm đáng chú ý là bước dựng graph nằm ngay sau bước chunk, trước embed. Lý do là graph được xây từ chính các chunk, và bản tóm tắt cụm của graph cũng được embed rồi index như một loại nội dung nữa. Bên phải là luồng online, nhận câu hỏi tiếng Việt và trả về ba nhóm ngữ cảnh.

---

### Slide 3 — Phase 1 · Parse · 0:50 · 3 lỗi chi tiết

**Cần chỉnh**

- **Sai** — Bỏ Mammoth. DOCX chỉ đi qua `MarkItDown`, xem `preprocess/docx_parse.py:22`.
- **Sai** — `openpyxi` → `openpyxl`.
- **Sai** — Đường dẫn output thật là `data/processed/sql_mvp/markdown/<doc_id>.md`, không có thư mục `p<project>`.
- **Sửa** — Câu "phục hồi cấu trúc heading hierarchy" nói quá. Thực tế chỉ có một quy tắc: bullet dạng `- 1.2. **TÊN BẢNG**` được nâng thành H2. Phần bảng nhiều trang là do Docling xử lý, không phải code của mình.

**Script**

Bước đầu tiên đưa mọi định dạng về một dạng chung là Markdown. Ba loại đầu vào: DOCX qua MarkItDown, PDF qua Docling, XLSX đọc bằng openpyxl và tự dựng Markdown theo cấu trúc bản ghi.

Mỗi file được gán một `doc_id` bỏ dấu, giữ lại đuôi file, ví dụ `mo_ta_bang_bds_new__docx`. Giữ đuôi trong id là có chủ ý: cùng một nội dung nhưng đọc từ DOCX và từ PDF sẽ ra hai artifact tách biệt, nhờ vậy cuối bài em so sánh được chất lượng của hai đường parse.

Riêng file DOCX có một vấn đề: tên bảng nằm trong bullet đánh số in đậm chứ không phải heading, nên cây tài liệu bị phẳng. Em chuẩn hoá bằng một quy tắc cấu trúc, nâng bullet đó thành H2, và quy tắc này không phụ thuộc tên bảng cụ thể nào.

---

### Slide 4 — Phase 2 · Extract, bảng Role · 0:45 · KHÔNG TỒN TẠI TRONG CODE

**Cần chỉnh**

- **Sai** — Sáu role `table_meaning`, `column_intro`, `business_rule`, `sql_sample`, `sample_query`, `sample_evidence` **không có trong `offline/extract.py`**. File đó chỉ sinh ba loại phần tử và không gán role nào.
- **Sửa** — Hai cách xử lý. Cách một: bỏ hẳn slide này. Cách hai, nên hơn: đổi tiêu đề thành **"Cấu trúc tài liệu nguồn"** và trình bày sáu mục này như các mục có sẵn trong tài liệu mô tả bảng, tức là thứ mà heading hierarchy giữ lại được, chứ không phải nhãn do hệ thống gán.

> **Đề xuất tiêu đề mới:** "Tài liệu nguồn có sẵn cấu trúc gì" — và thêm một dòng cuối: những mục này được giữ nguyên qua heading, không bị gán nhãn lại.

**Script** *(theo phương án đổi tiêu đề)*

Trước khi nói về việc cắt nhỏ tài liệu, cần nhìn qua tài liệu nguồn có gì. Mỗi bảng trong tài liệu mô tả được viết theo một khuôn khá đều: ý nghĩa nghiệp vụ của bảng, giới thiệu từng cột và kiểu dữ liệu, quy tắc nghiệp vụ, câu SQL mẫu, câu hỏi tự nhiên mẫu, và ví dụ dữ liệu.

Đây là một điểm thuận lợi. Hệ thống không cần một mô hình phân loại để đoán đoạn văn nào nói về cái gì, vì cấu trúc đó đã nằm sẵn trong heading. Việc còn lại chỉ là giữ nguyên cây heading qua các bước sau, và đó chính là bước Extract với Link.

---

### Slide 5 — Phase 2 · Extract, Heading | Table | Text · 0:35 · bỏ chữ "Role"

**Cần chỉnh**

- **Sai** — Dòng `Heading | Table | Text / Role` → bỏ `/ Role`. Đúng là ba loại, không hơn.
- **Thêm** — Nói rõ parser là `markdown-it` ở chế độ commonmark có bật extension table, và mỗi phần tử nhận id chạy `el_1`, `el_2`. Output: `<doc_id>.extract.json`.

**Script**

Bước Extract đọc Markdown bằng markdown-it và chuyển thành một danh sách phẳng gồm đúng ba loại phần tử: heading, table, và text. Bảng được giữ nguyên khối chứ không bị tách thành từng dòng, vì một dòng mô tả cột mà mất phần header thì không còn hiểu được.

Em cố tình giữ bước này đơn giản, không có mô hình nào ở đây. Mọi thứ đều quyết định được từ cú pháp Markdown, nên chạy lại bao nhiêu lần cũng ra kết quả giống nhau. Mỗi phần tử được đánh id tuần tự để bước sau nối quan hệ cha con.

---

### Slide 6 — Phase 3 · Link · 0:35 · nói quá

**Cần chỉnh**

- **Sai** — "Gắn quan hệ cha–con **và section/table**" — code chỉ gắn `parent_id`. Không có quan hệ section hay table riêng. Xem `offline/link.py`, đúng 43 dòng.
- **Thêm** — Nêu cơ chế: một stack heading, gặp heading mới thì pop hết heading có level lớn hơn hoặc bằng. Đây cũng chính là hạn chế mà slide 16 nhắc tới.

**Script**

Danh sách phần tử ở bước trước là phẳng, nên bước Link dựng lại cây. Cách làm là duyệt một lượt với một stack heading: gặp heading mới thì bỏ khỏi stack mọi heading có cấp bằng hoặc sâu hơn, phần tử hiện tại nhận heading còn lại trên đỉnh stack làm cha.

Kết quả là mỗi đoạn văn và mỗi bảng đều biết mình thuộc bảng dữ liệu nào, mục nào. Cần nói thẳng một hạn chế: quan hệ này thuần tuý dựa vào vị trí xuất hiện. Nếu tài liệu viết một đoạn ở nhầm chỗ thì cây sẽ sai theo, hệ thống không có cách kiểm tra lại về mặt ngữ nghĩa.

---

### Slide 7 — Phase 4 · Chunk · 0:55 · CHẾ ĐỘ GENERAL KHÔNG CÓ

**Cần chỉnh**

- **Sai** — Bỏ "Chế độ General". Docstring `offline/chunk.py` ghi rõ: "chỉ có một luồng parent-child". Không có nhánh code nào cho chế độ kia.
- **Sửa** — Dòng output bị lặp hai lần trên slide, xoá một.
- **Thêm** — Thay chỗ trống bằng tham số thật: đơn vị **token** theo tokenizer của chính model embedding, child **40–512** token, overlap **32**, parent tối đa **3000**, bảng cắt **10 dòng** có lặp lại header, và mỗi child mang một **breadcrumb** đường dẫn heading.

**Script**

Bước Chunk cắt nội dung thành đơn vị tìm kiếm. Hệ thống dùng một chiến lược duy nhất là parent-child. Child là đoạn nhỏ từ 40 đến 512 token, đây là thứ được embed và đem đi so khớp. Parent là cả mục theo heading cấp hai, tối đa 3000 token, và đây là thứ thực sự trả về cho mô hình.

Tách đôi như vậy để giải quyết một mâu thuẫn: đoạn càng ngắn thì vector càng sắc và tìm càng chính xác, nhưng đoạn ngắn lại thiếu ngữ cảnh để trả lời. Tìm bằng child, trả về parent thì được cả hai.

Hai chi tiết riêng cho tài liệu này. Thứ nhất, bảng được cắt theo mười dòng một và lặp lại dòng header ở mỗi mảnh, để mảnh nào cũng đọc được độc lập. Thứ hai, mỗi child được gắn breadcrumb là đường dẫn heading của nó, nên khi câu hỏi nhắc tên bảng thì vế BM25 bắt được ngay cả khi đoạn văn đó không nhắc lại tên bảng.

Số token được đếm bằng đúng tokenizer của model embedding, không phải đếm ký tự, để giới hạn 512 khớp với giới hạn thật của model.

---

### Slide 8 — Graph · Entity & Relationship Extraction · 0:55 · KHÔNG CÓ REFLECTOR

**Cần chỉnh**

- **Sai** — Bỏ khối **Reflector**. Trong `SQLGraphAgent` chỉ có hai tác vụ: `extract` và `summarize`. Không có vòng kiểm tra lại bằng LLM.
- **Sai** — Output không phải `raw_entities.csv` / `raw_relationships.csv`, mà là một file `<doc_id>.graph.json`.
- **Sửa** — Schema trên slide đang là schema GraphRAG gốc. Schema thật **ràng buộc kiểu** và **bắt buộc trích dẫn**: entity gồm name, type, description, **evidence**; relationship có thêm trường **type**.
- **Thêm** — Liệt kê 6 kiểu entity và 9 kiểu quan hệ đã khai báo trong `settings.json`. Đây là điểm khác biệt đáng nói nhất của slide này.

**Script**

Song song với vế vector, em dựng thêm một knowledge graph. Từng chunk được đưa qua một LLM agent, ở đây là GPT với structured output, để rút ra thực thể và quan hệ.

Khác biệt so với GraphRAG gốc nằm ở chỗ em không để mô hình tự do đặt kiểu. Danh sách kiểu được cố định trước: sáu kiểu thực thể là bảng, cột, chỉ số, quy tắc nghiệp vụ, giá trị lọc và hàm SQL; chín kiểu quan hệ như bảng có cột, khoá ngoại, join với, chỉ số dùng cột. Kiểu nào nằm ngoài danh sách sẽ bị loại ở bước sau.

Ràng buộc thứ hai là mỗi thực thể và mỗi quan hệ đều phải kèm một đoạn trích nguyên văn từ chunk làm bằng chứng. Prompt cũng nói rõ là không được suy diễn schema còn thiếu. Hai ràng buộc này nhằm hạn chế việc mô hình bịa ra tên cột không có trong tài liệu, vì với bài toán sinh SQL thì một tên cột bịa sẽ làm câu lệnh chạy lỗi ngay.

---

### Slide 9 — Graph · Entity Resolution · 0:40 · KHÔNG CÓ SUMMARIZER Ở BƯỚC NÀY

**Cần chỉnh**

- **Sai** — Bỏ khối **Summarizer** và câu "nếu mô tả quá dài thì đưa qua LLM tóm tắt". Hàm `_resolve()` hoàn toàn xác định: chuẩn hoá tên, gộp theo khoá `(type, tên đã casefold)`, nối mô tả bằng dấu `|` và loại trùng. Không gọi LLM.
- **Sai** — Output không phải `resolved_entities.csv`.
- **Thêm** — Nêu bước lọc: quan hệ nào có đầu mút không khớp đúng một entity đã rút ra thì bị bỏ. Đây là lý do graph sạch nhưng có nhiều node cô lập.

**Script**

Vì extract chạy theo từng chunk, cùng một bảng sẽ xuất hiện nhiều lần dưới nhiều cách viết. Bước resolution gộp chúng lại. Em làm bước này hoàn toàn xác định, không gọi LLM: bỏ ký tự escape của Markdown, chuẩn hoá khoảng trắng, rồi gộp theo cặp kiểu và tên đã chuẩn hoá. Các mô tả của cùng một thực thể được nối lại và loại trùng.

Chọn cách xác định vì bước này quyết định danh tính của node. Nếu để LLM gộp thì hai lần chạy có thể ra hai graph khác nhau, và mọi con số đánh giá phía sau sẽ mất ý nghĩa.

Sau khi gộp, em lọc quan hệ: chỉ giữ quan hệ mà cả hai đầu khớp đúng một thực thể đã rút ra và có kiểu nằm trong danh sách cho phép. Cách này giữ graph sạch, nhưng đổi lại nhiều node bị mất hết cạnh, và lát nữa con số node cô lập sẽ cho thấy cái giá đó.

---

### Slide 10 — Graph · Community & Report · 0:50 · KHÔNG PHẢI LEIDEN PHÂN CẤP

**Cần chỉnh**

- **Sai** — **Hierarchical Leiden không có trong code.** `offline/graph.py:209` hỗ trợ ba lựa chọn: `greedy_modularity` (đang khoá), `louvain`, `connected_components`. Community **một tầng phẳng**, không phân cấp.
- **Sai** — Bỏ "đưa từng community từ dưới lên". Không có thứ bậc thì không có bottom-up. Report sinh phẳng, tối đa 30 community.
- **Sai** — Output không phải `.gexf` hay các file csv. Tất cả nằm trong `<doc_id>.graph.json`; phần hiển thị là SVG dựng bằng spring layout trong app.
- **Thêm** — Đây là chỗ tốt để nói trước rằng community algorithm chính là tham số được tune ở luồng đánh giá graph.

**Script**

Sau khi có node và cạnh, em dựng graph bằng networkx rồi chia cụm. Code hỗ trợ ba thuật toán và cấu hình đang khoá ở greedy modularity. Cần nói rõ là cụm ở đây phẳng, chỉ một tầng, chứ chưa phải cấu trúc phân cấp như GraphRAG gốc của Microsoft.

Mỗi cụm được đưa qua LLM một lần nữa để sinh một bản tóm tắt ngắn gồm tiêu đề và nội dung, với yêu cầu giữ nguyên các sự kiện về bảng, cột, join và quy tắc, không thêm thông tin ngoài cụm. Những bản tóm tắt này sau đó cũng được embed và index, nên chúng trở thành một loại nội dung có thể tìm kiếm được, bên cạnh chunk tài liệu và chunk SQL.

Việc chọn thuật toán chia cụm không phải chọn cảm tính. Lát nữa ở phần đánh giá, em có một luồng riêng để tune tham số này.

---

### Slide 11 — Graph · Global Query · 0:40 · CHƯA ĐƯỢC CÀI ĐẶT

**Cần chỉnh**

- **Sai** — Toàn bộ luồng map-reduce, gom report thành chunk, chấm helpfulness, lọc theo ngưỡng, synthesize, **không có trong repo**. `online/retrieval.py` xử lý graph y hệt docs và sql: hybrid, rerank, lấy top 3.
- **Sửa** — Hai lựa chọn. Cách an toàn: đổi slide này thành **"Graph được dùng thế nào ở online"** và mô tả đúng cơ chế ba vế. Cách còn lại: chuyển nguyên slide sang phần Hướng phát triển ở slide 16 và nói rõ đây là thiết kế dự kiến.
- **Thêm** — Nếu giữ slide theo cách an toàn, nêu `graph_top_k = 3` và việc vế graph tự bỏ qua khi collection chưa tồn tại.

> **Nếu bị hỏi thẳng:** trả lời rằng bản MVP dừng ở mức graph là một nguồn truy hồi thứ ba, còn map-reduce trên community report là bước kế tiếp đã thiết kế nhưng chưa cài. Đừng mô tả nó như thứ đang chạy.

**Script** *(theo phương án đổi tiêu đề)*

Ở phía online, hệ thống truy hồi song song ba vế cho mỗi câu hỏi: vế tài liệu lấy năm kết quả, vế SQL mẫu lấy ba, và vế graph lấy ba bản tóm tắt cụm. Ba vế nằm ở ba collection riêng nên không tranh chỗ của nhau, tài liệu dài không đẩy câu SQL mẫu ra khỏi kết quả.

Vế graph dùng đúng cơ chế hybrid và rerank như hai vế kia, và nếu chưa index graph thì nó tự trả về rỗng để hệ thống vẫn chạy được.

Ở đây em nói rõ giới hạn hiện tại: graph đang đóng vai trò một nguồn truy hồi bổ sung, chứ chưa có bước tổng hợp toàn cục kiểu map-reduce trên toàn bộ community report. Đó là hướng phát triển tiếp theo, và em có nói ở slide cuối.

---

### Slide 12 — Phase 5 · Embed · 0:35 · slide gần như trống

**Cần chỉnh**

- **Thêm** — Tên model thật: dense `AITeamVN/Vietnamese_Embedding`, sparse `Qdrant/bm25`, chạy trên CUDA, batch 16, vector chuẩn hoá.
- **Thêm** — BM25 cấu hình `k1=1.2`, `b=0.0` và **tắt stemmer**. Đây là lựa chọn có lý do, nên nói ra.
- **Thêm** — Bước này embed cả chunk lẫn item graph, ra hai file: `.vectors.jsonl` và `.graph_vectors.jsonl`.

**Script**

Bước embed sinh hai loại biểu diễn cho mỗi chunk. Dense dùng Vietnamese_Embedding của AITeamVN, một model chuyên tiếng Việt, vector được chuẩn hoá để tính cosine bằng tích vô hướng. Sparse dùng BM25 của Qdrant.

Hai chi tiết trong cấu hình BM25 là chủ ý. Em đặt tham số b bằng 0, tức bỏ chuẩn hoá theo độ dài văn bản, vì các chunk ở đây đã bị giới hạn trong khoảng 40 đến 512 token nên độ dài khá đồng đều. Em cũng tắt stemmer, vì stemmer không hỗ trợ tiếng Việt và với tên bảng, tên cột thì việc cắt gốc từ chỉ làm hỏng khớp chính xác.

Bước này chạy trên cả chunk tài liệu lẫn các bản tóm tắt cụm của graph, nên hai loại nội dung nằm cùng một không gian vector.

---

### Slide 13 — Phase 6 · Index · 0:40 · slide gần như trống

**Cần chỉnh**

- **Thêm** — Cấu trúc collection thật: mỗi knowledge có ba collection `docs` / `sql` / `graph`. p1 gắn với DOCX, p2 gắn với PDF, cả hai dùng chung file testcase.
- **Thêm** — Mỗi point mang hai named vector trong cùng một collection: `dense` cosine và `bm25` sparse có bật IDF modifier. Nhờ vậy hai vế truy hồi trên đúng một tập điểm.
- **Thêm** — Point id sinh bằng UUID5 từ namespace cố định nên chạy lại là ghi đè, không nhân bản dữ liệu.

**Script**

Toàn bộ vector được đưa vào Qdrant. Cách tổ chức: mỗi bộ tri thức có ba collection tách riêng cho tài liệu, SQL mẫu và graph. Em dựng hai bộ song song, p1 dùng bản DOCX và p2 dùng bản PDF, cùng chia sẻ file testcase. Hai bộ này về sau cho phép so sánh trực tiếp chất lượng của hai đường parse.

Trong mỗi collection, một điểm mang đồng thời hai vector có tên: một dense và một sparse có bật IDF. Đây là lý do phần hybrid ở bước sau thực hiện được sạch sẽ, vì hai vế tìm trên đúng cùng một tập điểm và chỉ việc trộn thứ hạng.

Payload lưu kèm cả text của child lẫn text của parent, nên khi trả kết quả không cần truy ngược về file. Id của điểm sinh xác định từ nội dung, nên chạy lại pipeline sẽ ghi đè chứ không tạo bản sao.

---

### Slide 13+ — SLIDE NÊN THÊM · Hybrid và Rerank · 0:45

**Vì sao cần**

- **Thêm** — Bài tên là "Hybrid Retrieval" nhưng không slide nào giải thích cách trộn. Công thức thật trong `online/retrieval.py` là RRF có trọng số: `score += w / (rrf_k + rank)`.
- **Thêm** — **Reranker không xuất hiện ở bất kỳ slide nào**, dù nó nằm trong đường chạy chính. Model `AITeamVN/Vietnamese_Reranker`, chấm lại 8 ứng viên hàng đầu.
- **Thêm** — Có một guard đáng nói: hệ thống bắt buộc dense và reranker cùng họ model, lệch họ thì báo lỗi ngay.

**Script**

Đây là phần lõi của tên đề tài. Với mỗi câu hỏi, hệ thống chạy hai truy vấn song song, dense và BM25, mỗi bên lấy 20 ứng viên. Hai danh sách được trộn bằng reciprocal rank fusion có trọng số: mỗi kết quả nhận điểm bằng trọng số của vế đó chia cho hằng số rrf_k cộng thứ hạng.

Trộn theo thứ hạng thay vì theo điểm số là có lý do: điểm cosine và điểm BM25 không cùng thang, cộng thẳng thì vế nào có thang lớn hơn sẽ áp đảo.

Sau khi trộn, tám ứng viên đầu được đưa qua một cross-encoder tiếng Việt để chấm lại. Khác với bi-encoder vốn mã hoá câu hỏi và đoạn văn tách rời, cross-encoder đọc cả hai cùng lúc nên bắt được liên hệ tinh hơn. Chi phí là phải chạy tám lượt cho mỗi câu hỏi, nên chỉ dùng ở bước cuối trên tập ứng viên nhỏ.

Một chi tiết nhỏ trong code: reranker được chấm trên text của child chứ không phải parent, vì parent có thể dài tới ba nghìn token và sẽ làm loãng tín hiệu.

---

### Slide 14 — Phase 7 · Verify, số tổng quan · 1:10 · SỐ LIỆU ĐÃ CŨ

**Cần chỉnh**

- **Sai** — `docs@5 ~0.67–0.71` → thật là **0.467** trên dev, **0.405** và **0.506** trên test. Con số cũ là của lần chạy trước khi đổi luật lọc dòng.
- **Sai** — `sql@3 ~0.88` → thật là **0.949** trên dev, **0.970** trên test. Chỗ này số thật **tốt hơn** slide.
- **Sai** — `Final score ~0.78–0.80` → thật là **0.578** dev, **0.653** / **0.561** test.
- **Sai** — Bỏ câu "A 5% improvement in recall@5 directly reduces wrong answers in deployed RAG systems". Đây là khẳng định không đo được từ dữ liệu của mình, và rất dễ bị hỏi lại.
- **Sửa** — "14 valid cases" → chỉ ghi **14 case**. Chữ valid gợi ý đã loại bỏ case, người nghe sẽ hỏi loại theo tiêu chí gì.
- **Thêm** — Định nghĩa điểm: `union_f1` trên hợp của hai vế. Không nêu thì con số không có nghĩa.
- **Thêm** — Nêu **leave-one-out**: khi chấm một case dev, chính câu SQL của case đó bị loại khỏi kết quả truy hồi. Đây là điểm mạnh về mặt phương pháp, đang bị bỏ trắng.

**Script**

Phần đánh giá gồm hai luồng độc lập. Luồng thứ nhất đo retrieval thông thường, luồng thứ hai đo chất lượng cấu trúc của graph. Cả hai đều tách dev và test: dev có 33 case dùng để chọn tham số, test có 14 case chỉ chạy một lần bằng cấu hình đã khoá, và không bao giờ tham gia vào việc chọn tham số.

Nhãn đúng của mỗi case là tập bảng liên quan, lấy từ cột Relevant Chunks trong file testcase. Điểm tổng là F1 trên hợp của hai vế docs và SQL, vì hệ thống được coi là thành công khi bảng cần thiết xuất hiện ở ít nhất một trong hai vế.

Có một điểm về phương pháp em muốn nhấn. File testcase cũng được index như một nguồn tri thức, nên khi chấm câu hỏi của case dev, hệ thống hoàn toàn có thể tìm thấy chính câu SQL đáp án của case đó và đạt điểm tuyệt đối một cách giả tạo. Em xử lý bằng cách loại chính section của case đang chấm ra khỏi kết quả truy hồi. Đây là lý do con số của em thấp hơn nếu so với cách chấm không có bước loại này.

---

### Slide 15 — Phase 7 · Verify, bảng kết quả · 1:30 · THAY TOÀN BỘ HAI BẢNG

**Cần chỉnh**

- **Sai** — Bảng dev cũ liệt kê 7 dòng với rrf_k từ 1 đến 60. Grid thật trong notebook chỉ có **4 cấu hình**: semantic, keyword, hybrid 0.1/0.9, hybrid 0.3/0.7, đều ở rrf_k=5.
- **Sai** — Slide kết luận cấu hình thắng là `rrf_k=1, 0.5/0.5`. Cấu hình đang khoá trong `normal_locked.json` là **rrf_k=5, 0.1/0.9**.
- **Thêm** — Thiếu hẳn bảng GraphRAG. Đây là nửa còn lại của công việc và hiện không có slide nào trình bày kết quả của nó.
- **Sửa** — Dùng bốn bảng ở phần "Số liệu thật" phía trên. Nếu chật, ghép dev và test của Normal vào một slide, graph vào slide kế tiếp.

**Script · phần Normal**

Trên dev, bốn cấu hình được so sánh. Điều đáng chú ý là keyword thuần đạt 0.559, cao hơn semantic thuần ở mức 0.514. Với loại tài liệu này thì hợp lý, vì câu hỏi và tài liệu dùng chung rất nhiều định danh chính xác như tên bảng viết hoa và tên cột, mà khớp chuỗi làm tốt hơn khớp ngữ nghĩa.

Cấu hình thắng là hybrid với rrf_k bằng 5 và trọng số 0.1 cho dense, 0.9 cho sparse, đạt 0.578. Tức là hybrid vẫn tốt hơn keyword thuần, nhưng phần đóng góp của dense là bổ sung chứ không phải chủ đạo. Em khoá cấu hình này rồi mới chạy test.

Trên test, p1 dựng từ DOCX đạt 0.653 còn p2 dựng từ PDF đạt 0.561. Chênh lệch này nằm ở precision chứ không phải recall: cả hai đều đạt union recall 0.988 và sql@3 0.970, nhưng p1 có precision 0.505 so với 0.415 của p2. Đọc ra là bản parse từ PDF sinh chunk vụn hơn, nên cùng lấy được đáp án nhưng kèm nhiều kết quả thừa hơn.

Điểm test cao hơn dev là do tập test dễ hơn về mặt phân bố, không phải do hệ thống được tối ưu theo test.

**Script · phần GraphRAG**

Luồng thứ hai đo graph. Ở đây em không đo recall, mà đo xem các bảng cần cho một câu hỏi có nằm gần nhau trong graph hay không. Ba chỉ số: complete là tỉ lệ case tìm thấy đủ mọi bảng cần thiết trong graph, connected là tỉ lệ case mà các bảng đó nối được với nhau, và same community là tỉ lệ case mà chúng rơi vào cùng một cụm. Điểm tổng lấy trọng số bốn, ba, ba.

Trên dev, greedy modularity đạt 0.818 còn cả bốn cấu hình louvain đều đạt 0.764. Khác biệt nằm trọn ở same community: 0.394 so với 0.212. Louvain ở đây chia cụm mịn hơn nên hay tách các bảng liên quan ra, và thay đổi resolution từ 0.5 lên 2.0 không cải thiện được chỉ số đó.

Trên test, graph gộp cả tài liệu lẫn SQL sample nên lớn hơn nhiều, khoảng 400 node và trên 550 cạnh, điểm còn 0.657. Complete vẫn tuyệt đối, connected còn 0.786, nhưng same community tụt xuống 0.071.

Em đọc con số này thẳng thắn: graph đang rút đúng thực thể, table coverage đạt 1.0 ở cả hai bộ, nhưng việc chia cụm chưa dùng được cho truy hồi. Gần 50 trên 400 node không có cạnh nào, và các bảng cần cho một câu hỏi hầu như luôn nằm ở các cụm khác nhau. Nguyên nhân em cho là ở bước lọc quan hệ khá chặt đã nói ở slide trước.

> *Nếu đã chạy xong so sánh Gemini thì thêm một đoạn ở đây; hiện trong thư mục benchmark chưa có file kết quả của nhánh đó.*

---

### Slide 16 — Hạn chế và Hướng phát triển · 1:00 · mâu thuẫn nội bộ

**Cần chỉnh**

- **Sai** — Bỏ **"Tích hợp GraphRAG"** khỏi mục Phát triển. Graph đang bật, đã extract, đã index, đã có số liệu. Để nguyên sẽ mâu thuẫn với slide 8 đến 11.
- **Sai** — Bỏ **"Qdrant-only vector store"** khỏi mục Hạn chế. Đây là lựa chọn thiết kế, không phải hạn chế, và nó trùng ý với dòng Pinecone/Weaviate ngay bên dưới.
- **Thêm** — Ba hạn chế thật, đo được từ chính kết quả: **same_community 0.071** trên test; **47/392 node cô lập**; và **vế graph chưa được nối vào câu trả lời cuối**, mới dừng ở truy hồi.
- **Thêm** — Một hạn chế nữa nên nói: **docs@5 chỉ quanh 0.4–0.5**. Đây là chỉ số yếu nhất của hệ thống, nên chủ động nêu thay vì để người khác chỉ ra.
- **Sửa** — "Hierachy" → "Hierarchy". "Multi-hop reasoning" nên nối trực tiếp với việc chưa có Global Query ở slide 11.

**Script**

Về hạn chế, em nêu bốn điểm và cả bốn đều rút ra từ số liệu vừa trình bày.

Thứ nhất, cây tài liệu phụ thuộc hoàn toàn vào vị trí xuất hiện của phần tử. Nếu tài liệu nguồn viết lộn xộn thì quan hệ cha con sẽ sai theo, và hệ thống không phát hiện được.

Thứ hai, chỉ số docs@5 chỉ quanh 0.4 đến 0.5. Nghĩa là trong năm đoạn tài liệu trả về, hệ thống mới phủ được khoảng một nửa số bảng cần thiết. Vế SQL mẫu bù lại rất tốt với 0.97, nên hợp hai vế vẫn gần như phủ đủ, nhưng riêng vế tài liệu thì còn yếu.

Thứ ba, phần chia cụm của graph chưa dùng được. Same community trên test chỉ 0.071, và gần 50 node không có cạnh nào. Em nghĩ nguyên nhân là luật lọc quan hệ quá chặt, và đây là chỗ cần sửa đầu tiên.

Thứ tư, vế graph mới dừng ở truy hồi, chưa có bước tổng hợp toàn cục trên community report.

Về hướng phát triển, ưu tiên theo đúng thứ tự đó: nới luật lọc quan hệ và thêm bước gộp thực thể theo ngữ nghĩa để giảm node cô lập; sau đó mới cài phần truy vấn toàn cục để trả lời được các câu hỏi cần nối nhiều bảng. Xa hơn là chunking theo token động và vòng phản hồi từ người dùng.

---

### Slide 17 — Slide trống, nên là slide chốt · 0:20

**Cần chỉnh**

- **Thêm** — Ba dòng chốt và một dòng cảm ơn. Đừng để trắng, người nghe cần một chỗ dừng mắt trong lúc hỏi đáp.
- **Thêm** — Nếu có demo Knowledge Studio trong `app/app.py`, đây là chỗ để bật lên: giao diện chạy được từng bước offline và xem graph trực tiếp.

**Script**

Tóm lại ba ý. Một, pipeline offline bảy bước chạy được đầu cuối trên cả DOCX và PDF, mỗi bước có artifact riêng nên chạy lại được từng phần. Hai, hybrid retrieval với rerank đạt union F1 0.653 trên tập test, trong đó vế SQL mẫu đạt 0.97. Ba, graph rút đúng thực thể với table coverage tuyệt đối, nhưng phần chia cụm chưa dùng được cho truy hồi và đó là việc tiếp theo.

Em xin hết phần trình bày.

---

## Chuẩn bị cho phần hỏi đáp

Bốn câu có xác suất bị hỏi cao nhất, dựa trên chỗ số liệu yếu và chỗ thiết kế khác thường.

**Vì sao docs@5 thấp mà vẫn kết luận hệ thống chạy được?**
Vì tiêu chí thành công là phủ đủ bảng cần thiết, và điều đó được đo bằng union recall trên hợp hai vế, đạt 0.988. Vế tài liệu yếu nhưng vế SQL mẫu bù được. Nói thêm rằng em vẫn coi docs@5 là hạn chế và đã nêu ở slide 16.

**Trọng số 0.1 cho dense có nghĩa là embedding vô dụng không?**
Không, vì hybrid 0.1/0.9 vẫn hơn keyword thuần, 0.578 so với 0.559. Dense đóng vai trò bổ sung cho các câu hỏi diễn đạt tự nhiên không nhắc tên bảng. Nếu tài liệu ít định danh chính xác hơn thì trọng số này sẽ khác, nên em để nó là tham số tune được chứ không cố định.

**Test cho điểm cao hơn dev, có bị rò rỉ dữ liệu không?**
Không. Cấu hình được khoá vào file JSON sau khi chạy xong dev, test chỉ chạy một lần với cấu hình đó. Thêm nữa dev còn bị loại chính case đang chấm khỏi kết quả truy hồi, còn test thì không cần bước đó, nên dev vốn đã bị chấm chặt hơn.

**Graph có đóng góp gì vào kết quả không?**
Trả lời thẳng: hiện chưa đo được đóng góp của graph vào điểm retrieval, vì hai luồng đánh giá đang tách rời. Graph mới được đo về mặt cấu trúc. Một thí nghiệm ablation bật tắt vế graph là việc nên làm tiếp theo.
