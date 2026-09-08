# Benchmark kb-text2sql

Báo cáo kết quả thang benchmark 8 kịch bản cho bài toán sinh câu lệnh SQL từ câu hỏi tiếng Việt trên bộ dữ liệu BIRD.

---

## 1. Bài toán và mục tiêu đo

Người dùng đặt một câu hỏi bằng tiếng Việt, ví dụ "trường nào có điểm trung bình môn Toán cao nhất ở hạt Alameda". Hệ thống phải sinh ra câu SQL chạy được trên cơ sở dữ liệu, và câu SQL đó phải trả về đúng kết quả mà câu SQL chuẩn trả về.

Điều khó không nằm ở cú pháp SQL, mà ở chỗ model phải biết bảng nào chứa dữ liệu cần tìm, cột nào mang ý nghĩa gì, và giá trị trong câu hỏi được lưu dưới dạng chuỗi như thế nào trong database. Toàn bộ 8 kịch bản dưới đây khác nhau ở đúng một điểm: **cung cấp thông tin nền cho model theo cách nào**.

Mục tiêu của thang benchmark là tách được đóng góp của từng cách. Vì vậy mỗi kịch bản chỉ thay đổi một yếu tố so với kịch bản liền trước, để nếu điểm số thay đổi thì biết nguyên nhân đến từ đâu.

---

## 2. Cách đánh giá

**Chấm điểm.** Một câu được tính là đúng khi câu SQL do model sinh ra chạy trên database và trả về đúng tập kết quả mà câu SQL chuẩn trả về. So sánh ở mức tập hợp giá trị, không so sánh chuỗi SQL — hai câu SQL viết khác nhau nhưng cùng kết quả vẫn được tính đúng. Nếu câu SQL chuẩn có `ORDER BY` thì thứ tự dòng cũng phải khớp; nếu không thì bỏ qua thứ tự.

Chỉ số chính gọi là **execution accuracy** — tỉ lệ câu đúng trên tổng số câu.

BIRD còn có một chỉ số thứ hai tên là R-VES, đo thêm tốc độ thực thi của câu SQL. Dự án chưa tích hợp bộ chấm R-VES chính thức nên chỉ số này để trống, không suy diễn từ execution accuracy.

**Dữ liệu.** Hai run trong báo cáo này chạy trên một bộ test 62 câu thuộc 2 database. Đây là điểm yếu lớn nhất của số liệu hiện có, giải thích ở mục 6.

**Model.** Toàn bộ kết quả dùng cùng một model (`gpt-5.4`), cùng một prompt, cùng seed. Nhờ vậy chênh lệch giữa các kịch bản không đến từ việc đổi model.

**Quy trình.** Các tham số (lấy bao nhiêu bảng, cắt context ở bao nhiêu token, cho phép sửa mấy vòng) được dò trên tập dev trước, khoá lại, rồi mới chạy test. Không quay lại chỉnh tham số sau khi nhìn thấy điểm test.

**Chống rò rỉ đáp án.** Câu SQL chuẩn không bao giờ được đưa vào prompt, vào retrieval, vào bước sửa lỗi hay bước chọn ứng viên. Bộ chấm chỉ được đọc đáp án sau khi câu SQL của model đã bị đóng băng.

---

## 3. Tám kịch bản

Mỗi kịch bản dưới đây gồm bốn phần: **nó là gì**, **quy trình chạy**, **tham số điều khiển**, và **bài báo gốc** kèm nhận xét về chỗ giống và chỗ khác.

Tám kịch bản xếp thành một thang tăng dần. Đọc từ trên xuống sẽ thấy mỗi bậc thêm đúng một thứ:

```
P1   đưa hết vào prompt
 │
B4   thay bằng: chỉ đưa phần liên quan (tìm kiếm + khớp bảng/cột + khớp giá trị)
 │
 ├── + event seeds        thêm ngữ cảnh dạng sự kiện, lấy trực tiếp
 │        │
 │        └── + expansion  lan tiếp sang sự kiện lân cận qua thực thể chung
 │                 │
 │                 └── B5  để model tự lọc lại đống ngữ cảnh đó
 │                          │
 │                          └── B6-relational  thêm: chạy thử rồi sửa
 │
 └── B6-hybrid            chạy thử rồi sửa, nhưng ngữ cảnh nghèo hơn (đối chứng)

G1   model tự chọn đi nhánh nào trong ba nhánh trên + sinh nhiều phương án
```

