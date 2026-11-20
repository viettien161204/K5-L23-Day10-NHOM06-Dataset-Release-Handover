# Báo cáo nhóm NHOM06

## 1. Số liệu luyện tập
- F1 trên seed 1006: lỗi luật 1.0, lỗi gán nhãn 0.6, tổng 0.8 (truy vết: tier_a 1.0, tier_b 1.0, notify 1.0).
- Lô sạch (seed 5, --no-faults, 50 ảnh calib): 0 lỗi luật, 2 ứng viên trên 2 ảnh.
- Hàng đợi trên seed 1006: validator sinh ra 27 ứng viên trên 18 ảnh; nhóm mở ảnh xem và ghi 24 dòng vào review_log.csv (8 confirmed, 16 rejected), chốt 20 lỗi gồm 12 lỗi luật và 8 lỗi gán nhãn.
- Ngưỡng đã chọn và cách chọn: nhóm đối chiếu theo pixel của mask panoptic kết hợp với IoU giữa bbox detection và segment (bỏ qua segment iscrowd và lọc các vật quá nhỏ dưới 400-800 px hoặc dưới 0.4% diện tích ảnh). Với swap yêu cầu độ phủ pixel >= 0.55 và IoU >= 0.45; với instance_merge yêu cầu một segment phủ từ 2 box cùng lớp trở lên với tỉ lệ pixel >= 0.15 và độ phủ box >= 0.35. Các ngưỡng này được thử trên lô sạch (ra 2 ứng viên/50 ảnh) trước khi áp dụng cho seed 1006 để hàng đợi đủ nhỏ, xem hết được bằng mắt.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Trong 24 dòng ứng viên được xem ở seed 1006, chỉ có 8 trường hợp thực sự là lỗi (confirmed), còn lại 16 trường hợp là lệch tự nhiên của COCO (vật che khuất, xếp chồng hoặc khác cách chia instance giữa hai nguồn). Nếu không xem ảnh mà báo hết toàn bộ ứng viên vào errors.json thì sẽ phát sinh 16 báo thừa (FP), làm precision tụt mạnh (8 / 24 ≈ 0.33), kéo F1 lỗi gán nhãn và F1 tổng xuống thấp hơn nhiều so với mức 0.6 và 0.8 hiện tại.

## 3. Quyết định và lineage
- QC v1: 20/250 = 8.0%, vượt ngưỡng 2.0% nên kết luận của lô v1 (lab250_ac88b506410e) là HOLD, không được đưa thẳng vào train.
- Nhóm giữ lại 240 ảnh sạch nhãn detection (sửa tại chỗ scene_leak, wrong_hash, guideline_mismatch; giữ nguyên các ảnh chỉ lỗi panoptic và ghi chú báo team panoptic) để đóng gói lô v2 (lab250_ac88b506410e_v2) có parent là v1, đồng thời tách 10 ảnh lỗi detection vào rework_queue.csv.
- Run R-021 đã train trên lô v1 nên khi kiểm tra impact vẫn báo affected=True (review_or_retrain). Việc phát hành v2 chỉ sửa bộ dữ liệu bàn giao chứ không tự cập nhật trọng số của model đã học từ v1, nên R-021 bắt buộc phải được đánh giá lại hoặc train lại trên dữ liệu sạch.

## 4. Hash chứng minh gì, không chứng minh gì?
- sha256 chứng minh tính toàn vẹn của file: file ảnh và nhãn nhận được khớp hoàn toàn từng byte với lúc đóng gói manifest, không bị sửa lén, hỏng file hay thất lạc.
- sha256 không chứng minh nội dung nhãn đúng hay sai. Một file nhãn bị gán nhầm lớp hoặc lệch box từ đầu vẫn cho ra mã sha256 hợp lệ nếu không bị thay đổi sau khi tạo manifest.

## 5. Truy vết
- Tầng a (tier_a): các ảnh nằm trong những scene được team AI nêu trong incoming/ticket.md, thuộc job dùng guideline cũ theo jobs.csv và có ít nhất một box detection thuộc lớp bị đổi quy tắc.
- Tầng b (tier_b): các ảnh còn lại trong lô cũng thuộc job dùng guideline cũ và có box của lớp bị đổi quy tắc đó nhưng chưa được team AI báo cáo.
- Lý do lấy phiên bản guideline theo jobs.csv thay vì đọc trường guideline_version trên từng ảnh ở metadata.json là vì metadata từng ảnh có thể đang bị lỗi guideline_mismatch, còn jobs.csv lưu đúng phiên bản guideline được giao từ đầu job.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
Không ghi nhận bug trong các script của lab. Lưu ý nhỏ khi chạy kiểm tra chéo giữa các máy là release_id của cùng một seed có thể khác nhau nếu tạo lô trên hai máy khác nhau, nên khi chạy check_handover.py cần chạy trên đúng thư mục runs/ đã sinh ra lô v2 đó.
