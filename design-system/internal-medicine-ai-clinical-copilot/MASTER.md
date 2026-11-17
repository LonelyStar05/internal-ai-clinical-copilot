# Design system — Internal Medicine AI Clinical Copilot (v2)

Bản v1 (nền cyan, sidebar xanh đậm) được lưu ở `_backup_ui_v1/`. Tệp này mô tả giao diện đang dùng trong `app/globals.css`.

## Nguyên tắc

1. **Văn bản lâm sàng là trung tâm.** Tóm tắt và bệnh án hiển thị như một tài liệu để đọc, không chia thành nhiều thẻ.
2. **Màu chỉ mang ý nghĩa lâm sàng.** Đỏ = cờ đỏ / ngoài ngưỡng, hổ phách = cần xem lại / bản nháp, xanh lá = đã duyệt. Phần còn lại trung tính.
3. **Mỗi dòng truy được nguồn.** Chip nguồn: xám = bản ghi hồ sơ, xanh dương = lượt nói (L1, L2…). Bấm chip mở panel "Nguồn" bên phải.
4. **Không dùng nhãn nội bộ trên UI** (SC-xx, UC-xx, "Module 1/2", "Pipeline"). Chỉ dùng từ bác sĩ hiểu.
5. **Một hành động chính mỗi màn hình** (Xác nhận tóm tắt, Ký duyệt, Chạy đánh giá).

## Token

| Vai trò | Giá trị |
|---|---|
| Nền | `#f6f5f1` |
| Bề mặt | `#ffffff` |
| Sidebar | `#efede7` |
| Viền | `#e4e1d9` / `#cfcbc0` |
| Chữ | `#1d1c19` / `#55524a` / `#85817a` |
| Nhấn | `#1f4d3f` |
| Đỏ | `#b3261e` trên `#fbeceb` |
| Hổ phách | `#8a5a00` trên `#fbf1d9` |
| Lượt nói | `#2b4c7e` trên `#e9eff8` |

Font: Be Vietnam Pro 400/500/600 (tự host qua `@fontsource/be-vietnam-pro`), cỡ nền 14px, văn bản lâm sàng 14.5px. Mã (mã BN, mã nguồn) dùng monospace hệ thống. Bo góc 6–8px, không đổ bóng trừ dialog và toast.

## Bố cục

- Sidebar 232px: tên sản phẩm, "Người bệnh", danh sách đang điều trị, người dùng.
- Hồ sơ: tiêu đề người bệnh + 3 tab (Tóm tắt hồ sơ, Bệnh án nháp, Transcript); cột tài liệu + panel rà soát 360px (Cảnh báo, Nguồn, Mã ICD-10).
- Dưới 1180px panel rà soát chuyển lên trên; dưới 820px sidebar thành thanh ngang.

## Tham khảo (Mobbin)

Heidi (ghi chú lâm sàng + panel mã ICD), Dropbox Dash và Gemini Notebook (chip trích nguồn), Fireflies/Grain (transcript), Customer.io và Klaviyo (audit log), Descript (đăng nhập).