---

### P1 — Đưa hết vào prompt

**Là gì.** Mốc so sánh. Không tìm kiếm, không lọc, không sửa: toàn bộ cấu trúc database và tài liệu nghiệp vụ được nhét thẳng vào prompt, model đọc hết rồi viết một câu SQL duy nhất.

**Quy trình.** Dựng ngữ cảnh → sinh SQL → xong.

**Vì sao cần.** Nếu các kịch bản retrieval phía dưới không vượt được P1 thì toàn bộ công sức xây tìm kiếm chưa mang lại giá trị. Đây là câu hỏi trung tâm của cả báo cáo.

**Bài báo.** [BIRD — Can LLM Already Serve as A Database Interface?](https://arxiv.org/abs/2305.03111) (Li và cộng sự, NeurIPS 2023). Đây là bộ dữ liệu nền, không phải một phương pháp. BIRD đóng góp ba thứ mà dự án dùng lại: bộ câu hỏi gắn với database thật cỡ lớn, phần gợi ý nghiệp vụ đi kèm mỗi câu hỏi, và cách chấm bằng so khớp kết quả thực thi.

---

### B4 — Chỉ đưa phần liên quan (schema linking)

**Là gì.** Thay vì đưa hết, hệ thống đi tìm đúng những mảnh thông tin liên quan tới câu hỏi rồi ghép lại thành ngữ cảnh gọn.

**Quy trình.** Bốn nguồn chạy song song, sau đó gộp và cắt:

1. **Khớp bảng và cột.** So câu hỏi với tên và mô tả của từng bảng, từng cột trong database. Chấm điểm theo mức trùng khớp, bỏ những cái dưới ngưỡng, giữ lại N bảng và M cột điểm cao nhất.

2. **Khớp giá trị.** Câu hỏi nhắc tới "hạt Alameda", nhưng trong database chuỗi đó có thể được lưu là `Alameda`, `Alameda County`, hay viết hoa khác đi. Bước này dò trong kho giá trị của database để tìm dạng lưu trữ thật, chấp nhận cả khớp chính xác lẫn khớp gần đúng theo ngưỡng tương đồng. Đây là bước quyết định việc mệnh đề `WHERE` có viết đúng hay không.

3. **Tìm đoạn tài liệu nghiệp vụ.** Chạy hai kiểu tìm kiếm song song trên tài liệu: tìm theo ngữ nghĩa (so vector nhúng của câu hỏi với vector của từng đoạn) và tìm theo từ khoá. Hai danh sách kết quả được trộn lại bằng cách cộng nghịch đảo thứ hạng, để một đoạn được cả hai cách xếp cao sẽ nổi lên trên. Tuỳ chọn thêm một bước xếp hạng lại bằng mô hình chuyên dụng đọc cặp câu hỏi–đoạn văn.

4. **Tìm ví dụ mẫu tương tự.** Theo thiết kế, lấy các cặp câu hỏi–SQL đã có sẵn từ tập train giống câu hỏi hiện tại để model học theo. **Nguồn này rỗng trong mọi run** vì repo không có tập train.

Sau đó phần gợi ý nghiệp vụ của BIRD được ghim vào đầu (luôn giữ, không bao giờ bị cắt), rồi tất cả xếp theo thứ tự ưu tiên — bảng/cột trước, giá trị, tài liệu, ví dụ, sự kiện sau cùng — và cắt dần từ dưới lên cho vừa hạn mức token.

**Tham số điều khiển.** Số bảng và số cột giữ lại; ngưỡng điểm tối thiểu; số giá trị và ngưỡng khớp gần đúng; tỉ lệ trộn giữa tìm ngữ nghĩa và tìm từ khoá; bật/tắt bước xếp hạng lại; hạn mức token của toàn ngữ cảnh.

**Bài báo.**

- [CHESS — Contextual Harnessing for Efficient SQL Synthesis](https://arxiv.org/abs/2405.16755) (Talaei, Pourreza, Chang, Mirhoseini, Saberi, 2024). Đây là nguồn ý tưởng chính. CHESS đặt vấn đề đúng như B4: schema của database thật quá lớn để nhét vào prompt, nên phải thu hẹp trước. Ba việc CHESS làm — truy hồi thông tin liên quan, chọn schema, rồi mới sinh SQL — là ba việc B4 làm. **Khác biệt:** CHESS tách thành các tác nhân chuyên trách riêng biệt và có bước lọc cột kỹ hơn nhiều; B4 gộp tất cả vào một bước dựng ngữ cảnh duy nhất.

- [DIN-SQL — Decomposed In-Context Learning of Text-to-SQL with Self-Correction](https://arxiv.org/abs/2304.11015) (Pourreza và Rafiei, NeurIPS 2023). **Chỉ trùng ở một module.** DIN-SQL có bốn phần: khớp schema, phân loại độ khó, phân rã câu khó thành câu con, và tự sửa lỗi. B4 chỉ tương ứng phần **khớp schema**. Ba phần còn lại nằm ở chỗ khác trong dự án: tự sửa lỗi ở B6, phân loại độ khó ở G1, còn phân rã câu hỏi **chưa được cài**. Khi trích DIN-SQL cho B4 cần ghi rõ là chỉ phần schema linking, nếu không sẽ thành nhận công của những thứ chưa làm.

---

### B4 + event seeds — Thêm ngữ cảnh dạng sự kiện

**Là gì.** Thêm nguồn thông tin thứ năm, tổ chức theo một cách khác hẳn bốn nguồn trên.

**Chuẩn bị trước (chạy một lần, ngoại tuyến).** Tài liệu nghiệp vụ và schema được tách thành các **sự kiện** — mỗi sự kiện là một mẩu nội dung trọn nghĩa, ví dụ một đoạn mô tả quy tắc tính điểm, một định nghĩa cột, một quan hệ khoá ngoại. Mỗi sự kiện được gắn với các **thực thể** xuất hiện trong nó: tên bảng, tên cột, khái niệm nghiệp vụ. Kết quả là một mạng lưới hai lớp: sự kiện ở một bên, thực thể ở bên kia, nối với nhau bằng quan hệ "có nhắc tới". Mọi nút và mọi cạnh đều lưu nguồn gốc để truy vết.

Điểm mấu chốt: **không phân rã thành bộ ba chủ ngữ–quan hệ–tân ngữ** như đồ thị tri thức thông thường. Một sự kiện giữ nguyên quan hệ nhiều chiều của nó.

**Quy trình lúc chạy.**

1. Nhận diện các thực thể được nhắc trong câu hỏi và trong ngữ cảnh B4 vừa dựng.
2. Chấm điểm từng sự kiện theo hai tín hiệu cộng lại: mức trùng từ ngữ giữa câu hỏi và nội dung sự kiện, cộng với số thực thể dùng chung (có trọng số thấp hơn).
3. Lấy N sự kiện điểm cao nhất. **Dừng ở đây** — không đi tiếp sang sự kiện lân cận.
4. Gộp vào ngữ cảnh B4, cắt theo hạn mức bằng quy tắc. Không hỏi model.

**Đo được.** Trung bình mỗi câu nhận thêm **1,85 sự kiện** sau khi cắt.

**Vì sao tách riêng bậc này.** Để biết phần lợi ích (nếu có) đến từ bản thân việc thêm sự kiện, hay đến từ cơ chế lan toả ở bậc sau.

**Bài báo.** [SAG — SQL-Retrieval Augmented Generation with Query-Time Dynamic Hyperedges](https://arxiv.org/abs/2606.15971) (Wu, Li, Liang, Chen, Liang, Mo, Li). Xem phần nhận xét chung ở bậc kế tiếp.

---

### B4 + event expansion — Lan ra theo thực thể chung

**Là gì.** Giống bậc trên, nhưng đi tiếp một bước: từ các sự kiện ban đầu, kéo thêm những sự kiện lân cận.

**Quy trình.** Bước 1–2 giống hệt bậc trên. Khác từ bước 3:

3. Từ mỗi sự kiện đã chọn, lấy danh sách thực thể nó nhắc tới. Với mỗi thực thể đó, lấy tất cả sự kiện khác cũng nhắc tới nó. Đây là cách bắc cầu: sự kiện A nói về thực thể X, sự kiện B cũng nói về X, vậy B liên quan gián tiếp tới câu hỏi dù có thể không dùng chung từ nào với câu hỏi.
4. Lặp bước trên theo số bước cho trước, duyệt theo chiều rộng.
5. Dừng khi chạm một trong ba giới hạn: đi đủ số bước, đủ số sự kiện tối đa, hoặc tổng độ dài chạm hạn mức token riêng cho phần sự kiện.
6. Vẫn cắt bằng quy tắc, chưa hỏi model.

**Ý nghĩa.** Đây là điểm mấu chốt của cả nhóm ý tưởng: vùng lân cận được **sinh ra tại lúc truy vấn**, riêng cho từng câu hỏi, thay vì dựng sẵn một đồ thị cố định từ trước.

**Tham số điều khiển.** Số sự kiện gốc; số bước lan; số sự kiện tối đa; hạn mức token riêng cho phần sự kiện.

**Đo được.** Trung bình **5,08 sự kiện** mỗi câu — gấp gần ba lần bậc trước.

**Một quan sát quan trọng.** Đi 1 bước và đi 2 bước cho kết quả **giống hệt nhau** trên tập dev: cùng độ phủ, cùng số sự kiện. Mạng lưới sự kiện của tài liệu hiện tại bão hoà ngay ở bước đầu, bước thứ hai không kéo thêm được nút nào. Không nên trình bày tham số "số bước lan" như một tham số có dải hoạt động rộng khi chưa có tài liệu sâu hơn.

| Cấu hình | Tỉ lệ phủ đủ bảng cần thiết | Độ phủ bảng | Số sự kiện trung bình |
|---|---|---|---|
| Lấy trực tiếp, 4 sự kiện gốc | 0,1818 | 0,5833 | 4,00 |
| Lấy trực tiếp, 8 sự kiện gốc | 0,3636 | 0,6515 | 6,18 |
| Lan 1 bước | 0,5455 | 0,7879 | 7,45 |
| Lan 2 bước | 0,5455 | 0,7879 | 7,45 |

**Bài báo.** [SAG](https://arxiv.org/abs/2606.15971) — nhận xét chung ở bậc kế tiếp.

---

### B5 — Để model tự lọc ngữ cảnh

**Là gì.** Sau khi đã gom được nhiều mảnh ngữ cảnh, thay vì cắt bớt bằng quy tắc ưu tiên, hệ thống đưa cả danh sách cho chính model và hỏi: với câu hỏi này, cần giữ lại những mảnh nào?

**Quy trình.**

1. Dựng ngữ cảnh B4.
2. Thêm sự kiện và lan toả như bậc trên.
3. **Bước mới:** gửi danh sách mảnh ngữ cảnh (mỗi mảnh rút gọn còn phần đầu) kèm câu hỏi cho model, yêu cầu trả về danh sách ID cần giữ, tối đa K mảnh, kèm lý do. Nếu model trả về rỗng hoặc ID không hợp lệ thì rơi về cách cắt bằng quy tắc.
4. Dựng lại ngữ cảnh chỉ từ các mảnh model chọn, rồi sinh SQL.

**Hai điểm thiết kế đáng nói.**

- Bước lọc này là **một lượt gọi model riêng biệt**, tách hẳn khỏi phần tìm kiếm. Tách như vậy để đo được riêng chi phí token và tác dụng của nó, thay vì trộn lẫn vào lượt sinh SQL.
- Prompt của bước lọc có chỉ dẫn không làm theo mệnh lệnh nằm bên trong nội dung được lọc — phòng trường hợp tài liệu nghiệp vụ chứa văn bản trông giống chỉ thị.

**Đo được.** Model cắt từ khoảng 5,08 xuống còn **1,71 mảnh sự kiện** mỗi câu. Nó lọc mạnh tay hơn quy tắc khá nhiều.

**Bài báo.** [SAG — SQL-Retrieval Augmented Generation with Query-Time Dynamic Hyperedges](https://arxiv.org/abs/2606.15971).

Ba bậc "seeds → expansion → selector" cùng lấy ý tưởng từ SAG, và ba đặc điểm cốt lõi của SAG đều có mặt: tổ chức tài liệu thành cặp sự kiện–thực thể thay vì dựng đồ thị tri thức sẵn, giữ nguyên quan hệ nhiều chiều thay vì bẻ thành bộ ba, và sinh vùng lân cận tại lúc truy vấn qua thực thể dùng chung.

**Khác biệt lớn nhất, cần nói rõ trong luận văn:** SAG gốc được đánh giá trên bài toán **hỏi đáp nhiều bước** (HotpotQA, 2WikiMultiHopQA, MuSiQue), **không phải sinh SQL**. Chỉ số nổi bật của SAG là độ phủ truy hồi tài liệu, một đại lượng khác hẳn execution accuracy. Việc mang cơ chế này sang text-to-SQL là **chuyển giao ý tưởng sang bài toán mới**, không phải tái lập kết quả — và vì thế không có gì bảo đảm trước rằng nó sẽ có lợi ở đây. Ba bậc ablation tách riêng chính là để trả lời câu hỏi đó bằng số liệu.

---

### B6 — Cho chạy thử rồi sửa (ReACT)

**Là gì.** Thay vì tin vào câu SQL đầu tiên, hệ thống chạy thật câu đó rồi để model sửa dựa trên những gì quan sát được.

**Quy trình.**

1. Dựng ngữ cảnh và **đóng băng** — ngữ cảnh không đổi qua các vòng sửa, để chênh lệch chỉ đến từ việc sửa.
2. Model sinh câu SQL đầu tiên.
3. Chạy câu đó trên database ở chế độ chỉ đọc. Kết quả trả về được phân loại thành các trạng thái: chạy được, chạy được nhưng không có dòng nào, lỗi cú pháp, sai tên bảng/cột, sai kiểu dữ liệu, hết thời gian, hoặc vi phạm chính sách.
4. Quyết định: nếu chạy được (kể cả rỗng) thì dừng. Nếu model vừa sửa ra đúng câu giống hệt vòng trước thì dừng, tránh lặp vô ích. Nếu đã hết số vòng cho phép thì dừng.
5. Nếu chưa dừng: đưa câu SQL cũ cùng thông tin lỗi quan sát được cho model, yêu cầu sửa tối thiểu. Quay lại bước 3.
6. Khi dừng, chọn phương án tốt nhất trong số các phương án đã sinh, xếp theo trạng thái chạy trước, rồi tới độ tự tin, rồi tới độ ngắn gọn.

**An toàn khi chạy thử.** Database mở ở chế độ chỉ đọc và bất biến, bật cờ cấm ghi ở tầng driver, cài thêm bộ kiểm duyệt chặn mọi thao tác không phải đọc, cộng với giới hạn thời gian và giới hạn số dòng trả về. Ba vai trò của SQLite trong hệ thống — dữ liệu BIRD, bộ nhớ trạng thái của luồng xử lý, kho lưu trữ — được tách riêng, không dùng chung một file.

**Hai biến thể.** Một dùng ngữ cảnh đầy đủ như B5, một chỉ dùng ngữ cảnh như B4. Mục đích là tách bạch: nếu sửa lỗi chỉ có tác dụng khi ngữ cảnh giàu, thì đó là kết luận khác với việc nó có tác dụng độc lập.

**Điều đã thực sự xảy ra.** Vòng sửa **chưa chạy lần nào** trong cả hai run, vì bước dò tham số chọn số vòng tối đa bằng **0**. Trên tập dev 11 câu, ba lựa chọn 0, 1, 2 vòng cho điểm hoàn toàn bằng nhau, và khi hoà điểm thì quy tắc chọn ưu tiên phương án tốn ít token nhất. Vì vậy hai dòng B6 trong bảng kết quả thực chất đo "sinh SQL, chạy thử, lấy luôn kết quả đó", chưa đo được cơ chế sửa lỗi.

**Bài báo.** [Robust Text-to-SQL Generation with Execution-Guided Decoding](https://arxiv.org/abs/1807.03100) (Wang, Tatwawadi, Brockschmidt, Huang, Mao, Polozov, Singh, 2018).

**Bài báo.** (https://arxiv.org/pdf/2210.03629)

Ý tưởng cốt lõi trùng nhau: dùng kết quả chạy thật của chương trình làm tín hiệu để loại phương án sai, thay vì chỉ tin vào xác suất của model. **Khác biệt:** bài gốc lồng tín hiệu thực thi vào ngay trong quá trình giải mã, loại bỏ nhánh sai khi chương trình mới sinh được một phần; bản này để model sinh trọn câu rồi mới sửa ở vòng ngoài. Bài gốc cũng chạy trên các bộ dữ liệu đơn giản hơn nhiều (WikiSQL, ATIS, GeoQuery), nơi không gian câu SQL hẹp hơn BIRD rất nhiều.

*Ghi chú về trích dẫn:* tên "Execution-Guided Neural Program Decoding" là một bài cùng nhóm tác giả, công bố ở workshop, bàn về ý tưởng tổng quát cho sinh chương trình. Bản áp dụng cho text-to-SQL là bài ở link trên; nên trích bài này vì gần với B6 hơn.

---

### G1 — Model tự quyết đường đi

**Là gì.** Kịch bản duy nhất mà model là bên quyết định các bước tiếp theo, thay vì đi theo một luồng cố định.

**Quy trình.**

1. **Chọn nhánh.** Model đọc câu hỏi (kèm nhãn độ khó) và tự quyết hai việc: dùng kiểu ngữ cảnh nào trong ba kiểu — đưa hết, chỉ phần liên quan, hay có thêm sự kiện — và cần sinh mấy phương án SQL. Số phương án model đề xuất bị kẹp lại bởi một trần cho trước.
2. **Dựng ngữ cảnh** theo nhánh đã chọn.
3. **Sinh song song.** Toả ra N nhánh chạy đồng thời, mỗi nhánh sinh một phương án theo một chiến lược khác nhau: ưu tiên phép nối bảng, ưu tiên phép gộp, hoặc ưu tiên xử lý giá trị chữ. Các phương án được gom về một chỗ.
4. **Chạy thử tất cả** ở chế độ chỉ đọc.
5. **Chọn phương án.** Nếu chỉ có một phương án thì lấy luôn. Nếu nhiều hơn, đưa cả câu hỏi, các câu SQL và kết quả chạy của từng câu cho model chọn. Model không được thấy đáp án. Nếu model trả về ID không hợp lệ thì rơi về cách chọn bằng quy tắc.

**Vì sao gọi là agentic.** Vì model quyết định nhánh và số phương án. Nếu việc chọn nhánh làm bằng luật cứng thì đây chỉ là một luồng xử lý có rẽ nhánh, không phải agent. Đây là ranh giới dự án đặt ra để không gọi nhầm tên.

**Model đã chọn gì trên 62 câu.**

| Nhánh model chọn | Số câu |
|---|---|
| Chỉ phần liên quan (như B4) | 45 |
| Đưa hết (như P1) | 14 |
| Có thêm sự kiện (như B5) | 3 |

Chỉ 3/62 câu đi nhánh có sự kiện, nên trong G1 phần ngữ cảnh dạng sự kiện gần như không được kích hoạt (trung bình 0,11 sự kiện mỗi câu). Model tự nó hầu như luôn chọn nhánh B4.

**Về số phương án.** Run đầu đặt trần 1 nên không đo được lợi ích của nhiều phương án. Run sau đặt trần 2, và model thực sự sinh 2 phương án ở 45/62 câu (trung bình 1,73).

**Bài báo.** [CHESS](https://arxiv.org/abs/2405.16755) — tham khảo về cách chia hệ thống thành các thành phần chuyên trách và cách điều phối chúng. **Khác biệt:** CHESS đi theo một pipeline cố định giữa các tác nhân; G1 để model tự chọn nhánh và tự chọn số phương án, nên phần định tuyến là đóng góp riêng chứ không lấy từ CHESS.

---
