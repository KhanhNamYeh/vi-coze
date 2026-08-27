## MỤC LỤC

| 1. Danh mục dùng chung.......................................................................................................................... 1      | 1. Danh mục dùng chung.......................................................................................................................... 1                                                                             | 1. Danh mục dùng chung.......................................................................................................................... 1      |
|---------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
|                                                                                                                                                         | 1.1. Bảng                                                                                                                                                                                                                      | V_USER_PRECINCT_PERMISSION.............................................................................. 1                                              |
| 1.2.                                                                                                                                                    | Bảng PRECINCT.........................................................................................................................                                                                                         | 1                                                                                                                                                       |
| 2. Dữ liệu điểm bán...................................................................................................................................1 | 2. Dữ liệu điểm bán...................................................................................................................................1                                                                        | 2. Dữ liệu điểm bán...................................................................................................................................1 |
| 2.1.                                                                                                                                                    | Bảng POINT_OF_SALE..............................................................................................................1                                                                                              |                                                                                                                                                         |
| 2.2.                                                                                                                                                    | Bảng V_BDS_NEW_SUB_SALE_POINT.................................................................................                                                                                                                 | 1                                                                                                                                                       |
| 2.3.                                                                                                                                                    | Bảng NHAN_VIEN_CHAM_SOC_LONG.................................................................................1                                                                                                                 |                                                                                                                                                         |
| 2.4.                                                                                                                                                    | Bảng EMPLOYEE_SALES.........................................................................................................1                                                                                                  |                                                                                                                                                         |
| 3. Dữ liệu kinh doanh................................................................................................................................1  | 3. Dữ liệu kinh doanh................................................................................................................................1                                                                         | 3. Dữ liệu kinh doanh................................................................................................................................1  |
| 3.1.                                                                                                                                                    | Bảng V_BDS_NEW_SUB_SHOP...............................................................................................1                                                                                                        |                                                                                                                                                         |
| 3.2. (TO_DATE(TO_CHAR(:date),                                                                                                                           | Bảng TABLE(pck_report_chatbox.get_new_sub_data_by_precinct 'dd/mm/yyyy'),                                                                                                                                                      | UPPER(:user_name)))...................................................1                                                                                 |
| - Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng                                                                                    | - Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng                                                                                                                                                           | - Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng                                                                                    |
|                                                                                                                                                         | V_USER_PRECINCT_PERMISSION để lọc quyền nữa.........................................................................1                                                                                                          |                                                                                                                                                         |
| 4.                                                                                                                                                      | Vùng phủ địa lý.....................................................................................................................................1                                                                          |                                                                                                                                                         |
|                                                                                                                                                         | 4.1. Bảng PUBLIC_LOCATION........................................................................................................                                                                                              | 1                                                                                                                                                       |
| 5.                                                                                                                                                      | Vùng phủ kỹ thuật.................................................................................................................................1                                                                            |                                                                                                                                                         |
|                                                                                                                                                         | 5.1. Bảng V_BDS_SITE......................................................................................................................1                                                                                    |                                                                                                                                                         |
| 6.                                                                                                                                                      | Báo cáo doanh thu TKC và VLR..........................................................................................................1                                                                                        |                                                                                                                                                         |
|                                                                                                                                                         | 6.1. Bảng TABLE(pck_report_chatbox.get_vlr_data_by_precinct (TO_DATE(TO_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user_name)))......................................................................................................1 |                                                                                                                                                         |
| - Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V_USER_PRECINCT_PERMISSION                                                         | - Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V_USER_PRECINCT_PERMISSION                                                                                                                                | - Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V_USER_PRECINCT_PERMISSION                                                         |
|                                                                                                                                                         | để lọc quyền nữa.........................................................................1 6.2. Bảng TABLE(pck_report_chatbox.get_rev_data_by_precinct (TO_DATE(TO_CHAR(:date),                                                |                                                                                                                                                         |
| 'dd/mm/yyyy'), UPPER(:user_name)))......................................................................................................1               | 'dd/mm/yyyy'), UPPER(:user_name)))......................................................................................................1                                                                                      | 'dd/mm/yyyy'), UPPER(:user_name)))......................................................................................................1               |
| -                                                                                                                                                       | Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V_USER_PRECINCT_PERMISSION để lọc quyền nữa.........................................................................1                                       |                                                                                                                                                         |
| 7.                                                                                                                                                      | Quản lý công việc và dự án...................................................................................................................1                                                                                 | Quản lý công việc và dự án...................................................................................................................1          |
|                                                                                                                                                         | 7.1. Bảng                                                                                                                                                                                                                      | LOCATION_GROUP.........................................................................................................1                                |
|                                                                                                                                                         | 7.2. Bảng                                                                                                                                                                                                                      | PROJECT............................................................................................................................1                    |
|                                                                                                                                                         | 7.3. Bảng                                                                                                                                                                                                                      | LOCATION.........................................................................................................................1                      |
| 7.4.                                                                                                                                                    | Bảng V_MAN_TASK..................................................................................................................                                                                                              | 1                                                                                                                                                       |
|                                                                                                                                                         | 7.5. Bảng                                                                                                                                                                                                                      | V_MAN_TASK_PROGRESS............................................................................................1                                        |
| 7.6.                                                                                                                                                    | Bảng V_CAT_STAFF..................................................................................................................                                                                                             | 1                                                                                                                                                       |

