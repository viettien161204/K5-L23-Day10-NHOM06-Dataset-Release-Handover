# Bảo mật khi làm việc

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
Không được chép lô `lab250_65cd8821648c` (hoặc bản sửa `lab250_65cd8821648c_v2`) ra USB mang về nhà. Gửi qua email cá nhân hay nhờ người ngoài làm hộ cũng vi phạm bảo mật vì đưa dữ liệu nội bộ ra khỏi hạ tầng kiểm soát của tổ chức và làm lộ cho bên thứ ba không có quyền truy cập. Thay vào đó, phải dừng việc đúng giờ, bàn giao trạng thái công việc trên hệ thống nội bộ, hoặc xin phép làm thêm giờ tại máy công ty / qua kênh truy cập từ xa (VPN, VDI) được cấp phép chính thức.

## 2. Năm việc: được hay không
- **Mở job được giao trên máy công ty:** **Được**, vì đây là thiết bị và phạm vi công việc được cấp phép đúng vai trò.
- **Chụp màn hình gửi người quen:** **Không**, vì có thể làm lộ dữ liệu ảnh, thông tin định danh cá nhân hoặc quy trình nội bộ ra ngoài.
- **Chép lô ra USB:** **Không**, vì thiết bị lưu trữ cá nhân dễ thất lạc, nhiễm mã độc và không kiểm soát được bản sao.
- **Dán nhãn thật lên chatbot:** **Không**, vì dữ liệu dự án thật có thể bị lưu lại hoặc dùng để huấn luyện trên máy chủ bên thứ ba (chỉ ở bài lab này dùng ảnh COCO công khai mới được phép dán hỏi AI và phải ghi lại trong `prompts.md`).
- **Đưa tài khoản CVAT cho đồng nghiệp:** **Không**, vì vi phạm nguyên tắc tài khoản định danh cá nhân, làm sai lệch log truy vết (`annotator`/`reviewer` trong `jobs.csv`) và vượt quyền kiểm soát.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
- **Hành động & Trạng thái lô:** Đặt trạng thái lô là **Hold + báo người phụ trách** (quản lý dự án / phụ trách bảo mật dữ liệu).
- **Lý do không tự làm mờ hay xóa ảnh:** Tự ý chỉnh sửa hay xóa ảnh sẽ làm thay đổi file gốc, sai lệch `sha256` trong `manifest.csv` và `release_id`, phá vỡ tính toàn vẹn/truy vết của lô dữ liệu bàn giao; việc xử lý dữ liệu nhạy cảm (PII) phải thực hiện theo quy trình chính thức từ nguồn gốc và có phê duyệt.
- **Ví dụ trong lô `r1006` của nhóm:** Ảnh `000000006771` (cận cảnh rõ khuôn mặt người phụ nữ cầm điện thoại giữa đám đông) và ảnh `000000005001` (nhiều khuôn mặt người lớn và trẻ em nhìn rõ khi cắt băng khánh thành).
