# Mẫu câu hỏi và câu SQL tương ứng

## SQL_001

query: 5 điểm bán hàng có số lượng thuê bao phát triển mới nhiều nhất trong tháng.

evidence: Điểm bán hàng được biểu diễn bằng SALE_CODE trong bảng POINT_OF_SALE. Số lượng thuê bao phát triển mới trong tháng được biểu diễn bằng ALL_QUANTITY_MONTH trong bảng V_BDS_NEW_SUB_SALE_POINT. Hai bảng liên kết với nhau qua SALE_CODE. Dữ liệu chỉ được lấy trong phạm vi phường/xã user có quyền truy cập thông qua V_USER_PRECINCT_PERMISSION.PRECINCT_CODE.

sql:

```sql
SELECT *
 FROM (
  SELECT
  p.sale_code as sale_code,
  nvl(s.all_quantity_month, 0) as all_quantity_month
  FROM point_of_sale p
  LEFT JOIN v_bds_new_sub_sale_point s
  on upper(trim(p.sale_code)) = upper(trim(s.sale_code))
  and s.SUM_date = to_char(sysdate, 'dd/MM/yyyy')
  WHERE exists (
  SELECT c.precinct_code
  FROM v_user_precinct_permission c
  WHERE upper(c.user_name) = upper('USER_NAME_ABC')
  and c.precinct_code = p.precinct_code
  )
  ORDER BY nvl(s.all_quantity_month, 0) desc
 )
 WHERE rownum <= 5
```

## SQL_002

query: Điểm bán nào phát triển thuê bao trong tháng nhưng chưa được chăm sóc?

evidence: Điểm bán có phát triển thuê bao trong tháng được biểu diễn bằng ALL_QUANTITY_MONTH > 0 trong bảng V_BDS_NEW_SUB_SALE_POINT. Lịch sử chăm sóc điểm bán được biểu diễn bằng MA_DIEM_BAN và NGAY_CHAM_SOC trong bảng NHAN_VIEN_CHAM_SOC_LONG. Dữ liệu điểm bán phải nằm trong phạm vi quyền user qua V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  p.sale_code as sale_code,
  p.sale_name as sale_name,
  p.branch_name as branch_name,
  p.hub as hub,
  p.precinct_code as precinct_code,
  p.precinct_name as precinct_name,
  nvl(s.mc_quantity_month, 0) as mc_quantity_month,
  nvl(s.mf_quantity_month, 0) as mf_quantity_month,
  nvl(s.all_quantity_month, 0) as all_quantity_month,
  s.SUM_date as SUM_date,
  s.SUM_month as SUM_month
 FROM point_of_sale p
 JOIN v_bds_new_sub_sale_point s
  on upper(trim(p.sale_code)) = upper(trim(s.sale_code))
  and s.SUM_date = to_char(sysdate, 'dd/MM/yyyy')
 LEFT JOIN (
  SELECT distinct ma_diem_ban
  FROM nhan_vien_cham_soc_long
  WHERE ngay_cham_soc >=
  to_date(to_char(sysdate, 'dd/MM/yyyy'), 'dd/MM/yyyy') - 30
  and ngay_cham_soc <
  to_date(to_char(sysdate, 'dd/MM/yyyy'), 'dd/MM/yyyy') + 1
 ) k
  on upper(trim(k.ma_diem_ban)) = upper(trim(p.sale_code))
 WHERE nvl(s.all_quantity_month, 0) > 0
  and k.ma_diem_ban is null
  and exists (
  SELECT c.precinct_code
  FROM v_user_precinct_permission c
  WHERE upper(c.user_name) = upper('USER_NAME_ABC')
  and c.precinct_code = p.precinct_code
  )
 ORDER BY
  nvl(s.all_quantity_month, 0) desc,
  p.branch_name,
  p.hub,
  p.precinct_name,
  p.sale_name
```

## SQL_003

query: So sánh phát triển thuê bao giữa các trung tâm kinh doanh trong tháng?

evidence: Trung tâm kinh doanh được biểu diễn bằng BRANCH_NAME trong bảng POINT_OF_SALE. Số thuê bao trả trước, trả sau và tổng thuê bao trong tháng được biểu diễn lần lượt bằng MC_QUANTITY_MONTH, MF_QUANTITY_MONTH và ALL_QUANTITY_MONTH trong bảng V_BDS_NEW_SUB_SALE_POINT. Điểm bán có phát triển thuê bao trong tháng được biểu diễn bằng ALL_QUANTITY_MONTH > 0. Dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  rownum as stt,
  x.*
 FROM (
  SELECT
  p.branch_name as branch_name,
  count(distinct p.sale_code) as tong_so_diem_ban,
  count(
  distinct case
  WHEN nvl(s.all_quantity_month, 0) > 0
  then p.sale_code
  end
  ) as so_diem_ban_co_ptm_thang,
  count(
  distinct case
  WHEN nvl(s.all_quantity_month, 0) = 0
  then p.sale_code
  end
  ) as so_diem_ban_chua_ptm_thang,
  round(
  count(
  distinct case
  WHEN nvl(s.all_quantity_month, 0) > 0
  then p.sale_code
  end
  ) * 100
  / nullif(count(distinct p.sale_code), 0),
  2
  ) as ty_le_diem_ban_co_ptm_thang,
  SUM(nvl(s.mc_quantity_month, 0)) as mc_quantity_month,
  SUM(nvl(s.mf_quantity_month, 0)) as mf_quantity_month,
  SUM(nvl(s.all_quantity_month, 0)) as all_quantity_month
  FROM point_of_sale p
  LEFT JOIN v_bds_new_sub_sale_point s
  on upper(trim(p.sale_code)) = upper(trim(s.sale_code))
  and s.SUM_date = to_char(sysdate, 'dd/mm/yyyy')
  WHERE exists (
  SELECT c.precinct_code
  FROM v_user_precinct_permission c
  WHERE upper(c.user_name) = upper('USER_NAME_ABC')
  and c.precinct_code = p.precinct_code
  )
  GROUP BY p.branch_name
  ORDER BY
  SUM(nvl(s.all_quantity_month, 0)) desc,
  count(
  distinct case
  WHEN nvl(s.all_quantity_month, 0) > 0
  then p.sale_code
  end
  ) desc
 ) x
```