## 1. Danh mục dùng chung

## 1.1. Bảng V\_USER\_PRECINCT\_PERMISSION

- Ý nghĩa của bảng: Lưu trữ quyền truy cập của user theo phường/xã (user được xem thông tin của các phường/xã nào)
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
- -Nếu user hỏi về các dữ liệu liên quan tới PTM, VLR, TKC, trạm, ... thì luôn luôn map với bảng này để chỉ trả về dữ liệu trong phạm vi quyền truy cập của user.
- -Dữ liệu tổng khoảng 10000 dòng.

| Tên cột       | Kiểu dữ liệu   | Mô tả                                                                                                                                                                                                                                                                             |
|---------------|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| USER_NAME     | VARCHAR2       | Mã user (ví dụ: HUY.NGUYEN)                                                                                                                                                                                                                                                       |
| USER_ID       | NUMBER         | Mã định danh user                                                                                                                                                                                                                                                                 |
| PRECINCT_CODE | VARCHAR2       | Mã phường/xã mà user được truy cập (ví dụ: VTAU)                                                                                                                                                                                                                                  |
| PRECINCT_NAME | VARCHAR2       | Tên phường/xã mà user được truy cập (ví dụ: Phường Vũng Tàu)                                                                                                                                                                                                                      |
| HUB_CODE      | VARCHAR2       | Hub quản lý (mã hub) của phường/xã mà user được truy cập (ví dụ: VT.1)                                                                                                                                                                                                            |
| BRANCH_CODE   | VARCHAR2       | Mã TTKD/chi nhánh của phường/xã mà user được truy cập (gồm Tên TTKD/chi nhánh (gồm 7 giá trị (tương ứng với 7 TTKD): HCM010000, HCM020000, HCM030000, HCM040000, HCM050000, HCM060000, HCM070000)                                                                                 |
| BRANCH_NAME   | VARCHAR2       | Tên TTKD/chi nhánh (gồm 7 giá trị (tương ứng với 7 TTKD): Trung Tâm Kinh Doanh Sài Gòn, Trung Tâm Kinh Doanh Gia Định, Trung Tâm Kinh Doanh Bến Thành, Trung Tâm Kinh Doanh Gò Vấp, Trung Tâm Kinh Doanh Thủ Đức, Trung Tâm Kinh Doanh Bình Dương, Trung Tâm Kinh Doanh Vũng Tàu) |

-----------------------------------------------------------------------------------------------------------

## 1.2. Bảng PRECINCT

- Ý nghĩa của bảng: Lưu trữ thông tin của của các phường/xã
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột CODE
- Ghi chú:
- -Thường truy xuất vào bảng này để lấy các thông tin thêm của phường/xã (phường/xã thuộc hub gì, TTKD gì, ...) nếu bảng gốc không có đủ thông tin.
- -Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

| Cột2        | Kiểu dữ liệu   | Mô tả         |
|-------------|----------------|---------------|
| ID          | NUMBER         | Khóa chính    |
| CODE        | VARCHAR2       | Mã phường xã  |
| NAME        | VARCHAR2       | Tên phường xã |
| BRANCH_NAME | VARCHAR2       | Tên TTKD      |
| HUB         | VARCHAR2       | Tên Hub       |
| BRANCH_CODE | VARCHAR2       | Mã TTKD       |

************************************************************************

## 2. Dữ liệu điểm bán

## 2.1. Bảng POINT\_OF\_SALE

- Ý nghĩa của bảng: Lưu trữ thông tin của các điểm bán
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột SALE\_CODE và PRECINCT\_CODE.
- Ghi chú:
- -Thường truy xuất vào bảng này để lấy các thông tin thêm của điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...) nếu bảng gốc không có đủ thông tin.
- -Dữ liệu tổng khoảng 2000 dòng (tương ứng với khoảng 2000 điểm bán).

| Tên cột          | Kiểu dữ liệu   | Mô tả                                                                                                                                                                                                                                                                             |
|------------------|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ID               | NUMBER         | Mã định danh điểm bán (ví dụ: 17)                                                                                                                                                                                                                                                 |
| ADDRESS          | VARCHAR2       | Địa chỉ điểm bán                                                                                                                                                                                                                                                                  |
| BRANCH_NAME      | VARCHAR2       | Tên TTKD/chi nhánh (gồm 7 giá trị (tương ứng với 7 TTKD): Trung Tâm Kinh Doanh Sài Gòn, Trung Tâm Kinh Doanh Gia Định, Trung Tâm Kinh Doanh Bến Thành, Trung Tâm Kinh Doanh Gò Vấp, Trung Tâm Kinh Doanh Thủ Đức, Trung Tâm Kinh Doanh Bình Dương, Trung Tâm Kinh Doanh Vũng Tàu) |
| EMP_NAME         | VARCHAR2       | Tên nhân viên phụ trách                                                                                                                                                                                                                                                           |
| HUB              | VARCHAR2       | Hub quản lý (mã hub) (ví dụ: VT.1)                                                                                                                                                                                                                                                |
| HUB_LEADER       | VARCHAR2       | Tên trưởng Hub                                                                                                                                                                                                                                                                    |
| LAT              | VARCHAR2       | Vĩ độ (ví dụ: 10.765590)                                                                                                                                                                                                                                                          |
| LON              | VARCHAR2       | Kinh độ (ví dụ: 106.662547)                                                                                                                                                                                                                                                       |
| NVBH_CODE        | VARCHAR2       | Mã nhân viên bán hàng                                                                                                                                                                                                                                                             |
| PARENT_SALE_CODE | VARCHAR2       | Mã nhân viên/quản lý cấp trên                                                                                                                                                                                                                                                     |
| PARENT_SALE_NAME | VARCHAR2       | Tên nhân viên/quản lý cấp trên                                                                                                                                                                                                                                                    |

