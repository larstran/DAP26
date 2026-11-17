# **BÁO CÁO XỬ LÝ DỮ LIỆU THIẾU VÀ NGOẠI LAI**

**BÀI TẬP 3 \- Phân tích Khám phá và Trực quan hóa Dữ liệu**

## **1\. MỞ ĐẦU VÀ TỔNG QUAN BỘ DỮ LIỆU**

Trong quá trình xây dựng hệ thống Định giá Nhà tự động (AVM) cho phân khúc nhà cho thuê tại TP.HCM (dữ liệu thu thập thực tế từ nền tảng CafeLand kết hợp các nguồn bổ sung với quy mô \>= 5.000 dòng và \>= 8 biến), chất lượng dữ liệu thô (raw data) thường không hoàn hảo. Việc phát hiện và xử lý đúng đắn các giá trị thiếu (Missing Values) và giá trị ngoại lai (Outliers) đóng vai trò sống còn nhằm:

> * Tránh bóp méo các chỉ số thống kê mô tả (Mean, Standard Deviation).  
> * Ngăn chặn hiện tượng mô hình học máy (như Linear Regression hay Decision Tree Regression) bị lệch lạc hoặc học theo các điểm nhiễu.

## **2\. PHÂN TÍCH VÀ XỬ LÝ GIÁ TRỊ THIẾU (MISSING VALUES)**

### **2.1. Đánh giá tỷ lệ thiếu ban đầu**

Sau khi tổng hợp bộ dữ liệu thô từ CafeLand với quy mô ban đầu trên 20.000 dòng và lọc theo chuẩn phân khúc sinh viên/người lao động tại TP.HCM, bước kiểm tra chất lượng bằng phương pháp isnull().mean() \* 100 cho thấy bức tranh phân bổ dữ liệu khuyết như sau:

> * **Các biến định lượng cốt lõi (gia\_thue\_trieu\_thang, dien\_tich\_m2):** Tỷ lệ thiếu rất thấp (dưới 1% tổng số dòng). Cụ thể, tập dữ liệu ghi nhận 41 dòng thiếu giá thuê và 194 dòng thiếu diện tích do tin đăng sơ sài từ người cho thuê.  
> * **Các biến đặc trưng cấu trúc (so\_phong\_ngu, so\_toilet):** Tỷ lệ thiếu ở mức trung bình (khoảng 15% \- 25%) do các tin rao vặt phòng trọ bình dân thường không liệt kê tường minh số phòng ngủ.  
> * **Biến địa lý (quan\_huyen):** Tỷ lệ thiếu trực tiếp không đáng kể (\< 1%), tuy nhiên có một lượng lớn bản ghi (hơn 53% tương đương 8.659 dòng) được định vị thuộc nhóm nhãn "Khác" do thông tin địa chỉ từ nguồn cào chưa khớp với danh mục hành chính chuẩn.

### **2.2. Phân loại nguyên nhân thiếu dữ liệu (MCAR / MAR / MNAR)**

Dựa trên đặc thù của nền tảng tin rao bất động sản trực tuyến, các giá trị thiếu trong bộ dữ liệu được phân tích theo 3 nhóm học thuật:

> * **MCAR (Missing Completely at Random \- Thiếu hoàn toàn ngẫu nhiên):** Các trường hợp mất kết nối mạng ngẫu nhiên trong quá trình cào dữ liệu (requests timeout) dẫn đến đứt quãng một số trường lẻ tẻ.  
> * **MAR (Missing at Random \- Thiếu ngẫu nhiên có điều kiện):** Phổ biến ở các tin đăng phòng trọ giá rẻ, ký túc xá hoặc sleepbox, nơi người cho thuê thường bỏ trống các trường như so\_phong\_ngu hoặc so\_toilet vì mặc định ai cũng hiểu phân khúc này chỉ có 1 không gian chung.  
> * **MNAR (Missing Not at Random \- Thiếu có hệ thống):** Một số tin đăng cố tình giấu giá thuê hoặc diện tích để ép khách hàng liên hệ trực tiếp ("Liên hệ", "Thương lượng").

### **2.3. Chiến lược và Quyết định xử lý thực tế**

Nhằm đảm bảo dữ liệu đầu ra đủ điều kiện phục vụ mô hình định giá (AVM) mà không làm méo mó phân phối thị trường, nhóm đã áp dụng các nguyên tắc xử lý sau:

> * **Đối với biến mục tiêu (gia\_thue\_trieu\_thang) và diện tích (dien\_tich\_m2):** Do đây là hai biến quyết định năng lực dự báo của mô hình, mọi dòng dữ liệu bị khuyết các trường này đều bị loại bỏ trực tiếp (dropna) thay vì điền giá trị đại diện mù quáng, nhằm tránh tạo ra các điểm dữ liệu giả mạo làm sai lệch sai số huấn luyện.  
> * **Đối với biến cấu trúc (so\_phong\_ngu, so\_toilet):** Áp dụng chiến lược Nội suy nghiệp vụ (Domain-based Imputation) kết hợp quy tắc phân khúc:  
  * Phòng trọ / KTX (phong\_tro\_ktx): Mặc định gán so\_phong\_ngu \= 1\.  
  * Căn hộ / Chung cư mini (can\_ho): Suy luận số phòng ngủ dựa vào từ khóa tiêu đề hoặc gán giá trị phổ biến (mode \= 1 hoặc 2).  
  * Nhà nguyên căn (nha\_nguyen\_can): Mặc định gán so\_phong\_ngu \= 2 nếu thiếu thông tin.  
  * Vệ sinh riêng (has\_wc\_rieng): Nếu tin đăng có đề cập WC riêng, tự động gán so\_toilet \= 1\.  