## SQL_004

query: Top 5 phường có số lượng phát triển thuê bao nhiều nhất trong ngày qua kênh cửa hàng/đại lý.

evidence: “Cửa hàng” được biểu diễn bằng SHOP_TYPE = '101', “Đại lý ủy quyền” bằng SHOP_TYPE = '201', “Đại lý chuyên” bằng SHOP_TYPE = '202' trong bảng V_BDS_NEW_SUB_SHOP. Số lượng thuê bao phát triển trong ngày được biểu diễn bằng ALL_QUANTITY_DAY. Phường/xã user được phép truy cập được biểu diễn bằng PRECINCT_CODE, PRECINCT_NAME trong bảng V_USER_PRECINCT_PERMISSION. Chỉ lấy dữ liệu V_BDS_NEW_SUB_SHOP có STATUS = 1.

sql:

```sql
SELECT *
 FROM (
  SELECT
  c.precinct_code,
  c.precinct_name,
  SUM(s.all_quantity_day) as tong_so_ttb
  FROM v_bds_new_sub_shop s
  INNER JOIN (
  SELECT distinct
  precinct_code,
  precinct_name
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
  ) c
  on c.precinct_code = s.precinct_code
  WHERE s.status = 1
  and s.shop_type in ('101', '201', '202')
  GROUP BY
  c.precinct_code,
  c.precinct_name
  ORDER BY tong_so_ttb desc nulls last
 )
 WHERE rownum <= 5
```

## SQL_005

query: Tỷ lệ cửa hàng/đại lý có phát triển thuê bao trong tháng so với tổng số cửa hàng/đại lý của từng trung tâm kinh doanh.

evidence: Cửa hàng/đại lý được biểu diễn bằng SHOP_TYPE IN ('101', '201', '202') trong bảng V_BDS_NEW_SUB_SHOP. Cửa hàng/đại lý có phát triển thuê bao trong tháng được biểu diễn bằng ALL_QUANTITY_MONTH > 0. Trung tâm kinh doanh được biểu diễn bằng BRANCH_NAME trong bảng V_USER_PRECINCT_PERMISSION. Chỉ lấy dữ liệu có STATUS = 1.

sql:

```sql
SELECT
  branch_name,
  tong_so_cua_hang,
  so_cua_hang_co_pttb,
  round(
  so_cua_hang_co_pttb * 100.0
  / nullif(tong_so_cua_hang, 0),
  2
  ) as ty_le_phat_trien
 FROM (
  SELECT
  c.branch_name,
  count(distinct s.shop_code) as tong_so_cua_hang,
  count(
  distinct case
  WHEN s.all_quantity_month > 0
  then s.shop_code
  end
  ) as so_cua_hang_co_pttb
  FROM v_bds_new_sub_shop s
  INNER JOIN (
  SELECT distinct
  precinct_code,
  branch_name
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
  ) c
  on c.precinct_code = s.precinct_code
  WHERE s.status = 1
  and s.shop_type in ('101', '201', '202')
  GROUP BY c.branch_name
 ) t
 WHERE branch_name is not null
 ORDER BY ty_le_phat_trien desc
```

## SQL_006

query: Phường/xã nào có tổng thuê bao phát triển mới cao nhất trong ngày 06/07/2026?

evidence: Phường/xã được biểu diễn bằng PRECINCT_NAME từ TABLE(pck_report_chatbox.get_new_sub_data_by_precinct(...)). Tổng thuê bao phát triển mới trong ngày được biểu diễn bằng tổng các cột CUAHANG_DAY, CHUOI_DIA_PHUONG_DAY, DLC_DAY, DLUQ_DAY, ONL_DAY, OTHERS_DAY, QUAN_LY_DAY, TKD_KHCN_DAY và TKD_KHDN_DAY.

sql:

```sql
SELECT *
 FROM (
  SELECT
  fact.precinct_name,
  (
  fact.cuahang_day
  + fact.chuoi_dia_phuong_day
  + fact.dlc_day
  + fact.dluq_day
  + fact.onl_day
  + fact.others_day
  + fact.quan_ly_day
  + fact.tkd_khcn_day
  + fact.tkd_khdn_day
  ) as tong_tb_moi
  FROM table(
  pck_report_chatbox.get_new_sub_data_by_precinct(
  to_date('06072026', 'ddmmyyyy'),
  upper('USER_NAME_ABC')
  )
  ) fact
  ORDER BY tong_tb_moi desc
 )
 WHERE rownum = 1
```

## SQL_007

query: Danh sách các Bệnh viện tại trung tâm kinh doanh Sài Gòn.