| PHONE_NUMBER   | VARCHAR2   | Số điện thoại điểm bán                  |
|----------------|------------|-----------------------------------------|
| PRECINCT_NAME  | VARCHAR2   | Tên phường/xã (ví dụ: Phường Diên Hồng) |
| SALE_CODE      | VARCHAR2   | Mã điểm bán                             |
| SALE_NAME      | VARCHAR2   | Tên điểm bán (ví dụ: ĐBH Minh Quang)    |
| SALE_TYPE      | VARCHAR2   | Loại điểm bán (ví dụ: Loại 2)           |
| PRECINCT_CODE  | VARCHAR2   | Mã phường/xã (ví dụ: VTAU)              |

-----------------------------------------------------------------------------------------------------------

## 2.2. Bảng V\_BDS\_NEW\_SUB\_SALE\_POINT

- Ý nghĩa của bảng: Lưu trữ thông tin phát triển mới thuê bao của kênh điểm bán
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột SALE\_CODE.
- Ghi chú:
- -Truy xuất vào bảng này để lấy các thông tin về số lượng PTM TB của kênh điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...).
- -Dữ liệu tổng khoảng 2000 dòng (tương ứng với khoảng 2000 điểm bán).

| Tên cột           | Kiểu dữ liệu   | Mô tả                                                                  |
|-------------------|----------------|------------------------------------------------------------------------|
| SALE_CODE         | VARCHAR 2      | Mã điểm bán (ví dụ: HCM01DHON_0009)                                    |
| SUM_DATE          | VARCHAR 2      | Ngày tổng hợp dữ liệu (luôn luôn là ngày hiện tại) (ví dụ: 17/06/2026) |
| MC_QUANTITY_DAY   | NUMBER         | Số lượng thuê bao trả trước trong ngày hiện tại (ví dụ: 1)             |
| MF_QUANTITY_DAY   | NUMBER         | Số lượng thuê bao trả sau trong ngày hiện tại (ví dụ: 0)               |
| ALL_QUANTITY_DAY  | NUMBER         | Tổng số thuê bao trong ngày hiện tại (ví dụ: 1)                        |
| SUM_MONTH         | VARCHAR 2      | Tháng tổng hợp dữ liệu (luôn luôn là tháng hiện tại) (ví dụ: 06/2026)  |
| MC_QUANTITY_MONTH | NUMBER         | Số lượng thuê bao trả trước trong tháng hiện tại (ví dụ: 15)           |
| MF_QUANTITY_MONTH | NUMBER         | Số lượng thuê bao trả sau trong tháng hiện tại (ví dụ: 0)              |

| ALL_QUANTITY_MONTH     | NUMBER    | Tổng số thuê bao trong tháng hiện tại (ví dụ: 15)                                                 |
|------------------------|-----------|---------------------------------------------------------------------------------------------------|
| SUM_YEAR               | VARCHAR 2 | Năm tổng hợp dữ liệu (năm hiện tại) (ví dụ: 2026)                                                 |
| MC_QUANTITY_YEAR       | NUMBER    | Số lượng thuê bao trả trước trong năm hiện tại (ví dụ: 30)                                        |
| MF_QUANTITY_YEAR       | NUMBER    | Số lượng thuê bao trả sau trong năm hiện tại (ví dụ: 0)                                           |
| ALL_QUANTITY_YEAR      | NUMBER    | Tổng số thuê bao trong năm hiện tại (ví dụ: 30)                                                   |
| MC_QUANTITY_ALL_YEAR   | NUMBER    | Tổng số thuê bao trả trước trong tất cả các năm (trong toàn bộ lịch sử được ghi nhận) (ví dụ: 39) |
| MF_QUANTITY_ALL_YEAR   | NUMBER    | Lũy kế thuê bao trả sau trong tất cả các năm (trong toàn bộ lịch sử được ghi nhận) (ví dụ: 1)     |
| ALL_QUANTITY_ALL_YEAR  | NUMBER    | Tổng lũy kế thuê bao trong tất cả các năm (trong toàn bộ lịch sử được ghi nhận) (ví dụ: 40)       |
| START_DATE_LAST_WEEK   | VARCHAR 2 | Ngày bắt đầu tuần trước (lấy thứ 5 là ngày bắt đầu tuần) (ví dụ: 04/06/2026)                      |
| LAST_DATE_LAST_WEEK    | VARCHAR 2 | Ngày kết thúc tuần trước (lấy thứ 4 là ngày kết thúc tuần) (ví dụ: 10/06/2026)                    |
| MC_QUANTITY_LAST_WEEK  | NUMBER    | Số lượng thuê bao trả trước trong tuần trước (ví dụ: 2)                                           |
| MF_QUANTITY_LAST_WEEK  | NUMBER    | Số lượng thuê bao trả sau trong tuần trước (ví dụ: 0)                                             |
| ALL_QUANTITY_LAST_WEEK | NUMBER    | Tổng số thuê bao trong tuần trước (ví dụ: 2)                                                      |
| START_DATE_THIS_WEEK   | VARCHAR 2 | Ngày bắt đầu tuần hiện tại (lấy thứ 5 là ngày bắt đầu tuần) (ví dụ: 11/06/2026)                   |
| LAST_DATE_THIS_WEEK    | VARCHAR 2 | Ngày kết thúc tuần hiện tại (lấy thứ 4 là ngày kết thúc tuần) (ví dụ: 17/06/2026)                 |
| MC_QUANTITY_THIS_WEEK  | NUMBER    | Số lượng thuê bao trả trước trong tuần hiện tại (ví dụ: 8)                                        |