> * **Đối với biến định danh vị địa lý (quan\_huyen):** Giữ nguyên các nhãn "Khác" hoặc các giá trị phân vùng hiện hữu, tuyệt đối không suy đoán mù quáng tên quận/huyện để tránh làm sai lệch độ lệch chuẩn không gian địa lý của thị trường TP.HCM.

## **3\. PHÁT HIỆN VÀ XỬ LÝ GIÁ TRỊ NGOẠI LAI (OUTLIERS)**

### **3.1. Phương pháp định lượng ngoại lai**

Thị trường bất động sản luôn tồn tại sự phân hóa mạnh mẽ giữa các phân khúc bình dân (phòng trọ sinh viên) và cao cấp (biệt thự, căn hộ dịch vụ hạng sang). Để xác định chính xác các điểm dữ liệu bất thường (outliers) mà không bị phụ thuộc vào giả định phân phối chuẩn, đồ án đã triển khai phương pháp IQR (Interquartile Range \- Tukey's Fences) kết hợp kiểm tra chéo:

> * Công thức tính ngưỡng chặn:

> $IQR={Q}_{3}-{Q}_{1}$

> $Ngưỡng\ dưới={Q}_{1}-1.5\times IQR$

> $Ngưỡng\ trên={Q}_{3}+1.5\times IQR$

> * **Ưu điểm:** Phương pháp IQR dựa trên phân vị (Q1, Q3, Median) nên hoàn toàn ổn định, không bị bóp méo bởi chính các giá trị cực đoan có sẵn trong tập dữ liệu bất động sản vốn có độ lệch phải (right-skewed) rất cao.

### **3.2. Triển khai kỹ thuật: Cắm cờ (Flagging) thay vì xóa bỏ**

Khác với các phương pháp xử lý truyền thống thường cắt tỉa dữ liệu bằng hàm clip() hoặc xóa sạch dòng ngoại lai, quy trình thực tế trong dự án đã chọn một hướng tiếp cận an toàn hơn nhằm bảo toàn thông tin thị trường:

> * **Đánh dấu cờ ngoại lai (IQR Flagging):** Hệ thống tạo ra các cột kiểm soát chuyên biệt (ví dụ: gia\_iqr\_flag, dien\_tich\_iqr\_flag) để ghi nhận các bản ghi nằm ngoài hàng rào Tukey.  
> * **Lý do giữ lại giá trị thật:** Các tin đăng có giá thuê hoặc diện tích rất lớn (như nhà nguyên căn cao cấp, penthouse) tuy là ngoại lai so với phân khúc trọ sinh viên thông thường, nhưng đây là các giá trị thực tế của thị trường TP.HCM, không phải lỗi cào dữ liệu (scraping artifacts). Việc giữ nguyên các dòng này (nhưng có cắm cờ đánh dấu) giúp các mô hình học máy phi tuyến tính (như Random Forest, XGBoost ở Bài tập sau) học được biên độ rộng của thị trường.  
> * **Loại bỏ dữ liệu rác (Garbage Removal):** Chỉ thực hiện xóa bỏ hoàn toàn các dòng dữ liệu bị lỗi kỹ thuật rõ rệt (ví dụ: diện tích âm hoặc bằng 0, giá thuê nhỏ hơn 200.000 VNĐ/tháng cho nhà nguyên căn do người đăng nhập thiếu số 0).

## **4\. BẢNG TỔNG HỢP QUYẾT ĐỊNH XỬ LÝ THEO BIẾN (SUMMARY MATRIX)**

Bảng tổng hợp dưới đây hệ thống hóa toàn bộ phương pháp phát hiện, xử lý và lý do khoa học áp dụng cho từng biến chính trong mô hình AVM:

| Tên biến (Columns) | Tỷ lệ thiếu thực tế | Phương pháp phát hiện | Phương pháp xử lý thực tế | Lý do khoa học   |
| :---- | :---- | :---- | :---- | :---- |
| **gia\_thue\_trieu\_thang** | Thấp (\~0.25% \- 41 dòng) | Kiểm tra isnull() & Biểu đồ phân phối | Loại bỏ (dropna) các dòng thiếu giá trị; Đánh dấu cờ (flag) ngoại lai bằng IQR thay vì xóa bỏ thô bạo. | Biến mục tiêu (y) tối quan trọng; không điền giá trị trung bình để tránh bóp méo sai số dự báo của mô hình AVM. |
| **dien\_tich\_m2** | Thấp (\~1.18% \- 194 dòng) | Kiểm tra isnull() & IQR | Loại bỏ (dropna) các dòng thiếu diện tích; giữ nguyên giá trị thực tế | Diện tích là trọng số cấu thành đơn giá trên mỗi m², không thể nội suy ngẫu nhiên gây sai lệch thông tin. |
| **so\_phong\_ngu / so\_toilet** | Trung bình (15% \- 25%) | Kiểm tra isnull() | Nội suy nghiệp vụ theo loại hình (Phòng trọ/KTX mặc định 1, nhà nguyên căn 2). | Tận dụng đặc điểm phân khúc thị trường bình dân để giữ lại tối đa số lượng mẫu huấn luyện thay vì xóa dòng. |
| **quan\_huyen** | Trống \< 1% / Nhãn "Khác" \> 53% | Phân tích tần suất value\_counts() | Giữ nguyên các nhãn "Khác" hoặc giá trị phân vùng hiện hữu, tuyệt đối không suy đoán mù quáng. | Đảm bảo tính minh bạch về vị trí địa lý, tránh gán sai lệch hành chính làm lệch phân tích không gian. |