evidence: “Bệnh viện” được biểu diễn bằng TYPE_NAME chứa 'Bệnh viện' trong bảng PUBLIC_LOCATION. Trung tâm kinh doanh Sài Gòn được biểu diễn bằng BRANCH_NAME chứa 'Sài Gòn' trong bảng PRECINCT. PUBLIC_LOCATION liên kết với PRECINCT và V_USER_PRECINCT_PERMISSION qua PRECINCT_CODE. Chỉ lấy địa điểm có STATUS = 1.

sql:

```sql
SELECT
  loc.name,
  loc.address,
  loc.precinct_name
 FROM public_location loc
 JOIN precinct prec
  on prec.code = loc.precinct_code
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = loc.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE loc.status = 1
  and loc.type_name like '%Bệnh viện%'
  and prec.branch_name like '%Sài Gòn'
```

## SQL_008

query: Thống kê số lượng Bệnh viện và Trụ sở công an theo từng trung tâm kinh doanh.

evidence: “Bệnh viện” được biểu diễn bằng TYPE_NAME = 'Bệnh viện' và “Trụ sở công an” bằng TYPE_NAME = 'Trụ sở công an' trong bảng PUBLIC_LOCATION. Trung tâm kinh doanh được biểu diễn bằng BRANCH_NAME trong bảng PRECINCT. Các bảng liên kết qua PRECINCT_CODE và dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION. Chỉ lấy PUBLIC_LOCATION có STATUS = 1.

sql:

```sql
SELECT
  prec.branch_name,
  SUM(
  case
  WHEN loc.type_name = 'Bệnh viện' then 1
  else 0
  end
  ) as so_luong_benh_vien,
  SUM(
  case
  WHEN loc.type_name = 'Trụ sở công an' then 1
  else 0
  end
  ) as so_luong_cong_an
 FROM public_location loc
 JOIN precinct prec
  on prec.code = loc.precinct_code
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = loc.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE loc.status = 1
  and loc.type_name in ('Bệnh viện', 'Trụ sở công an')
 GROUP BY prec.branch_name
 ORDER BY prec.branch_name asc
```

## SQL_009

query: Top 3 Hub có nhiều Trung tâm hành chính nhất.

evidence: “Trung tâm hành chính” được biểu diễn bằng TYPE_NAME = 'Trung tâm hành chính' trong bảng PUBLIC_LOCATION. Hub được biểu diễn bằng HUB trong PUBLIC_LOCATION. Dữ liệu phải nằm trong phạm vi quyền user qua V_USER_PRECINCT_PERMISSION và chỉ lấy địa điểm có STATUS = 1.

sql:

```sql
SELECT *
 FROM (
  SELECT
  loc.hub,
  count(loc.id) as so_luong_tthc
  FROM public_location loc
  JOIN v_user_precinct_permission perm
  on perm.precinct_code = loc.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
  WHERE loc.status = 1
  and loc.type_name = 'Trung tâm hành chính'
  GROUP BY loc.hub
  ORDER BY so_luong_tthc desc
 )
 WHERE rownum <= 3
```

## SQL_010

query: Tổng số thuê bao VLR 4G và 5G đang hoạt động trong ngày của các trạm trung tâm kinh doanh Gò Vấp.

evidence: VLR 4G và 5G trong ngày được biểu diễn bằng VLR_4G_DAY và VLR_5G_DAY trong bảng V_BDS_SITE. Trạm đang hoạt động được biểu diễn bằng STATUS = 1. Trung tâm kinh doanh Gò Vấp được biểu diễn bằng BRANCH_NAME chứa 'Gò Vấp' trong bảng PRECINCT. Dữ liệu ngày mới nhất của nhóm VLR/trạm trong mẫu được lấy theo SUM_DATE = SYSDATE - 2 và phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  SUM(nvl(site.vlr_4g_day, 0)) as vlr_4g,
  SUM(nvl(site.vlr_5g_day, 0)) as vlr_5g
 FROM v_bds_site site
 JOIN precinct prec
  on prec.code = site.precinct_code
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = site.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE site.SUM_date = to_char(sysdate - 2, 'DD/MM/YYYY')
  and prec.branch_name like '%Gò Vấp'
  and site.status = 1
```

## SQL_011

query: Top 10 trạm BTS có tổng thuê bao VLR cao nhất trong tháng này.

evidence: Trạm BTS được biểu diễn bằng CELL_SITE trong bảng V_BDS_SITE. Tổng VLR trong tháng được biểu diễn bằng VLR_ALL_MONTH; tháng tổng hợp dữ liệu được biểu diễn bằng SUM_MONTH. Chỉ lấy trạm có STATUS = 1 và dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT *
 FROM (
  SELECT
  site.cell_site,
  site.vlr_all_month,
  site.branch_code
  FROM v_bds_site site
  JOIN v_user_precinct_permission perm
  on perm.precinct_code = site.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
  WHERE site.SUM_month = to_char(sysdate, 'MM/YYYY')
  and site.status = 1
  ORDER BY site.vlr_all_month desc
 )
 WHERE rownum <= 10
```

## SQL_012

query: Danh sách 5 phường có chỉ số chất lượng chênh lệch thu chi trung bình thấp nhất trong tháng.