| MF_QUANTITY_THIS_WEEK          | NUMBER   | Số lượng thuê bao trả sau trong tuần hiện tại (ví dụ: 0)                                                                                                                                                     |
|--------------------------------|----------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ALL_QUANTITY_THIS_WEEK         | NUMBER   | Tổng số thuê bao trong tuần hiện tại (ví dụ: 8)                                                                                                                                                              |
| SALE_POINT_QUANTITY_LAST_W EEK | NUMBER   | Điểm bán này có phát triển thuê bao hay chưa, tính từ ngày đầu tháng hiện tại đến ngày bắt đầu tuần trước (START_DATE_LAST_WEE K). Giá trị: 0: chưa phát triển thuê bao nào, 1: đã có phát triển thuê bao    |
| SALE_POINT_QUANTITY_THIS_W EEK | NUMBER   | Điểm bán này có phát triển thuê bao hay chưa, tính từ ngày đầu tháng hiện tại đến ngày bắt đầu tuần hiện tại (START_DATE_THIS_WEE K). Giá trị: 0: chưa phát triển thuê bao nào, 1: đã có phát triển thuê bao |

-----------------------------------------------------------------------------------------------------------

## 2.3. Bảng NHAN\_VIEN\_CHAM\_SOC\_LONG

- Ý nghĩa của bảng: Lưu trữ lịch sử chăm sóc điểm bán của nhân viên chăm sóc
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột MA\_DIEM\_BAN và MA\_NHAN\_VIEN\_CHAM\_SOC.
- Ghi chú:
- -Thường truy xuất vào bảng này để lấy các thông tin thêm của điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...) nếu bảng gốc không có đủ thông tin.
- -Dữ liệu mới nhất là dữ liệu ngày N-1.
- -Dữ liệu tổng khoảng 30000 dòng.

| Tên cột             | Kiểu dữ liệu   | Mô tả                                               |
|---------------------|----------------|-----------------------------------------------------|
| INSERT_DATE         | DATE           | Ngày ghi nhận dữ liệu (ví dụ: 08/06/2026 14:30:12)  |
| NGAY_CHAM_SOC       | DATE           | Ngày chăm sóc điểm bán (ví dụ: 01/06/2026 00:00:00) |
| MA_DIEM_BAN         | VARCHAR2       | Mã điểm bán                                         |
| TEN_DIEM_BAN        | VARCHAR2       | Tên điểm bán (ví dụ: ĐBH Minh Quang)                |
| NGUOI_GIAO_KE_HOACH | VARCHAR2       | Người giao kế hoạch chăm sóc                        |

| NHAN_VIEN_CHAM_SOC    | VARCHAR2   | Họ tên nhân viên chăm sóc điểm bán   |
|-----------------------|------------|--------------------------------------|
| MA_NHAN_VIEN_CHAM_SOC | VARCHAR2   | Mã nhân viên chăm sóc điểm bán       |

-----------------------------------------------------------------------------------------------------------

## 2.4. Bảng EMPLOYEE\_SALES

- Ý nghĩa của bảng: Lưu trữ thông tin của các nhân viên chăm sóc
- Chi tiết các cột trong bảng:

| Tên cột     | Kiểu dữ liệu   | Mô tả                                      |
|-------------|----------------|--------------------------------------------|
| ID          | NUMBER         | Khóa chính, định danh duy nhất của bản ghi |
| BRANCH_NAME | VARCHAR2       | Tên trung tâm kinh doanh / chi nhánh       |
| EMP_CODE    | VARCHAR2       | Mã nhân viên                               |
| HUB         | VARCHAR2       | Tên Hub / khu vực quản lý                  |
| HUB_LEADER  | VARCHAR2       | Tên hoặc mã trưởng Hub                     |
| SALES_CODE  | VARCHAR2       | Mã Điểm Bán                                |
| SALES_NAME  | VARCHAR2       | Tên nhân viên bán hàng                     |

## ● Mối liên kết:

- -Liên kết với các bảng khác qua cột SALES\_CODE và SALES\_NAME.
- Ghi chú:
- -Thường truy xuất vào bảng này để lấy các thông tin thêm của điểm bán (phường/xã thuộc hub gì, TTKD gì, loại gì, ...) nếu bảng gốc không có đủ thông tin.
- -Dữ liệu mới nhất là dữ liệu ngày N-1.
- -Dữ liệu tổng khoảng 100 dòng (tương ứng với 100 nhân viên chăm sóc).

************************************************************************

## 3. Dữ liệu kinh doanh

- 3.1. Bảng V\_BDS\_NEW\_SUB\_SHOP
- Ý nghĩa của bảng: Lưu trữ thông tin phát triển mới thuê bao của kênh cửa hàng và đại lý
- Chi tiết các cột trong bảng:
- Mối liên kết:
5. -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
7. -Truy xuất vào bảng này để lấy số lượng PTM TB của kênh cửa hàng và đại lý.
8. -Chỉ được sử dụng SHOP\_TYPE in ('101', '201', '202'), các giá trị khác không được SELECT
9. -Dữ liệu tổng khoảng 600 dòng.

| Tên cột            | Kiểu dữ liệu   | Mô tả                                                                   |
|--------------------|----------------|-------------------------------------------------------------------------|
| SHOP_CODE          | VARCHAR2       | Mã cửa hàng                                                             |
| SHOP_TYPE          | VARCHAR2       | Loại cửa hàng (101: cửa hàng, 201: đại lý uỷ quyền, 202: đại lý chuyên) |
| NAME               | VARCHAR2       | Tên cửa hàng                                                            |
| ADDRESS            | VARCHAR2       | Địa chỉ cửa hàng                                                        |
| LATITUDE           | NUMBER         | Vĩ độ                                                                   |
| LONGITUDE          | NUMBER         | Kinh độ                                                                 |
| STATUS             | NUMBER         | Trạng thái cửa hàng                                                     |
| SUM_DATE           | VARCHAR2       | Ngày tổng hợp dữ liệu                                                   |
| ALL_QUANTITY_DAY   | NUMBER         | Tổng số thuê bao trong ngày                                             |
| MC_QUANTITY_DAY    | NUMBER         | Số lượng thuê bao trả trước trong ngày                                  |
| MF_QUANTITY_DAY    | NUMBER         | Số lượng thuê bao trả sau trong ngày                                    |
| SUM_MONTH          | VARCHAR2       | Tháng tổng hợp dữ liệu                                                  |
| ALL_QUANTITY_MONTH | NUMBER         | Tổng số thuê bao trong tháng                                            |
| MC_QUANTITY_MONTH  | NUMBER         | Số lượng thuê bao trả trước trong tháng                                 |
| MF_QUANTITY_MONTH  | NUMBER         | Số lượng thuê bao trả sau trong tháng                                   |
| BRANCH_CODE        | VARCHAR2       | Mã TTKD/chi nhánh                                                       |
| PRECINCT_CODE      | VARCHAR2       | Mã phường/xã                                                            |

-----------------------------------------------------------------------------------------------------------

## 3.2. Bảng TABLE(pck\_report\_chatbox.get\_new\_sub\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name)))

- Ý nghĩa của bảng: Lưu trữ thông tin phát triển mới thuê bao của các kênh kinh doanh (kênh cửa hàng, kênh chuỗi, kênh đại lý chuyên, kênh đại lý ủy quyền, kênh online, kênh quản lý, kênh Khách hàng cá nhân, kênh Khách hàng doanh nghiệp)
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
- -Truy xuất vào bảng này để lấy số lượng PTM TB của các kênh (kênh cửa hàng, kênh chuỗi, kênh đại lý chuyên, kênh đại lý ủy quyền, kênh online, kênh quản lý, kênh Khách hàng cá nhân, kênh Khách hàng doanh nghiệp), ngoại trừ kênh điểm bán.
- -Khi gọi, truyền biến date (ngày phát triển thuê bao (cột SUM\_DATE)) và user\_name (user gọi truy cập dữ liệu)
- -Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa.
- -Dữ liệu mới nhất là ngày N (ngày hiện tại)
- -Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

| Tên cột   | Mô tả   |
|-----------|---------|

