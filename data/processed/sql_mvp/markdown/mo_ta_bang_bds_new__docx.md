**MỤC LỤC**

[1. Danh mục dùng chung 1](#_heading=h.qezms6ujqiw5)

[1.1. Bảng V\_USER\_PRECINCT\_PERMISSION 1](#_heading=h.75kw53zeb6d)

[1.2. Bảng PRECINCT 1](#_heading=h.259zvh70nfe2)

[2. Dữ liệu điểm bán 1](#_heading=h.r8brk5af1z7z)

[2.1. Bảng POINT\_OF\_SALE 1](#_heading=h.eoljx8sqtp9p)

[2.2. Bảng V\_BDS\_NEW\_SUB\_SALE\_POINT 1](#_heading=h.pclt2jwjtzpm)

[2.3. Bảng NHAN\_VIEN\_CHAM\_SOC\_LONG 1](#_heading=h.ycewrekxgl6p)

[2.4. Bảng EMPLOYEE\_SALES 1](#_heading=h.cts2yaxzgks8)

[3. Dữ liệu kinh doanh 1](#_heading=h.f3vkc8y09mej)

[3.1. Bảng V\_BDS\_NEW\_SUB\_SHOP 1](#_heading=h.j1ky93lsohce)

[3.2. Bảng TABLE(pck\_report\_chatbox.get\_new\_sub\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name))) 1](#_heading=h.a0vf20fd64kq)

[- Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa. 1](#_heading=h.5mpcimowrlpy)

[4. Vùng phủ địa lý 1](#_heading=h.gfa1uvpicnkm)

[4.1. Bảng PUBLIC\_LOCATION 1](#_heading=h.mh6ozrjhn9mb)

[5. Vùng phủ kỹ thuật 1](#_heading=h.czr7vqpzdixn)

[5.1. Bảng V\_BDS\_SITE 1](#_heading=h.5yp3vowmm6sm)

[6. Báo cáo doanh thu TKC và VLR 1](#_heading=h.3sxt62plo848)

[6.1. Bảng TABLE(pck\_report\_chatbox.get\_vlr\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name))) 1](#_heading=h.6lp1w6rc9qag)

[- Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa. 1](#_heading=h.ay0cnwd0a0gm)

[6.2. Bảng TABLE(pck\_report\_chatbox.get\_rev\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name))) 1](#_heading=h.b9maggrumu2j)

[- Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa. 1](#_heading=h.54x7pv1nlakr)

[7. Quản lý công việc và dự án 1](#_heading=h.2zgcj4mah8tc)

[7.1. Bảng LOCATION\_GROUP 1](#_heading=h.gtjcqs21keb9)

[7.2. Bảng PROJECT 1](#_heading=h.9jiojrldqcc4)

[7.3. Bảng LOCATION 1](#_heading=h.rm9pvxiudwv4)

[7.4. Bảng V\_MAN\_TASK 1](#_heading=h.4tytma7u9km9)

[7.5. Bảng V\_MAN\_TASK\_PROGRESS 1](#_heading=h.cct9ndhhxw9b)

[7.6. Bảng V\_CAT\_STAFF 1](#_heading=h.4pcirakav9d2)

# Danh mục dùng chung

## Bảng V\_USER\_PRECINCT\_PERMISSION
* Ý nghĩa của bảng: Lưu trữ quyền truy cập của user theo phường/xã (user được xem thông tin của các phường/xã nào)
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| USER\_NAME | VARCHAR2 | Mã user (ví dụ: HUY.NGUYEN) |
| USER\_ID | NUMBER | Mã định danh user |
| PRECINCT\_CODE | VARCHAR2 | Mã phường/xã mà user được truy cập (ví dụ: VTAU) |
| PRECINCT\_NAME | VARCHAR2 | Tên phường/xã mà user được truy cập (ví dụ: Phường Vũng Tàu) |
| HUB\_CODE | VARCHAR2 | Hub quản lý (mã hub) của phường/xã mà user được truy cập (ví dụ: VT.1) |
| BRANCH\_CODE | VARCHAR2 | Mã TTKD/chi nhánh của phường/xã mà user được truy cập (gồm Tên TTKD/chi nhánh (gồm 7 giá trị (tương ứng với 7 TTKD): HCM010000, HCM020000, HCM030000, HCM040000, HCM050000, HCM060000, HCM070000) |
| BRANCH\_NAME | VARCHAR2 | Tên TTKD/chi nhánh (gồm 7 giá trị (tương ứng với 7 TTKD): Trung Tâm Kinh Doanh Sài Gòn, Trung Tâm Kinh Doanh Gia Định, Trung Tâm Kinh Doanh Bến Thành, Trung Tâm Kinh Doanh Gò Vấp, Trung Tâm Kinh Doanh Thủ Đức, Trung Tâm Kinh Doanh Bình Dương, Trung Tâm Kinh Doanh Vũng Tàu) |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Nếu user hỏi về các dữ liệu liên quan tới PTM, VLR, TKC, trạm, ... thì luôn luôn map với bảng này để chỉ trả về dữ liệu trong phạm vi quyền truy cập của user.
* Dữ liệu tổng khoảng 10000 dòng.

-----------------------------------------------------------------------------------------------------------

## Bảng PRECINCT
* Ý nghĩa của bảng: Lưu trữ thông tin của của các phường/xã
* Chi tiết các cột trong bảng:

| **Cột2** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Khóa chính |
| CODE | VARCHAR2 | Mã phường xã |
| NAME | VARCHAR2 | Tên phường xã |
| BRANCH\_NAME | VARCHAR2 | Tên TTKD |
| HUB | VARCHAR2 | Tên Hub |
| BRANCH\_CODE | VARCHAR2 | Mã TTKD |

* Mối liên kết:
* Liên kết với các bảng khác qua cột CODE
* Ghi chú:
* Thường truy xuất vào bảng này để lấy các thông tin thêm của phường/xã (phường/xã thuộc hub gì, TTKD gì, ...) nếu bảng gốc không có đủ thông tin.
* Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

# Dữ liệu điểm bán

## Bảng POINT\_OF\_SALE
* Ý nghĩa của bảng: Lưu trữ thông tin của các điểm bán
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Mã định danh điểm bán (ví dụ: 17) |
| ADDRESS | VARCHAR2 | Địa chỉ điểm bán |
| BRANCH\_NAME | VARCHAR2 | Tên TTKD/chi nhánh (gồm 7 giá trị (tương ứng với 7 TTKD): Trung Tâm Kinh Doanh Sài Gòn, Trung Tâm Kinh Doanh Gia Định, Trung Tâm Kinh Doanh Bến Thành, Trung Tâm Kinh Doanh Gò Vấp, Trung Tâm Kinh Doanh Thủ Đức, Trung Tâm Kinh Doanh Bình Dương, Trung Tâm Kinh Doanh Vũng Tàu) |
| EMP\_NAME | VARCHAR2 | Tên nhân viên phụ trách |
| HUB | VARCHAR2 | Hub quản lý (mã hub) (ví dụ: VT.1) |
| HUB\_LEADER | VARCHAR2 | Tên trưởng Hub |
| LAT | VARCHAR2 | Vĩ độ (ví dụ: 10.765590) |
| LON | VARCHAR2 | Kinh độ (ví dụ: 106.662547) |
| NVBH\_CODE | VARCHAR2 | Mã nhân viên bán hàng |
| PARENT\_SALE\_CODE | VARCHAR2 | Mã nhân viên/quản lý cấp trên |
| PARENT\_SALE\_NAME | VARCHAR2 | Tên nhân viên/quản lý cấp trên |
| PHONE\_NUMBER | VARCHAR2 | Số điện thoại điểm bán |
| PRECINCT\_NAME | VARCHAR2 | Tên phường/xã (ví dụ: Phường Diên Hồng) |
| SALE\_CODE | VARCHAR2 | Mã điểm bán |
| SALE\_NAME | VARCHAR2 | Tên điểm bán (ví dụ: ĐBH Minh Quang) |
| SALE\_TYPE | VARCHAR2 | Loại điểm bán (ví dụ: Loại 2) |
| PRECINCT\_CODE | VARCHAR2 | Mã phường/xã (ví dụ: VTAU) |

* Mối liên kết:
* Liên kết với các bảng khác qua cột SALE\_CODE và PRECINCT\_CODE.
* Ghi chú:
* Thường truy xuất vào bảng này để lấy các thông tin thêm của điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...) nếu bảng gốc không có đủ thông tin.
* Dữ liệu tổng khoảng 2000 dòng (tương ứng với khoảng 2000 điểm bán).

-----------------------------------------------------------------------------------------------------------

## Bảng V\_BDS\_NEW\_SUB\_SALE\_POINT
* Ý nghĩa của bảng: Lưu trữ thông tin phát triển mới thuê bao của kênh điểm bán
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| SALE\_CODE | VARCHAR2 | Mã điểm bán (ví dụ: HCM01DHON\_0009) |
| SUM\_DATE | VARCHAR2 | Ngày tổng hợp dữ liệu (luôn luôn là ngày hiện tại) (ví dụ: 17/06/2026) |
| MC\_QUANTITY\_DAY | NUMBER | Số lượng thuê bao trả trước trong ngày hiện tại (ví dụ: 1) |
| MF\_QUANTITY\_DAY | NUMBER | Số lượng thuê bao trả sau trong ngày hiện tại (ví dụ: 0) |
| ALL\_QUANTITY\_DAY | NUMBER | Tổng số thuê bao trong ngày hiện tại (ví dụ: 1) |
| SUM\_MONTH | VARCHAR2 | Tháng tổng hợp dữ liệu (luôn luôn là tháng hiện tại) (ví dụ: 06/2026) |
| MC\_QUANTITY\_MONTH | NUMBER | Số lượng thuê bao trả trước trong tháng hiện tại (ví dụ: 15) |
| MF\_QUANTITY\_MONTH | NUMBER | Số lượng thuê bao trả sau trong tháng hiện tại (ví dụ: 0) |
| ALL\_QUANTITY\_MONTH | NUMBER | Tổng số thuê bao trong tháng hiện tại (ví dụ: 15) |
| SUM\_YEAR | VARCHAR2 | Năm tổng hợp dữ liệu (năm hiện tại) (ví dụ: 2026) |
| MC\_QUANTITY\_YEAR | NUMBER | Số lượng thuê bao trả trước trong năm hiện tại (ví dụ: 30) |
| MF\_QUANTITY\_YEAR | NUMBER | Số lượng thuê bao trả sau trong năm hiện tại (ví dụ: 0) |
| ALL\_QUANTITY\_YEAR | NUMBER | Tổng số thuê bao trong năm hiện tại (ví dụ: 30) |
| MC\_QUANTITY\_ALL\_YEAR | NUMBER | Tổng số thuê bao trả trước trong tất cả các năm (trong toàn bộ lịch sử được ghi nhận) (ví dụ: 39) |
| MF\_QUANTITY\_ALL\_YEAR | NUMBER | Lũy kế thuê bao trả sau trong tất cả các năm (trong toàn bộ lịch sử được ghi nhận) (ví dụ: 1) |
| ALL\_QUANTITY\_ALL\_YEAR | NUMBER | Tổng lũy kế thuê bao trong tất cả các năm (trong toàn bộ lịch sử được ghi nhận) (ví dụ: 40) |
| START\_DATE\_LAST\_WEEK | VARCHAR2 | Ngày bắt đầu tuần trước (lấy thứ 5 là ngày bắt đầu tuần) (ví dụ: 04/06/2026) |
| LAST\_DATE\_LAST\_WEEK | VARCHAR2 | Ngày kết thúc tuần trước (lấy thứ 4 là ngày kết thúc tuần) (ví dụ: 10/06/2026) |
| MC\_QUANTITY\_LAST\_WEEK | NUMBER | Số lượng thuê bao trả trước trong tuần trước (ví dụ: 2) |
| MF\_QUANTITY\_LAST\_WEEK | NUMBER | Số lượng thuê bao trả sau trong tuần trước (ví dụ: 0) |
| ALL\_QUANTITY\_LAST\_WEEK | NUMBER | Tổng số thuê bao trong tuần trước (ví dụ: 2) |
| START\_DATE\_THIS\_WEEK | VARCHAR2 | Ngày bắt đầu tuần hiện tại (lấy thứ 5 là ngày bắt đầu tuần) (ví dụ: 11/06/2026) |
| LAST\_DATE\_THIS\_WEEK | VARCHAR2 | Ngày kết thúc tuần hiện tại (lấy thứ 4 là ngày kết thúc tuần) (ví dụ: 17/06/2026) |
| MC\_QUANTITY\_THIS\_WEEK | NUMBER | Số lượng thuê bao trả trước trong tuần hiện tại (ví dụ: 8) |
| MF\_QUANTITY\_THIS\_WEEK | NUMBER | Số lượng thuê bao trả sau trong tuần hiện tại (ví dụ: 0) |
| ALL\_QUANTITY\_THIS\_WEEK | NUMBER | Tổng số thuê bao trong tuần hiện tại (ví dụ: 8) |
| SALE\_POINT\_QUANTITY\_LAST\_WEEK | NUMBER | Điểm bán này có phát triển thuê bao hay chưa, tính từ ngày đầu tháng hiện tại đến ngày bắt đầu tuần trước (START\_DATE\_LAST\_WEEK). Giá trị: 0: chưa phát triển thuê bao nào, 1: đã có phát triển thuê bao |
| SALE\_POINT\_QUANTITY\_THIS\_WEEK | NUMBER | Điểm bán này có phát triển thuê bao hay chưa, tính từ ngày đầu tháng hiện tại đến ngày bắt đầu tuần hiện tại (START\_DATE\_THIS\_WEEK). Giá trị: 0: chưa phát triển thuê bao nào, 1: đã có phát triển thuê bao |

* Mối liên kết:
* Liên kết với các bảng khác qua cột SALE\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để lấy các thông tin về số lượng PTM TB của kênh điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...).
* Dữ liệu tổng khoảng 2000 dòng (tương ứng với khoảng 2000 điểm bán).

-----------------------------------------------------------------------------------------------------------

## Bảng NHAN\_VIEN\_CHAM\_SOC\_LONG
* Ý nghĩa của bảng: Lưu trữ lịch sử chăm sóc điểm bán của nhân viên chăm sóc
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| INSERT\_DATE | DATE | Ngày ghi nhận dữ liệu (ví dụ: 08/06/2026 14:30:12) |
| NGAY\_CHAM\_SOC | DATE | Ngày chăm sóc điểm bán (ví dụ: 01/06/2026 00:00:00) |
| MA\_DIEM\_BAN | VARCHAR2 | Mã điểm bán |
| TEN\_DIEM\_BAN | VARCHAR2 | Tên điểm bán (ví dụ: ĐBH Minh Quang) |
| NGUOI\_GIAO\_KE\_HOACH | VARCHAR2 | Người giao kế hoạch chăm sóc |
| NHAN\_VIEN\_CHAM\_SOC | VARCHAR2 | Họ tên nhân viên chăm sóc điểm bán |
| MA\_NHAN\_VIEN\_CHAM\_SOC | VARCHAR2 | Mã nhân viên chăm sóc điểm bán |

* Mối liên kết:
* Liên kết với các bảng khác qua cột MA\_DIEM\_BAN và MA\_NHAN\_VIEN\_CHAM\_SOC.
* Ghi chú:
* Thường truy xuất vào bảng này để lấy các thông tin thêm của điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...) nếu bảng gốc không có đủ thông tin.
* Dữ liệu mới nhất là dữ liệu ngày N-1.
* Dữ liệu tổng khoảng 30000 dòng.

-----------------------------------------------------------------------------------------------------------

## Bảng EMPLOYEE\_SALES
* Ý nghĩa của bảng: Lưu trữ thông tin của các nhân viên chăm sóc
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Khóa chính, định danh duy nhất của bản ghi |
| BRANCH\_NAME | VARCHAR2 | Tên trung tâm kinh doanh / chi nhánh |
| EMP\_CODE | VARCHAR2 | Mã nhân viên |
| HUB | VARCHAR2 | Tên Hub / khu vực quản lý |
| HUB\_LEADER | VARCHAR2 | Tên hoặc mã trưởng Hub |
| SALES\_CODE | VARCHAR2 | Mã Điểm Bán |
| SALES\_NAME | VARCHAR2 | Tên nhân viên bán hàng |

* Mối liên kết:
* Liên kết với các bảng khác qua cột SALES\_CODE và SALES\_NAME.
* Ghi chú:
* Thường truy xuất vào bảng này để lấy các thông tin thêm của điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...) nếu bảng gốc không có đủ thông tin.
* Dữ liệu mới nhất là dữ liệu ngày N-1.
* Dữ liệu tổng khoảng 100 dòng (tương ứng với 100 nhân viên chăm sóc).

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

# Dữ liệu kinh doanh

## Bảng V\_BDS\_NEW\_SUB\_SHOP
* Ý nghĩa của bảng: Lưu trữ thông tin phát triển mới thuê bao của kênh cửa hàng và đại lý
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| SHOP\_CODE | VARCHAR2 | Mã cửa hàng |
| SHOP\_TYPE | VARCHAR2 | Loại cửa hàng (101: cửa hàng, 201: đại lý uỷ quyền, 202: đại lý chuyên) |
| NAME | VARCHAR2 | Tên cửa hàng |
| ADDRESS | VARCHAR2 | Địa chỉ cửa hàng |
| LATITUDE | NUMBER | Vĩ độ |
| LONGITUDE | NUMBER | Kinh độ |
| STATUS | NUMBER | Trạng thái cửa hàng |
| SUM\_DATE | VARCHAR2 | Ngày tổng hợp dữ liệu |
| ALL\_QUANTITY\_DAY | NUMBER | Tổng số thuê bao trong ngày |
| MC\_QUANTITY\_DAY | NUMBER | Số lượng thuê bao trả trước trong ngày |
| MF\_QUANTITY\_DAY | NUMBER | Số lượng thuê bao trả sau trong ngày |
| SUM\_MONTH | VARCHAR2 | Tháng tổng hợp dữ liệu |
| ALL\_QUANTITY\_MONTH | NUMBER | Tổng số thuê bao trong tháng |
| MC\_QUANTITY\_MONTH | NUMBER | Số lượng thuê bao trả trước trong tháng |
| MF\_QUANTITY\_MONTH | NUMBER | Số lượng thuê bao trả sau trong tháng |
| BRANCH\_CODE | VARCHAR2 | Mã TTKD/chi nhánh |
| PRECINCT\_CODE | VARCHAR2 | Mã phường/xã |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để lấy số lượng PTM TB của kênh cửa hàng và đại lý.
* Chỉ được sử dụng SHOP\_TYPE in ('101', '201', '202'), các giá trị khác không được SELECT
* Dữ liệu tổng khoảng 600 dòng.

-----------------------------------------------------------------------------------------------------------

## Bảng TABLE(pck\_report\_chatbox.get\_new\_sub\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name)))
* Ý nghĩa của bảng: Lưu trữ thông tin phát triển mới thuê bao của các kênh kinh doanh (kênh cửa hàng, kênh chuỗi, kênh đại lý chuyên, kênh đại lý ủy quyền, kênh online, kênh quản lý, kênh Khách hàng cá nhân, kênh Khách hàng doanh nghiệp)
* Chi tiết các cột trong bảng:

| **Tên cột** | **Mô tả** |
| --- | --- |
| PRECINCT\_CODE | Mã phường/xã |
| PRECINCT\_NAME | Tên phường/xã |
| SUM\_DATE | Ngày báo cáo dữ liệu thuê bao phát triển mới |
| CUAHANG\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Cửa hàng |
| CHUOI\_DIA\_PHUONG\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh chuỗi địa phương |
| DLC\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Đại lý chuyên |
| DLUQ\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Đại lý ủy quyền |
| ONL\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Online |
| OTHERS\_DAY | Số lượng thuê bao phát triển mới trong ngày qua các kênh khác |
| QUAN\_LY\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Quản lý |
| TKD\_KHCN\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Tổ KD KHCN |
| TKD\_KHDN\_DAY | Số lượng thuê bao phát triển mới trong ngày qua kênh Tổ KD KHDN |
| SUM\_MONTH | Tháng báo cáo dữ liệu thuê bao phát triển mới |
| CUAHANG\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Cửa hàng |
| CHUOI\_DIA\_PHUONG\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh chuỗi địa phương |
| DLC\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Đại lý chuyên |
| DLUQ\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Đại lý ủy quyền |
| ONL\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Online |
| OTHERS\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua các kênh khác |
| QUAN\_LY\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Quản lý |
| TKD\_KHCN\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Tổ KD KHCN |
| TKD\_KHDN\_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh Tổ KD KHDN |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để lấy số lượng PTM TB của các kênh (kênh cửa hàng, kênh chuỗi, kênh đại lý chuyên, kênh đại lý ủy quyền, kênh online, kênh quản lý, kênh Khách hàng cá nhân, kênh Khách hàng doanh nghiệp), ngoại trừ kênh điểm bán.
* Khi gọi, truyền biến date (ngày phát triển thuê bao (cột SUM\_DATE)) và user\_name (user gọi truy cập dữ liệu)
* **Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa.**
* Dữ liệu mới nhất là ngày N (ngày hiện tại)
* Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

# Vùng phủ địa lý

## Bảng PUBLIC\_LOCATION
* Ý nghĩa của bảng: Lưu trữ thông tin các điểm dữ liệu địa lý hành chính dùng để hiển thị lên bản đồ số, bao gồm các Trung tâm hành chính, Trụ sở công an, Cảng biển, Bệnh viện, Cao đẳng, Trạm PCCC, Doanh Nghiệp, Đại học
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Khoá chính |
| TYPE | VARCHAR2 | Loại địa điểm, bao gồm các giá trị: 'TTHC', 'CA', 'CB', 'BV', 'CD', 'PCCC', 'DN', 'DH' |
| TYPE\_NAME | VARCHAR2 | Tên loại địa điểm, bao gồm các giá trị: 'Trung tâm hành chính', 'Trụ sở công an', 'Cảng biển', 'Bệnh viện', 'Cao đẳng', 'Trạm PCCC', 'Doanh Nghiệp', 'Đại học' |
| NAME | VARCHAR2 | Tên địa điểm |
| ADDRESS | VARCHAR2 | Địa chỉ |
| LATITUDE | NUMBER | Vĩ độ |
| LONGITUDE | NUMBER | Kinh độ |
| STATUS | NUMBER | Trạng thái |
| BRAND\_CODE | VARCHAR2 | Mã TTKD/chi nhánh |
| PRECINCT\_CODE | VARCHAR2 | Mã phường/xã |
| PRECINCT\_NAME | VARCHAR2 | Tên phường/xã |
| HUB | VARCHAR2 | Hub quản lý |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để lấy số lượng PTM TB của kênh cửa hàng và đại lý.
* Dữ liệu tổng khoảng 5000 dòng.

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

# Vùng phủ kỹ thuật

## Bảng V\_BDS\_SITE
* Ý nghĩa của bảng: Lưu trữ thông tin về cell/trạm BTS.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| CELL\_SITE | VARCHAR2 | Mã trạm BTS / Cell Site |
| LATITUDE | NUMBER | Vĩ độ |
| LONGITUDE | NUMBER | Kinh độ |
| STATUS | NUMBER | Trạng thái trạm (1: đang hoạt động, 0: không hoạt động/OFF) |
| SUM\_DATE | VARCHAR2 | Ngày tổng hợp dữ liệu |
| VLR\_ALL\_DAY | NUMBER | Tổng VLR trong ngày |
| VLR\_3G\_DAY | NUMBER | VLR 3G trong ngày |
| VLR\_4G\_DAY | NUMBER | VLR 4G trong ngày |
| VLR\_5G\_DAY | NUMBER | VLR 5G trong ngày |
| SUM\_MONTH | VARCHAR2 | Tháng tổng hợp dữ liệu |
| VLR\_ALL\_MONTH | NUMBER | Tổng VLR trong tháng |
| VLR\_2G\_MONTH | NUMBER | VLR 2G trong tháng |
| VLR\_3G\_MONTH | NUMBER | VLR 3G trong tháng |
| VLR\_4G\_MONTH | NUMBER | VLR 4G trong tháng |
| VLR\_5G\_MONTH | NUMBER | VLR 5G trong tháng |
| CLTC\_MONTH | VARCHAR2 | Tháng ghi nhận chênh lệch thu chi |
| CLTC | NUMBER | Chỉ số chất lượng chênh lệch thu chi |
| BRANCH\_CODE | VARCHAR2 | Mã TTKD/chi nhánh |
| PRECINCT\_CODE | VARCHAR2 | Mã phường/xã |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để thông tin về cell/trạm BTS và các dữ liệu VLR, CLTS của cell/trạm BTS.
* Luôn thêm điều kiện STATUS = 1 khi truy xuất, vì chỉ cần quan tâm dữ liệu của các trạm/cell cùng hoạt động
* Dữ liệu tổng khoảng 30000 dòng.

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

# Báo cáo doanh thu TKC và VLR

## Bảng TABLE(pck\_report\_chatbox.get\_vlr\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name)))
* Ý nghĩa của bảng: Lưu trữ thông tin số lượng VLR.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Mô tả** |
| --- | --- |
| PRECINCT\_CODE | Mã phường/xã |
| PRECINCT\_NAME | Tên phường/xã |
| SUM\_DATE | Ngày báo cáo dữ liệu VLR |
| MOBIFONE\_VLR\_QUANTITY\_DAY | Số lượng VLR MobiFone trong ngày |
| SAYMEE\_VLR\_QUANTITY\_DAY | Số lượng VLR Saymee trong ngày |
| SUM\_MONTH | Tháng báo cáo dữ liệu VLR |
| MOBIFONE\_VLR\_QUANTITY\_MONTH | Số lượng VLR MobiFone trong tháng |
| SAYMEE\_VLR\_QUANTITY\_MONTH | Số lượng VLR Saymee trong tháng |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để lấy số lượng VLR.
* Khi gọi, truyền biến date (ngày phát triển thuê bao (cột SUM\_DATE)) và user\_name (user gọi truy cập dữ liệu)
* **Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa.**
* Dữ liệu mới nhất là ngày N-2.
* Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

-----------------------------------------------------------------------------------------------------------

## Bảng TABLE(pck\_report\_chatbox.get\_rev\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name)))
* Ý nghĩa của bảng: Lưu trữ thông tin doanh thu tài khoản chính.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Mô tả** |
| --- | --- |
| PRECINCT\_CODE | Mã phường/xã |
| PRECINCT\_NAME | Tên phường/xã |
| SUM\_DATE | Ngày báo cáo doanh thu |
| MOBIFONE\_TKC\_REV\_DAY | Doanh thu TKC MobiFone trong ngày |
| SAYMEE\_TKC\_REV\_DAY | Doanh thu TKC Saymee trong ngày |
| BHM\_REV\_DAY | Doanh thu BHM trong ngày |
| SUM\_MONTH | Tháng báo cáo doanh thu |
| MOBIFONE\_TKC\_REV\_MONTH | Doanh thu TKC MobiFone trong tháng |
| SAYMEE\_TKC\_REV\_MONTH | Doanh thu TKC Saymee trong tháng |
| BHM\_REV\_MONTH | Doanh thu BHM trong tháng |

* Mối liên kết:
* Liên kết với các bảng khác qua cột PRECINCT\_CODE.
* Ghi chú:
* Truy xuất vào bảng này để lấy doanh thu tài khoản chính.
* Khi gọi, truyền biến date (ngày phát triển thuê bao (cột SUM\_DATE)) và user\_name (user gọi truy cập dữ liệu)
* **Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa.**
* Dữ liệu mới nhất là ngày N-2.
* Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

# Quản lý công việc và dự án

## Bảng LOCATION\_GROUP
* Ý nghĩa của bảng: Lưu trữ thông tin nhóm địa điểm.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Khoá chính |
| Name | VARCHAR2 | Tên nhóm địa điểm |

* Mối liên kết:
* Liên kết với các bảng khác qua cột ID.
* Ghi chú:
* Truy xuất vào bảng này để lấy thông tin nhóm địa điểm.
* Dữ liệu tổng có 1 dòng (hiện chỉ có 1 nhóm địa điểm là Uỷ Ban Nhân Dân).

-----------------------------------------------------------------------------------------------------------

## Bảng PROJECT
* Ý nghĩa của bảng: Lưu trữ thông tin dự án.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Khoá chính |
| NAME | VARCHAR2 | Tên dự án |
| LOCATION\_GROUP\_ID | NUMBER | Mã nhóm địa điểm liên kết |

* Mối liên kết:
* Liên kết với các bảng khác qua cột ID và LOCATION\_GROUP\_ID.
* Ghi chú:
* Truy xuất vào bảng này để lấy thông tin nhóm địa điểm.
* Dữ liệu tổng có 1 dòng (hiện chỉ có 1 nhóm địa điểm là Triển khai hạ tầng CNTT 168 Xã).

-----------------------------------------------------------------------------------------------------------

## Bảng LOCATION
* Ý nghĩa của bảng: Lưu trữ thông tin địa điểm.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Mã định danh địa điểm |
| ADDRESS | VARCHAR2 | Địa chỉ địa điểm |
| LAT | NUMBER | Vĩ độ |
| LON | NUMBER | Kinh độ |
| NAME | VARCHAR2 | Tên địa điểm |
| LOCATION\_GROUP\_ID | NUMBER | Mã nhóm địa điểm |
| PROJECT\_ID | NUMBER | Mã dự án |
| PRECINCT\_NAME | VARCHAR2 | Tên phường/xã |
| HUB | VARCHAR2 | Hub quản lý |
| BRANCH\_NAME | VARCHAR2 | Tên TTKD/chi nhánh |

* Mối liên kết:
* Liên kết với các bảng khác qua cột ID, LOCATION\_GROUP\_ID và PRECINCT\_NAME.
* Ghi chú:
* Truy xuất vào bảng này để lấy thông tin địa điểm.
* Dữ liệu tổng khoảng 300 dòng.

-----------------------------------------------------------------------------------------------------------

## Bảng V\_MAN\_TASK
* Ý nghĩa của bảng: Lưu trữ thông tin các công việc được khai báo.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Mã định danh công việc |
| CREATED\_DATE | TIMESTAMP | Thời gian tạo bản ghi |
| END\_DATE | TIMESTAMP | Ngày kết thúc công việc |
| NAME | VARCHAR2 | Tên công việc |
| PRIORITY | VARCHAR2 | Mức độ ưu tiên |
| START\_DATE | TIMESTAMP | Ngày bắt đầu công việc |
| PROGRESS\_ID | NUMBER | Tiến độ thực hiện |
| location\_id | NUMBER | Mã địa điểm |
| project\_id | NUMBER | Mã dự án |
| assigner\_staff\_id | NUMBER | Mã Người giao |
| assignee\_staff\_id | NUMBER | Mã Người nhận |

* Mối liên kết:
* Liên kết với các bảng khác qua cột ID, PROGRESS\_ID , LOCATION\_ID, PROJECT\_ID, assigner\_staff\_id và assignee\_staff\_id.
* Ghi chú:
* Truy xuất vào bảng này để lấy thông tin công việc.
* Dữ liệu tổng khoảng 20000 dòng.

-----------------------------------------------------------------------------------------------------------

## Bảng V\_MAN\_TASK\_PROGRESS
* Ý nghĩa của bảng: Lưu trữ thông tin tiến độ công việc.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Mã định danh tiến độ công việc |
| CREATED\_DATE | TIMESTAMP | Thời gian tạo bản ghi |
| PERCENT | NUMBER | Phần trăm hoàn thành |
| TASK\_ID | NUMBER | Mã công việc |

* Mối liên kết:
* Liên kết với các bảng khác qua cột ID, và TASK\_ID.
* Ghi chú:
* Truy xuất vào bảng này để lấy thông tin tiến độ công việc.
* Dữ liệu tổng khoảng 30000 dòng.

-----------------------------------------------------------------------------------------------------------

## Bảng V\_CAT\_STAFF
* Ý nghĩa của bảng: Lưu trữ thông tin nhân viên của công việc.
* Chi tiết các cột trong bảng:

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| ID | NUMBER | Mã định danh người dùng |
| FULL\_NAME | VARCHAR2 | Họ và tên người dùng |
| GENDER | NUMBER | Giới tính |
| ISDN | VARCHAR2 | Số thuê bao/số điện thoại |

* Mối liên kết:
* Liên kết với các bảng khác qua cột ID.
* Ghi chú:
* Truy xuất vào bảng này để lấy thông tin nhân viên của công việc.
* Dữ liệu tổng khoảng 500 dòng.

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*