evidence: Chỉ số chất lượng chênh lệch thu chi được biểu diễn bằng CLSQL_ trong bảng V_BDS_SITE. Phường/xã được biểu diễn bằng NAME trong bảng PRECINCT và liên kết qua PRECINCT_CODE. Tháng tổng hợp được biểu diễn bằng SUM_MONTH. Chỉ lấy trạm có STATUS = 1 và dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT *
 FROM (
  SELECT
  prec.name as ten_phuong,
  avg(site.clSQL_) as clSQL__trung_binh
  FROM v_bds_site site
  JOIN precinct prec
  on prec.code = site.precinct_code
  JOIN v_user_precinct_permission perm
  on perm.precinct_code = site.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
  WHERE site.SUM_month = to_char(sysdate, 'MM/YYYY')
  and site.status = 1
  GROUP BY prec.name
  ORDER BY clSQL__trung_binh asc
 )
 WHERE rownum <= 5
```

## SQL_013

query: Số lượng VLR MobiFone và Saymee theo từng phường/xã hôm nay

evidence: Phường/xã được biểu diễn bằng PRECINCT_NAME từ TABLE(pck_report_chatbox.get_vlr_data_by_precinct(...)). Số lượng VLR MobiFone và Saymee trong ngày được biểu diễn bằng MOBIFONE_VLR_QUANTITY_DAY và SAYMEE_VLR_QUANTITY_DAY. Dữ liệu VLR mới nhất là ngày N-2.

sql:

```sql
SELECT
  fact.precinct_name,
  fact.mobifone_vlr_quantity_day,
  fact.saymee_vlr_quantity_day
 FROM table(
  pck_report_chatbox.get_vlr_data_by_precinct(
  to_date(
  to_char(sysdate - 2, 'ddmmyyyy'),
  'ddmmyyyy'
  ),
  upper('USER_NAME_ABC')
  )
 ) fact
```

## SQL_014

query: Phường/xã nào có số lượng VLR MobiFone cao nhất trong ngày 06/07/2026?

evidence: Phường/xã được biểu diễn bằng PRECINCT_NAME từ TABLE(pck_report_chatbox.get_vlr_data_by_precinct(...)). Số lượng VLR MobiFone trong ngày được biểu diễn bằng MOBIFONE_VLR_QUANTITY_DAY.

sql:

```sql
SELECT *
 FROM (
  SELECT
  fact.precinct_name,
  fact.mobifone_vlr_quantity_day
  FROM table(
  pck_report_chatbox.get_vlr_data_by_precinct(
  to_date('06072026', 'ddmmyyyy'),
  upper('USER_NAME_ABC')
  )
  ) fact
  ORDER BY fact.mobifone_vlr_quantity_day desc
 )
 WHERE rownum = 1
```

## SQL_015

query: Phường/xã nào có doanh thu tài khoản chính MobiFone cao nhất trong tháng 07/2026?

evidence: Phường/xã được biểu diễn bằng PRECINCT_NAME từ TABLE(pck_report_chatbox.get_rev_data_by_precinct(...)). Doanh thu tài khoản chính MobiFone trong tháng được biểu diễn bằng MOBIFONE_TKC_REV_MONTH.

sql:

```sql
SELECT *
 FROM (
  SELECT
  fact.precinct_name,
  fact.mobifone_tkc_rev_month
  FROM table(
  pck_report_chatbox.get_rev_data_by_precinct(
  to_date('31072026', 'ddmmyyyy'),
  upper('USER_NAME_ABC')
  )
  ) fact
  ORDER BY fact.mobifone_tkc_rev_month desc
 )
 WHERE rownum = 1
```

## SQL_016

query: Có bao nhiêu công việc đã hoàn thành trong dự án Triển khai hạ tầng CNTT 168 Xã tại UBND Phường Bình Phú?

evidence: Dự án “Triển khai hạ tầng CNTT 168 Xã” được biểu diễn bằng NAME trong bảng PROJECT. Địa điểm “UBND Phường Bình Phú” được biểu diễn bằng NAME trong bảng LOCATION. Công việc được biểu diễn bằng ID trong bảng V_MAN_TASK. Công việc hoàn thành được biểu diễn bằng PERCENT = 100 trong bảng V_MAN_TASK_PROGRESS. Dữ liệu địa bàn phải giới hạn theo V_USER_PRECINCT_PERMISSION thông qua PRECINCT.

sql:

```sql
SELECT
  count(task.id) as so_cong_viec_hoan_thanh
 FROM v_man_task task
 INNER JOIN project proj
  on task.project_id = proj.id
 INNER JOIN location loc
  on task.location_id = loc.id
 INNER JOIN v_man_task_progress prog
  on task.id = prog.task_id
 INNER JOIN (
  SELECT distinct
  code,
  name,
  branch_name
  FROM precinct
 ) p
  on p.name = loc.precinct_name
  and p.branch_name = loc.branch_name
 INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
 ) perm
  on perm.precinct_code = p.code
 WHERE proj.name = 'Triển khai hạ tầng CNTT 168 Xã'
  and loc.name = 'UBND Phường Bình Phú'
  and prog.percent = 100