| PRECINCT_CODE          | Mã phường/xã                                                           |
|------------------------|------------------------------------------------------------------------|
| PRECINCT_NAME          | Tên phường/xã                                                          |
| SUM_DATE               | Ngày báo cáo dữ liệu thuê bao phát triển mới                           |
| CUAHANG_DAY            | Số lượng thuê bao phát triển mới trong ngày qua kênh Cửa hàng          |
| CHUOI_DIA_PHUONG_DAY   | Số lượng thuê bao phát triển mới trong ngày qua kênh chuỗi địa phương  |
| DLC_DAY                | Số lượng thuê bao phát triển mới trong ngày qua kênh Đại lý chuyên     |
| DLUQ_DAY               | Số lượng thuê bao phát triển mới trong ngày qua kênh Đại lý ủy quyền   |
| ONL_DAY                | Số lượng thuê bao phát triển mới trong ngày qua kênh Online            |
| OTHERS_DAY             | Số lượng thuê bao phát triển mới trong ngày qua các kênh khác          |
| QUAN_LY_DAY            | Số lượng thuê bao phát triển mới trong ngày qua kênh Quản lý           |
| TKD_KHCN_DAY           | Số lượng thuê bao phát triển mới trong ngày qua kênh Tổ KD KHCN        |
| TKD_KHDN_DAY           | Số lượng thuê bao phát triển mới trong ngày qua kênh Tổ KD KHDN        |
| SUM_MONTH              | Tháng báo cáo dữ liệu thuê bao phát triển mới                          |
| CUAHANG_MONTH          | Số lượng thuê bao phát triển mới trong tháng qua kênh Cửa hàng         |
| CHUOI_DIA_PHUONG_MONTH | Số lượng thuê bao phát triển mới trong tháng qua kênh chuỗi địa phương |
| DLC_MONTH              | Số lượng thuê bao phát triển mới trong tháng qua kênh Đại lý chuyên    |
| DLUQ_MONTH             | Số lượng thuê bao phát triển mới trong tháng qua kênh Đại lý ủy quyền  |
| ONL_MONTH              | Số lượng thuê bao phát triển mới trong tháng qua kênh Online           |
| OTHERS_MONTH           | Số lượng thuê bao phát triển mới trong tháng qua các kênh khác         |
| QUAN_LY_MONTH          | Số lượng thuê bao phát triển mới trong tháng qua kênh Quản lý          |
| TKD_KHCN_MONTH         | Số lượng thuê bao phát triển mới trong tháng qua kênh Tổ KD KHCN       |
| TKD_KHDN_MONTH         | Số lượng thuê bao phát triển mới trong tháng qua kênh Tổ KD KHDN       |

************************************************************************

## 4. Vùng phủ địa lý

## 4.1. Bảng PUBLIC\_LOCATION

- Ý nghĩa của bảng: Lưu trữ thông tin các điểm dữ liệu địa lý hành chính dùng để hiển thị lên bản đồ số, bao gồm các Trung tâm hành chính, Trụ sở công an, Cảng biển, Bệnh viện, Cao đẳng, Trạm PCCC, Doanh Nghiệp, Đại học
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
- -Truy xuất vào bảng này để lấy số lượng PTM TB của kênh cửa hàng và đại lý.
- -Dữ liệu tổng khoảng 5000 dòng.

| Tên cột       | Kiểu dữ liệu   | Mô tả                                                                                                                                                          |
|---------------|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ID            | NUMBER         | Khoá chính                                                                                                                                                     |
| TYPE          | VARCHAR2       | Loại địa điểm, bao gồm các giá trị: 'TTHC', 'CA', 'CB', 'BV', 'CD', 'PCCC', 'DN', 'DH'                                                                         |
| TYPE_NAME     | VARCHAR2       | Tên loại địa điểm, bao gồm các giá trị: 'Trung tâm hành chính', 'Trụ sở công an', 'Cảng biển', 'Bệnh viện', 'Cao đẳng', 'Trạm PCCC', 'Doanh Nghiệp', 'Đại học' |
| NAME          | VARCHAR2       | Tên địa điểm                                                                                                                                                   |
| ADDRESS       | VARCHAR2       | Địa chỉ                                                                                                                                                        |
| LATITUDE      | NUMBER         | Vĩ độ                                                                                                                                                          |
| LONGITUDE     | NUMBER         | Kinh độ                                                                                                                                                        |
| STATUS        | NUMBER         | Trạng thái                                                                                                                                                     |
| BRAND_CODE    | VARCHAR2       | Mã TTKD/chi nhánh                                                                                                                                              |
| PRECINCT_CODE | VARCHAR2       | Mã phường/xã                                                                                                                                                   |

| PRECINCT_NAME   | VARCHAR2   | Tên phường/xã   |
|-----------------|------------|-----------------|
| HUB             | VARCHAR2   | Hub quản lý     |

************************************************************************

## 5. Vùng phủ kỹ thuật

## 5.1. Bảng V\_BDS\_SITE

- Ý nghĩa của bảng: Lưu trữ thông tin về cell/trạm BTS.
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
- -Truy xuất vào bảng này để thông tin về cell/trạm BTS và các dữ liệu VLR, CLTS của cell/trạm BTS.
- -Luôn thêm điều kiện STATUS = 1 khi truy xuất, vì chỉ cần quan tâm dữ liệu của các trạm/cell cùng hoạt động
- -Dữ liệu tổng khoảng 30000 dòng.

| Tên cột       | Kiểu dữ liệu   | Mô tả                                                       |
|---------------|----------------|-------------------------------------------------------------|
| CELL_SITE     | VARCHAR2       | Mã trạm BTS / Cell Site                                     |
| LATITUDE      | NUMBER         | Vĩ độ                                                       |
| LONGITUDE     | NUMBER         | Kinh độ                                                     |
| STATUS        | NUMBER         | Trạng thái trạm (1: đang hoạt động, 0: không hoạt động/OFF) |
| SUM_DATE      | VARCHAR2       | Ngày tổng hợp dữ liệu                                       |
| VLR_ALL_DAY   | NUMBER         | Tổng VLR trong ngày                                         |
| VLR_3G_DAY    | NUMBER         | VLR 3G trong ngày                                           |
| VLR_4G_DAY    | NUMBER         | VLR 4G trong ngày                                           |
| VLR_5G_DAY    | NUMBER         | VLR 5G trong ngày                                           |
| SUM_MONTH     | VARCHAR2       | Tháng tổng hợp dữ liệu                                      |
| VLR_ALL_MONTH | NUMBER         | Tổng VLR trong tháng                                        |
| VLR_2G_MONTH  | NUMBER         | VLR 2G trong tháng                                          |
| VLR_3G_MONTH  | NUMBER         | VLR 3G trong tháng                                          |
| VLR_4G_MONTH  | NUMBER         | VLR 4G trong tháng                                          |
| VLR_5G_MONTH  | NUMBER         | VLR 5G trong tháng                                          |
| CLTC_MONTH    | VARCHAR2       | Tháng ghi nhận chênh lệch thu chi                           |
| CLTC          | NUMBER         | Chỉ số chất lượng chênh lệch thu chi                        |
| BRANCH_CODE   | VARCHAR2       | Mã TTKD/chi nhánh                                           |
| PRECINCT_CODE | VARCHAR2       | Mã phường/xã                                                |

************************************************************************

## 6. Báo cáo doanh thu TKC và VLR

- 6.1. Bảng TABLE(pck\_report\_chatbox.get\_vlr\_data\_by\_precinct (TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name)))
- Ý nghĩa của bảng: Lưu trữ thông tin số lượng VLR.
- Chi tiết các cột trong bảng:
- Mối liên kết:
5. -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
7. -Truy xuất vào bảng này để lấy số lượng VLR.
8. -Khi gọi, truyền biến date (ngày phát triển thuê bao (cột SUM\_DATE)) và user\_name (user gọi truy cập dữ liệu)
9. -Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa.
10. -Dữ liệu mới nhất là ngày N-2.
11. -Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

| Tên cột                     | Mô tả                             |
|-----------------------------|-----------------------------------|
| PRECINCT_CODE               | Mã phường/xã                      |
| PRECINCT_NAME               | Tên phường/xã                     |
| SUM_DATE                    | Ngày báo cáo dữ liệu VLR          |
| MOBIFONE_VLR_QUANTITY_DAY   | Số lượng VLR MobiFone trong ngày  |
| SAYMEE_VLR_QUANTITY_DAY     | Số lượng VLR Saymee trong ngày    |
| SUM_MONTH                   | Tháng báo cáo dữ liệu VLR         |
| MOBIFONE_VLR_QUANTITY_MONTH | Số lượng VLR MobiFone trong tháng |
| SAYMEE_VLR_QUANTITY_MONTH   | Số lượng VLR Saymee trong tháng   |

-----------------------------------------------------------------------------------------------------------

- 6.2. Bảng TABLE(pck\_report\_chatbox.get\_rev\_data\_by\_precinct

(TO\_DATE(TO\_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user\_name)))

- Ý nghĩa của bảng: Lưu trữ thông tin doanh thu tài khoản chính.
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột PRECINCT\_CODE.
- Ghi chú:
- -Truy xuất vào bảng này để lấy doanh thu tài khoản chính.
- -Khi gọi, truyền biến date (ngày phát triển thuê bao (cột SUM\_DATE)) và user\_name (user gọi truy cập dữ liệu)
- -Bảng này đã có sẵn phân quyền. Nên không cần phải map lại với bảng V\_USER\_PRECINCT\_PERMISSION để lọc quyền nữa.
- -Dữ liệu mới nhất là ngày N-2.
- -Dữ liệu tổng có 168 dòng (tương ứng với 168 phường/xã).

| Tên cột                | Mô tả                              |
|------------------------|------------------------------------|
| PRECINCT_CODE          | Mã phường/xã                       |
| PRECINCT_NAME          | Tên phường/xã                      |
| SUM_DATE               | Ngày báo cáo doanh thu             |
| MOBIFONE_TKC_REV_DAY   | Doanh thu TKC MobiFone trong ngày  |
| SAYMEE_TKC_REV_DAY     | Doanh thu TKC Saymee trong ngày    |
| BHM_REV_DAY            | Doanh thu BHM trong ngày           |
| SUM_MONTH              | Tháng báo cáo doanh thu            |
| MOBIFONE_TKC_REV_MONTH | Doanh thu TKC MobiFone trong tháng |
| SAYMEE_TKC_REV_MONTH   | Doanh thu TKC Saymee trong tháng   |
| BHM_REV_MONTH          | Doanh thu BHM trong tháng          |

************************************************************************

## 7. Quản lý công việc và dự án

## 7.1. Bảng LOCATION\_GROUP

- Ý nghĩa của bảng: Lưu trữ thông tin nhóm địa điểm.
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột ID.
- Ghi chú:
- -Truy xuất vào bảng này để lấy thông tin nhóm địa điểm.
- -Dữ liệu tổng có 1 dòng (hiện chỉ có 1 nhóm địa điểm là Uỷ Ban Nhân Dân).

| Tên cột   | Kiểu dữ liệu   | Mô tả             |
|-----------|----------------|-------------------|
| ID        | NUMBER         | Khoá chính        |
| Name      | VARCHAR2       | Tên nhóm địa điểm |

-----------------------------------------------------------------------------------------------------------