```

## SQL_017

query: Thống kê công việc của dự án Triển khai hạ tầng CNTT 168 Xã theo Hub: số lượng đã hoàn thành, chưa hoàn thành, và tổng.

evidence: Dự án được biểu diễn bằng NAME trong bảng PROJECT. Hub được biểu diễn bằng HUB trong bảng LOCATION. Công việc được biểu diễn bằng ID trong V_MAN_TASK. Hoàn thành được biểu diễn bằng PERCENT = 100; chưa hoàn thành bằng PERCENT < 100 hoặc NULL trong V_MAN_TASK_PROGRESS. Dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  loc.hub,
  SUM(
  case
  WHEN prog.percent = 100 then 1
  else 0
  end
  ) as so_cv_hoan_thanh,
  SUM(
  case
  WHEN prog.percent < 100
  or prog.percent is null then 1
  else 0
  end
  ) as so_cv_chua_hoan_thanh,
  count(task.id) as tong_so_cong_viec
 FROM v_man_task task
 INNER JOIN project proj
  on task.project_id = proj.id
 INNER JOIN location loc
  on task.location_id = loc.id
 LEFT JOIN v_man_task_progress prog
  on task.id = prog.task_id
 INNER JOIN (
  SELECT distinct
  code,
  name,
  branch_name
  FROM precinct
 ) p
  on p.name = loc.precinct_name
  and p.branch_name = loc.branch_name
 INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
 ) perm
  on perm.precinct_code = p.code
 WHERE proj.name = 'Triển khai hạ tầng CNTT 168 Xã'
 GROUP BY loc.hub
 ORDER BY tong_so_cong_viec desc
```

## SQL_018

query: Liệt kê các địa điểm thuộc Triển khai hạ tầng CNTT 168 Xã chưa có công việc hoàn thành?

evidence: Dự án “Triển khai hạ tầng CNTT 168 Xã” được biểu diễn bằng NAME trong bảng PROJECT. Địa điểm được biểu diễn bằng NAME trong bảng LOCATION. Công việc hoàn thành được biểu diễn bằng PERCENT = 100 trong bảng V_MAN_TASK_PROGRESS. “Chưa có công việc hoàn thành” được xác định khi không tồn tại công việc tại địa điểm đó có tiến độ PERCENT = 100. Dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT distinct
  loc.name as ten_dia_diem
 FROM location loc
 INNER JOIN project proj
  on loc.project_id = proj.id
 INNER JOIN (
  SELECT distinct
  code,
  name,
  branch_name
  FROM precinct
 ) p
  on p.name = loc.precinct_name
  and p.branch_name = loc.branch_name
 INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
 ) perm
  on perm.precinct_code = p.code
 WHERE proj.name = 'Triển khai hạ tầng CNTT 168 Xã'
  and not exists (
  SELECT 1
  FROM v_man_task t
  INNER JOIN v_man_task_progress tp
  on t.id = tp.task_id
  WHERE t.location_id = loc.id
  and tp.percent = 100
  )
```

## SQL_019

query: Top 5 phường có số lượng điểm bán hàng có phát triển thuê bao trong tuần nhiều nhất

evidence: Phường/xã được biểu diễn bằng PRECINCT_CODE, PRECINCT_NAME trong bảng POINT_OF_SALE. Điểm bán có phát triển thuê bao tính đến tuần hiện tại được biểu diễn bằng SALE_POINT_QUANTITY_THIS_WEEK trong bảng V_BDS_NEW_SUB_SALE_POINT, với 0 là chưa phát triển và 1 là đã phát triển. Hai bảng liên kết qua SALE_CODE. Dữ liệu phải nằm trong phạm vi quyền user thông qua V_USER_PRECINCT_PERMISSION.PRECINCT_CODE.

sql:

```sql
SELECT *
 FROM (
  SELECT
  p.precinct_code,
  p.precinct_name,
  SUM(nvl(s.sale_point_quantity_this_week, 0)) as total_sale_points
  FROM point_of_sale p
  JOIN v_bds_new_sub_sale_point s
  on upper(trim(p.sale_code)) = upper(trim(s.sale_code))
  and s.SUM_date = to_char(sysdate, 'DD/MM/YYYY')
  JOIN v_user_precinct_permission perm
  on perm.precinct_code = p.precinct_code
  WHERE perm.user_name = upper('USER_NAME_ABC')
  GROUP BY
  p.precinct_code,
  p.precinct_name
  HAVING SUM(nvl(s.sale_point_quantity_this_week, 0)) > 0
  ORDER BY total_sale_points desc
 )
 WHERE rownum <= 5
```

## SQL_020

query: Vũng tàu có bao nhiêu điểm bán có phát triển thuê bao hôm nay, và số lượng thuê bao là bao nhiêu?

evidence: Trung tâm kinh doanh Vũng Tàu được biểu diễn bằng BRANCH_NAME chứa 'Vũng Tàu' trong bảng POINT_OF_SALE. Điểm bán có phát triển thuê bao hôm nay được biểu diễn bằng ALL_QUANTITY_DAY > 0 trong bảng V_BDS_NEW_SUB_SALE_POINT. Số thuê bao phát triển hôm nay được biểu diễn bằng ALL_QUANTITY_DAY. Dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  count(distinct p.sale_code) as so_luong_diem_ban,
  SUM(nvl(s.all_quantity_day, 0)) as tong_so_luong_thue_bao
 FROM point_of_sale p
 JOIN v_bds_new_sub_sale_point s
  on upper(trim(p.sale_code)) = upper(trim(s.sale_code))
  and s.SUM_date = to_char(sysdate, 'DD/MM/YYYY')
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = p.precinct_code
 WHERE p.branch_name like '%Vũng Tàu'
  and perm.user_name = upper('USER_NAME_ABC')
  and nvl(s.all_quantity_day, 0) > 0
```

## SQL_021

query: Danh sách điểm bán đã được chăm sóc hôm qua nhưng chưa phát triển thuê bao trong tháng.

sql:

```sql
SELECT distinct
  p.sale_code,
  p.sale_name,
  p.branch_name,
  p.hub,
  p.precinct_name,
  cs.nhan_vien_cham_soc
 FROM point_of_sale p
 JOIN nhan_vien_cham_soc_long cs
  on upper(trim(cs.ma_diem_ban)) = upper(trim(p.sale_code))
 left JOIN v_bds_new_sub_sale_point s
  on upper(trim(s.sale_code)) = upper(trim(p.sale_code))
  and s.SUM_date = to_char(sysdate, 'DD/MM/YYYY')
 WHERE trunc(cs.ngay_cham_soc) = trunc(sysdate - 1)
  and nvl(s.all_quantity_month, 0) = 0
  and exists (
  SELECT 1
  FROM v_user_precinct_permission perm
  WHERE upper(perm.user_name) = upper('USER_NAME_ABC')
  and perm.precinct_code = p.precinct_code
  )
 ORDER BY
  p.branch_name,
  p.hub,
  p.sale_name
```

## SQL_022

query: Thống kê tổng số lượng phát triển thuê bao trong tháng, phân loại theo nhóm Cửa hàng và Đại lý.

evidence: “Cửa hàng” được biểu diễn bằng SHOP_TYPE = '101'; “Đại lý” được biểu diễn bằng SHOP_TYPE IN ('201', '202') trong bảng V_BDS_NEW_SUB_SHOP. Tổng thuê bao trong tháng được biểu diễn bằng ALL_QUANTITY_MONTH, thuê bao trả trước bằng MC_QUANTITY_MONTH và thuê bao trả sau bằng MF_QUANTITY_MONTH. Chỉ sử dụng SHOP_TYPE IN ('101', '201', '202'), lấy STATUS = 1 và giới hạn quyền qua V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  case
  WHEN s.shop_type = '101' then 'Cửa hàng'
  WHEN s.shop_type in ('201', '202') then 'Đại lý'
  end as loai_hinh,
  SUM(s.all_quantity_month) as tong_thue_bao,
  SUM(s.mc_quantity_month) as thue_bao_tra_truoc,
  SUM(s.mf_quantity_month) as thue_bao_tra_sau
 FROM v_bds_new_sub_shop s
 INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
 ) c
  on c.precinct_code = s.precinct_code
 WHERE s.status = 1
  and s.shop_type in ('101', '201', '202')
 GROUP BY
  case
  WHEN s.shop_type = '101' then 'Cửa hàng'
  WHEN s.shop_type in ('201', '202') then 'Đại lý'
  end
 ORDER BY tong_thue_bao desc
```

## SQL_023

query: Số lượng đại lý chuyên chưa phát triển được thuê bao nào trong tháng này.

evidence: “Đại lý chuyên” được biểu diễn bằng SHOP_TYPE = '202' trong bảng V_BDS_NEW_SUB_SHOP. Chưa phát triển thuê bao trong tháng được biểu diễn bằng ALL_QUANTITY_MONTH = 0 hoặc ALL_QUANTITY_MONTH IS NULL. Chỉ lấy dữ liệu có STATUS = 1 và trong phạm vi quyền user qua V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  count(distinct s.shop_code) as so_dai_ly_chua_co_pttb
 FROM v_bds_new_sub_shop s
 INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
 ) c
  on c.precinct_code = s.precinct_code
 WHERE (
  s.all_quantity_month = 0
  or s.all_quantity_month is null
  )
  and s.status = 1
  and s.shop_type = '202'
```

## SQL_024

query: Kênh bán hàng nào phát triển thuê bao nhiều nhất trong tháng 07/2026?

evidence: Sản lượng phát triển thuê bao theo từng kênh trong tháng được biểu diễn bằng CUAHANG_MONTH, CHUOI_DIA_PHUONG_MONTH, DLC_MONTH, DLUQ_MONTH, ONL_MONTH, QUAN_LY_MONTH, TKD_KHCN_MONTH, TKD_KHDN_MONTH và OTHERS_MONTH từ TABLE(pck_report_chatbox.get_new_sub_data_by_precinct(...)). Tháng báo cáo được biểu diễn bằng SUM_MONTH.

sql:

```sql
SELECT *
 FROM (
  SELECT
  kenh,
  tong_thue_bao
  FROM (
  SELECT
  SUM(fact.cuahang_month) as ch,
  SUM(fact.chuoi_dia_phuong_month) as cdp,
  SUM(fact.dlc_month) as dlc,
  SUM(fact.dluq_month) as dluq,
  SUM(fact.onl_month) as onl,
  SUM(fact.quan_ly_month) as ql,
  SUM(fact.tkd_khcn_month) as khcn,
  SUM(fact.tkd_khdn_month) as khdn,
  SUM(fact.others_month) as oth
  FROM table(
  pck_report_chatbox.get_new_sub_data_by_precinct(
  to_date('01072026', 'ddmmyyyy'),
  upper('USER_NAME_ABC')
  )
  ) fact
  WHERE fact.SUM_month = '07/2026'
  )
  unpivot (
  tong_thue_bao for kenh in (
  ch as 'Cửa hàng',
  cdp as 'Chuỗi địa phương',
  dlc as 'Đại lý chuyên',
  dluq as 'Đại lý ủy quyền',
  onl as 'Online',
  ql as 'Quản lý',
  khcn as 'Tổ KD KHCN',
  khdn as 'Tổ KD KHDN',
  oth as 'Khác'
  )
  )
  ORDER BY tong_thue_bao desc
 )
 WHERE rownum = 1
```

## SQL_025