## 7.2. Bảng PROJECT

- Ý nghĩa của bảng: Lưu trữ thông tin dự án.
- ●
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột ID và LOCATION\_GROUP\_ID.
- Ghi chú:
- -Truy xuất vào bảng này để lấy thông tin nhóm địa điểm.
- -Dữ liệu tổng có 1 dòng (hiện chỉ có 1 nhóm địa điểm là Triển khai hạ tầng CNTT 168 Xã).

| Tên cột           | Kiểu dữ liệu   | Mô tả                     |
|-------------------|----------------|---------------------------|
| ID                | NUMBER         | Khoá chính                |
| NAME              | VARCHAR2       | Tên dự án                 |
| LOCATION_GROUP_ID | NUMBER         | Mã nhóm địa điểm liên kết |

-----------------------------------------------------------------------------------------------------------

## 7.3. Bảng LOCATION

- Ý nghĩa của bảng: Lưu trữ thông tin địa điểm.
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột ID, LOCATION\_GROUP\_ID và PRECINCT\_NAME.
- Ghi chú:
- -Truy xuất vào bảng này để lấy thông tin địa điểm.
- -Dữ liệu tổng khoảng 300 dòng.

| Tên cột           | Kiểu dữ liệu   | Mô tả                 |
|-------------------|----------------|-----------------------|
| ID                | NUMBER         | Mã định danh địa điểm |
| ADDRESS           | VARCHAR2       | Địa chỉ địa điểm      |
| LAT               | NUMBER         | Vĩ độ                 |
| LON               | NUMBER         | Kinh độ               |
| NAME              | VARCHAR2       | Tên địa điểm          |
| LOCATION_GROUP_ID | NUMBER         | Mã nhóm địa điểm      |
| PROJECT_ID        | NUMBER         | Mã dự án              |
| PRECINCT_NAME     | VARCHAR2       | Tên phường/xã         |
| HUB               | VARCHAR2       | Hub quản lý           |
| BRANCH_NAME       | VARCHAR2       | Tên TTKD/chi nhánh    |

-----------------------------------------------------------------------------------------------------------

## 7.4. Bảng V\_MAN\_TASK

- Ý nghĩa của bảng: Lưu trữ thông tin các công việc được khai báo.
- ●
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột ID, PROGRESS\_ID , LOCATION\_ID, PROJECT\_ID, assigner\_staff\_id và assignee\_staff\_id.
- Ghi chú:
- -Truy xuất vào bảng này để lấy thông tin công việc.
- -Dữ liệu tổng khoảng 20000 dòng.

| Tên cột           | Kiểu dữ liệu   | Mô tả                   |
|-------------------|----------------|-------------------------|
| ID                | NUMBER         | Mã định danh công việc  |
| CREATED_DATE      | TIMESTAMP      | Thời gian tạo bản ghi   |
| END_DATE          | TIMESTAMP      | Ngày kết thúc công việc |
| NAME              | VARCHAR2       | Tên công việc           |
| PRIORITY          | VARCHAR2       | Mức độ ưu tiên          |
| START_DATE        | TIMESTAMP      | Ngày bắt đầu công việc  |
| PROGRESS_ID       | NUMBER         | Tiến độ thực hiện       |
| location_id       | NUMBER         | Mã địa điểm             |
| project_id        | NUMBER         | Mã dự án                |
| assigner_staff_id | NUMBER         | Mã Người giao           |
| assignee_staff_id | NUMBER         | Mã Người nhận           |

-----------------------------------------------------------------------------------------------------------

## 7.5. Bảng V\_MAN\_TASK\_PROGRESS

- Ý nghĩa của bảng: Lưu trữ thông tin tiến độ công việc.
- ●
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột ID, và TASK\_ID.
- Ghi chú:
- -Truy xuất vào bảng này để lấy thông tin tiến độ công việc.
- -Dữ liệu tổng khoảng 30000 dòng.

| Tên cột      | Kiểu dữ liệu   | Mô tả                          |
|--------------|----------------|--------------------------------|
| ID           | NUMBER         | Mã định danh tiến độ công việc |
| CREATED_DATE | TIMESTAMP      | Thời gian tạo bản ghi          |
| PERCENT      | NUMBER         | Phần trăm hoàn thành           |
| TASK_ID      | NUMBER         | Mã công việc                   |

-----------------------------------------------------------------------------------------------------------

## 7.6. Bảng V\_CAT\_STAFF

- Ý nghĩa của bảng: Lưu trữ thông tin nhân viên của công việc.
- Chi tiết các cột trong bảng:
- Mối liên kết:
- -Liên kết với các bảng khác qua cột ID.
- Ghi chú:
- -Truy xuất vào bảng này để lấy thông tin nhân viên của công việc.
- -Dữ liệu tổng khoảng 500 dòng.

| Tên cột   | Kiểu dữ liệu   | Mô tả                     |
|-----------|----------------|---------------------------|
| ID        | NUMBER         | Mã định danh người dùng   |
| FULL_NAME | VARCHAR2       | Họ và tên người dùng      |
| GENDER    | NUMBER         | Giới tính                 |
| ISDN      | VARCHAR2       | Số thuê bao/số điện thoại |

************************************************************************