query: Phường/xã nào có đồng thời Bệnh viện và Trụ sở công an?

evidence: “Bệnh viện” được biểu diễn bằng TYPE_NAME = 'Bệnh viện' và “Trụ sở công an” bằng TYPE_NAME = 'Trụ sở công an' trong bảng PUBLIC_LOCATION. Phường/xã được biểu diễn bằng PRECINCT_CODE, PRECINCT_NAME. Các địa điểm chỉ lấy với STATUS = 1 và phải nằm trong phạm vi quyền user qua V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  loc.precinct_code,
  loc.precinct_name,
  SUM(
  case
  WHEN loc.type_name = 'Bệnh viện' then 1
  else 0
  end
  ) as so_luong_benh_vien,
  SUM(
  case
  WHEN loc.type_name = 'Trụ sở công an' then 1
  else 0
  end
  ) as so_luong_cong_an
 FROM public_location loc
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = loc.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE loc.status = 1
  and loc.type_name in ('Bệnh viện', 'Trụ sở công an')
 GROUP BY
  loc.precinct_code,
  loc.precinct_name
 HAVING SUM(
  case
  WHEN loc.type_name = 'Bệnh viện' then 1
  else 0
  end
  ) > 0
  and SUM(
  case
  WHEN loc.type_name = 'Trụ sở công an' then 1
  else 0
  end
  ) > 0
 ORDER BY loc.precinct_name
```

## SQL_026

query: Trung tâm kinh doanh nào không có Bệnh viện?

evidence: “Bệnh viện” được biểu diễn bằng TYPE_NAME = 'Bệnh viện' trong bảng PUBLIC_LOCATION. Trung tâm kinh doanh user được phép truy cập được biểu diễn bằng BRANCH_NAME trong bảng V_USER_PRECINCT_PERMISSION. Một trung tâm kinh doanh không có Bệnh viện khi trong các phường/xã thuộc phạm vi quyền của trung tâm đó không tồn tại PUBLIC_LOCATION có STATUS = 1 và TYPE_NAME = 'Bệnh viện'.

sql:

```sql
SELECT distinct
  perm.branch_name
 FROM v_user_precinct_permission perm
 WHERE upper(perm.user_name) = upper('USER_NAME_ABC')
  and perm.branch_name is not null
  and not exists (
  SELECT 1
  FROM public_location loc
  JOIN v_user_precinct_permission p2
  on p2.precinct_code = loc.precinct_code
  and upper(p2.user_name) = upper('USER_NAME_ABC')
  WHERE loc.status = 1
  and loc.type_name = 'Bệnh viện'
  and p2.branch_name = perm.branch_name
  )
 ORDER BY perm.branch_name
```

## SQL_027

query: Có bao nhiêu trạm đang ở trạng thái ngưng hoạt động?

evidence: Trạm BTS được biểu diễn bằng CELL_SITE trong bảng V_BDS_SITE. Trạng thái “ngưng hoạt động” được biểu diễn bằng STATUS = 0. Đây là trường hợp ngoại lệ so với rule truy xuất trạm hoạt động thường dùng STATUS = 1. Dữ liệu phải giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  count(site.cell_site) as so_luong_tram_off
 FROM v_bds_site site
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = site.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE site.status = 0
```

## SQL_028

query: Tại trung tâm kinh doanh Gò Vấp, có bao nhiêu trạm BTS có phát sinh thuê bao 3G trong ngày?

evidence: Trạm BTS được biểu diễn bằng CELL_SITE trong bảng V_BDS_SITE. Phát sinh VLR 3G trong ngày được biểu diễn bằng VLR_3G_DAY > 0. Trung tâm kinh doanh Gò Vấp được biểu diễn bằng BRANCH_NAME chứa 'Gò Vấp' trong bảng PRECINCT. Dữ liệu ngày được lấy theo SUM_DATE = ngày N-2, chỉ lấy STATUS = 1 và giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  count(site.cell_site) as so_tram_co_3g
 FROM v_bds_site site
 JOIN precinct prec
  on prec.code = site.precinct_code
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = site.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE site.SUM_date = to_char(sysdate - 2, 'DD/MM/YYYY')
  and prec.branch_name like '%Gò Vấp'
  and site.status = 1
  and nvl(site.vlr_3g_day, 0) > 0
```

## SQL_029

query: Danh sách các trạm BTS đang hoạt động nhưng không phát sinh VLR 4G và 5G trong ngày.

evidence: Trạm BTS được biểu diễn bằng CELL_SITE trong bảng V_BDS_SITE. Trạm đang hoạt động được biểu diễn bằng STATUS = 1. Không phát sinh VLR 4G và 5G trong ngày được biểu diễn bằng VLR_4G_DAY và VLR_5G_DAY bằng 0 hoặc NULL. Dữ liệu ngày được lấy theo SUM_DATE = ngày N-2, giới hạn theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT
  site.cell_site,
  site.precinct_code,
  site.vlr_4g_day,
  site.vlr_5g_day
 FROM v_bds_site site
 JOIN v_user_precinct_permission perm
  on perm.precinct_code = site.precinct_code
  and perm.user_name = upper('USER_NAME_ABC')
 WHERE site.SUM_date = to_char(sysdate - 2, 'DD/MM/YYYY')
  and site.status = 1
  and nvl(site.vlr_4g_day, 0) = 0
  and nvl(site.vlr_5g_day, 0) = 0
 ORDER BY site.cell_site
```

## SQL_030

query: Tổng doanh thu tài khoản chính theo ngày của từng phường/xã hôm nay

evidence: Phường/xã được biểu diễn bằng PRECINCT_NAME từ TABLE(pck_report_chatbox.get_rev_data_by_precinct(...)). Tổng doanh thu tài khoản chính theo ngày được biểu diễn bằng tổng MOBIFONE_TKC_REV_DAY, SAYMEE_TKC_REV_DAY và BHM_REV_DAY. Dữ liệu mới nhất là ngày N-2.

sql:

```sql
SELECT
  fact.precinct_name,
  (
  fact.mobifone_tkc_rev_day
  + fact.saymee_tkc_rev_day
  + fact.bhm_rev_day
  ) as tong_doanh_thu
 FROM table(
  pck_report_chatbox.get_rev_data_by_precinct(
  to_date(
  to_char(sysdate - 2, 'ddmmyyyy'),
  'ddmmyyyy'
  ),
  upper('USER_NAME_ABC')
  )
 ) fact
```

## SQL_031

query: Phường/xã nào có số lượng VLR Saymee trong tháng lớn hơn VLR MobiFone trong tháng?

evidence: Phường/xã được biểu diễn bằng PRECINCT_NAME từ TABLE(pck_report_chatbox.get_vlr_data_by_precinct(...)). VLR Saymee và MobiFone trong tháng được biểu diễn bằng SAYMEE_VLR_QUANTITY_MONTH và MOBIFONE_VLR_QUANTITY_MONTH. Dữ liệu mới nhất của function VLR là ngày N-2

sql:

```sql
SELECT
  fact.precinct_name,
  fact.saymee_vlr_quantity_month,
  fact.mobifone_vlr_quantity_month
 FROM table(
  pck_report_chatbox.get_vlr_data_by_precinct(
  to_date(
  to_char(sysdate - 2, 'ddmmyyyy'),
  'ddmmyyyy'
  ),
  upper('USER_NAME_ABC')
  )
 ) fact
 WHERE nvl(fact.saymee_vlr_quantity_month, 0)
  > nvl(fact.mobifone_vlr_quantity_month, 0)
 ORDER BY fact.precinct_name
```

## SQL_032

query: Công việc mới nhất của dự án Triển khai hạ tầng CNTT 168 Xã của UBND Xã Nhuận Đức là gì?

evidence: Dự án “Triển khai hạ tầng CNTT 168 Xã” được biểu diễn bằng NAME trong bảng PROJECT. Địa điểm “UBND Xã Nhuận Đức” được biểu diễn bằng NAME trong bảng LOCATION. Công việc được biểu diễn bằng NAME và thời điểm bắt đầu bằng START_DATE trong bảng V_MAN_TASK. LOCATION liên kết với PRECINCT bằng PRECINCT_NAME và BRANCH_NAME để giới hạn dữ liệu theo V_USER_PRECINCT_PERMISSION.

sql:

```sql
SELECT *
 FROM (
  SELECT
  task.name as ten_cong_viec,
  task.start_date
  FROM v_man_task task
  INNER JOIN project proj
  on task.project_id = proj.id
  INNER JOIN location loc
  on task.location_id = loc.id
  INNER JOIN (
  SELECT distinct
  code,
  name,
  branch_name
  FROM precinct
  ) p
  on p.name = loc.precinct_name
  and p.branch_name = loc.branch_name
  INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
  ) perm
  on perm.precinct_code = p.code
  WHERE proj.name = 'Triển khai hạ tầng CNTT 168 Xã'
  and loc.name = 'UBND Xã Nhuận Đức'
  ORDER BY task.start_date desc
 )
 WHERE rownum <= 1
```

## SQL_033

query: Thống kê tỉ lệ hoàn thành công việc của từng trung tâm kinh doanh (dự án Triển khai hạ tầng CNTT 168 Xã)

evidence: Dự án được biểu diễn bằng NAME trong bảng PROJECT. Trung tâm kinh doanh được biểu diễn bằng BRANCH_NAME trong bảng LOCATION. Công việc hoàn thành được biểu diễn bằng PERCENT = 100 trong bảng V_MAN_TASK_PROGRESS. Tỷ lệ hoàn thành là số công việc có PERCENT = 100 trên tổng số công việc. Dữ liệu địa bàn phải giới hạn theo V_USER_PRECINCT_PERMISSION thông qua PRECINCT.

sql:

```sql
SELECT
  loc.branch_name,
  round(
  SUM(
  case
  WHEN prog.percent = 100 then 1
  else 0
  end
  ) * 100
  / count(task.id),
  2
  ) as ti_le_hoan_thanh_pt
 FROM v_man_task task
 INNER JOIN project proj
  on task.project_id = proj.id
 INNER JOIN location loc
  on task.location_id = loc.id
 left JOIN v_man_task_progress prog
  on task.id = prog.task_id
 INNER JOIN (
  SELECT distinct
  code,
  name,
  branch_name
  FROM precinct
 ) p
  on p.name = loc.precinct_name
  and p.branch_name = loc.branch_name
 INNER JOIN (
  SELECT distinct precinct_code
  FROM v_user_precinct_permission
  WHERE upper(user_name) = upper('USER_NAME_ABC')
 ) perm
  on perm.precinct_code = p.code
 WHERE proj.name = 'Triển khai hạ tầng CNTT 168 Xã'
 GROUP BY loc.branch_name
 ORDER BY ti_le_hoan_thanh_pt desc
```
