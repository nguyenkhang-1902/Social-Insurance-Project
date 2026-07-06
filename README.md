# Hệ thống quản lý và xuất báo cáo BHXH

<div align="center">
  <img src="assets/PLACEHOLDER.png" alt="Ảnh minh họa hệ thống BHXH" width="900" />
</div>

<p align="center">
  <strong>Quản lý dữ liệu lao động, cập nhật tháng và xuất báo cáo Excel một cách dễ dàng.</strong>
</p>

README này hướng dẫn người dùng cách nhập dữ liệu lao động, cập nhật dữ liệu tháng và xuất các báo cáo Excel phục vụ công tác quản lý bảo hiểm xã hội.

## 🛠️ Hướng dẫn cài đặt & Chạy ứng dụng
1. Tải toàn bộ thư mục dự án về máy.
2. Đảm bảo máy tính có đủ quyền truy cập thư mục.
3. Click đúp vào file [CHAY_CHUONG_TRINH.bat](CHAY_CHUONG_TRINH.bat).
4. Hệ thống sẽ tự động mở trình duyệt tại địa chỉ http://127.0.0.1:8501.

## 1. Hướng dẫn người dùng mới

Nếu bạn là người dùng lần đầu, hãy thực hiện theo quy trình ngắn dưới đây:

1. Mở chương trình và chọn tháng/năm cần cập nhật.
2. Tải file dữ liệu tháng lên hệ thống.
3. Kiểm tra thông báo hệ thống để đảm bảo file đúng định dạng và đúng tháng/năm.
4. Nhấn xác nhận cập nhật nếu dữ liệu hợp lệ.
5. Sau khi cập nhật, dùng các nút xuất báo cáo để tải file Excel về máy.

## 🤝 Liên hệ
- Người phát triển: [Nguyễn Minh Khang]
- Công ty: [Hansoll Vina]

> Nếu bạn chưa quen với giao diện, hãy bắt đầu từ phần “Cập nhật dữ liệu hàng tháng” trước, sau đó mới dùng phần “Xuất báo cáo”.

## 2. Quy trình thao tác nhanh

### Bước 1: Cập nhật dữ liệu
- Chọn tháng và năm.
- Tải file Excel/CSV lên.
- Xác nhận cập nhật.

### Bước 2: Xuất báo cáo
- Nhập mã nhân viên nếu cần xuất báo cáo cá nhân.
- Chọn nút xuất tương ứng cho danh sách đang làm việc hoặc nghỉ việc.

### Bước 3: Tải file về máy
- File Excel sẽ được tải xuống tự động.
- Mở file để kiểm tra nội dung trước khi dùng cho công việc.

## 3. Mục tiêu của dự án

Dự án này giúp người dùng:
- tải file dữ liệu tháng (Excel/CSV) vào hệ thống;
- kiểm tra tháng/năm trong file trước khi cập nhật;
- lưu trữ dữ liệu vào cơ sở dữ liệu nội bộ;
- xuất các báo cáo Excel theo nhu cầu: báo cáo cá nhân, danh sách lao động đang làm việc và danh sách lao động nghỉ việc.

Hệ thống gồm hai phần chính:
- giao diện người dùng bằng Streamlit;
- API backend bằng FastAPI để xử lý dữ liệu và xuất file.

---

## 5. Các chức năng chính

### 5.1. Cập nhật dữ liệu hàng tháng
Trong phần đầu giao diện, người dùng có thể:
- chọn tháng và năm;
- tải file Excel/CSV chứa dữ liệu cập nhật;
- kiểm tra file có đúng tháng/năm hay không;
- xác nhận cập nhật dữ liệu vào hệ thống.

Hệ thống sẽ:
- đọc thông tin tháng/năm từ file;
- kiểm tra dữ liệu tháng đó đã tồn tại chưa;
- nếu cần, ghi đè dữ liệu cũ bằng dữ liệu mới;
- lưu dữ liệu vào cơ sở dữ liệu và tạo các bản ghi lịch sử phù hợp.

### 5.2. Xuất báo cáo Excel
Giao diện có 3 nút xuất file chính:
- Xuất báo cáo cá nhân;
- Xuất danh sách lao động đang làm việc;
- Xuất danh sách lao động nghỉ việc.

Các báo cáo này được tạo dưới dạng file Excel và tải về trực tiếp cho người dùng.

---

## 6. Cách chạy chương trình

### 6.1. Chạy nhanh bằng file Windows batch
Nếu đang dùng Windows, có thể chạy file sau:
- [CHAY_CHUONG_TRINH.bat](CHAY_CHUONG_TRINH.bat)

File này sẽ cố gắng dùng Python portable có sẵn trong thư mục dự án để khởi động backend.

### 6.2. Chạy thủ công
Nếu cần chạy thủ công, có thể thực hiện theo hướng dẫn sau:

1. Vào thư mục dự án.
2. Khởi động backend API:
   - python Code/main.py
   - hoặc dùng uvicorn nếu đã cài đặt.
3. Khởi động giao diện Streamlit:
   - streamlit run Code/app.py

> Lưu ý: Backend và giao diện nên được chạy đồng thời để nút xuất báo cáo hoạt động đúng.

### 6.3. Môi trường Python
Dự án có sẵn thư mục Python portable tại [python-3.15.0b3-embed-amd64](python-3.15.0b3-embed-amd64). Nếu máy chưa cài Python hệ thống, có thể dùng thư mục này để chạy chương trình.

---

## 7. Mô tả từng nút xuất file

### 7.1. Nút “Tải Report Cá nhân”
Nút này dùng để xuất lịch sử bảo hiểm của một nhân viên cụ thể.

Các trường hợp thường gặp:
- Nếu chưa nhập mã nhân viên: hệ thống sẽ hiển thị cảnh báo yêu cầu nhập mã nhân viên trước khi xuất.
- Nếu mã nhân viên không tồn tại trong hệ thống: hệ thống sẽ hiển thị cảnh báo và không tạo file.
- Nếu mã nhân viên tồn tại nhưng chưa có dữ liệu lịch sử: hệ thống vẫn có thể tạo file báo cáo, nhưng nội dung bảng sẽ trống hoặc chỉ có phần đầu báo cáo.
- Nếu mã nhân viên có nhiều bản ghi lịch sử: file xuất sẽ tổng hợp toàn bộ dữ liệu lịch sử theo từng tháng/năm.

File xuất có dạng Excel và thường được đặt tên theo mã nhân viên và tên nhân viên để dễ nhận biết.

### 7.2. Nút “Tải Danh sách Đang làm việc”
Nút này xuất danh sách người lao động đang làm việc trong tháng/năm đang chọn.

Các trường hợp thường gặp:
- Nếu tháng/năm đang chọn không có dữ liệu: file vẫn có thể được tạo nhưng nội dung sẽ trống.
- Nếu có dữ liệu cho tháng/năm đó: hệ thống sẽ lấy các bản ghi có trạng thái đang làm việc và xuất thành file Excel.
- Báo cáo này thường dùng để kiểm tra số lượng lao động đang hoạt động trong một tháng cụ thể.

### 7.3. Nút “Tải Danh sách Nhân viên nghỉ việc”
Nút này xuất danh sách nhân viên nghỉ việc tương ứng với tháng/năm đang chọn.

Các trường hợp thường gặp:
- Nếu không có nhân viên nghỉ việc trong tháng/năm đang chọn: file sẽ được tạo với nội dung rỗng hoặc chỉ có tiêu đề báo cáo.
- Nếu có nhân viên nghỉ việc: hệ thống sẽ đưa các bản ghi nghỉ việc vào file Excel để người dùng xem và lưu trữ.
- Báo cáo này thường dùng cho công tác thống kê và theo dõi tình trạng nghỉ việc trong tháng.

### 7.4. Ảnh minh họa và cách chụp
Bạn có thể lưu ảnh minh họa vào thư mục [assets](assets) để làm tài liệu trực quan cho README.

Các ảnh nên chụp cho các bước sau:
- màn hình upload dữ liệu tháng;
- màn hình chọn tháng/năm và nút xác nhận cập nhật;
- màn hình nhập mã nhân viên và nút xuất báo cáo cá nhân;
- màn hình nút xuất danh sách đang làm việc;
- màn hình nút xuất danh sách nghỉ việc.

Gợi ý cách chụp:
- chụp ở chế độ đầy màn hình để thấy toàn bộ giao diện;
- chọn nền sáng, tránh hiện thông báo quá nhiều che khuất nội dung;
- chụp trước khi nhấn nút để thấy trạng thái ban đầu;
- chụp sau khi nhấn nút để thấy kết quả hoặc file được tải về;
- đặt tên file ngắn gọn, ví dụ: upload-data.png, export-personal.png, export-working.png, export-resigned.png.

Sau khi có ảnh, bạn chỉ cần thay đường dẫn trong README thành đường dẫn ảnh mới.

---

## 8. Bố cục thư mục

```text
App_BHXH/
├── Code/                  # code chính của hệ thống
├── Data/                  # dữ liệu runtime và database
├── Templates/             # template báo cáo và file mẫu
├── assets/                # ảnh minh họa cho README
├── database/              # thư mục dữ liệu liên quan database
├── CHAY_CHUONG_TRINH.bat  # file chạy nhanh trên Windows
└── README.md              # tài liệu hướng dẫn
```

Dự án được tổ chức như sau:

- [Code](Code): chứa toàn bộ code chính của hệ thống.
  - [Code/app.py](Code/app.py): giao diện Streamlit cho người dùng.
  - [Code/main.py](Code/main.py): backend FastAPI, xử lý upload, lưu trữ và xuất báo cáo.
  - [Code/database.py](Code/database.py): cấu hình kết nối cơ sở dữ liệu.
  - [Code/models.py](Code/models.py): định nghĩa model dữ liệu như Employee và PayrollHistory.
  - [Code/etl_scripts](Code/etl_scripts): các script ETL và xử lý dữ liệu bổ sung.
  - [Code/all_tests.py](Code/all_tests.py): bộ test đơn vị.
  - [Code/generate_valid_sample.py](Code/generate_valid_sample.py): script tạo dữ liệu mẫu.

- [Data](Data): thư mục dùng để lưu trữ cơ sở dữ liệu và các dữ liệu runtime phát sinh.

- [Templates](Templates): chứa template báo cáo và các file dữ liệu mẫu dùng cho xử lý đầu vào.

- [assets](assets): lưu hình ảnh, ảnh minh họa hoặc tài nguyên phụ trợ.

- [database](database): thư mục lưu trữ dữ liệu liên quan đến database hoặc các file phụ hỗ trợ.

- [python-3.15.0b3-embed-amd64](python-3.15.0b3-embed-amd64): Python portable có sẵn trong dự án.

- [CHAY_CHUONG_TRINH.bat](CHAY_CHUONG_TRINH.bat): script chạy nhanh trên Windows.

---

## 9. Lưu ý khi sử dụng

- File dữ liệu upload nên có cấu trúc rõ ràng và chứa thông tin tháng/năm để hệ thống nhận diện đúng.
- Nếu file không chứa thông tin tháng/năm hoặc cấu trúc không phù hợp, hệ thống sẽ cảnh báo và từ chối cập nhật.
- Nên kiểm tra lại tháng/năm trước khi xác nhận cập nhật để tránh ghi đè dữ liệu sai.
- Sau khi xuất file, người dùng nên lưu file vào thư mục phù hợp để tiện tra cứu.

---

## 10. Gợi ý nâng cấp trong tương lai

- bổ sung kiểm tra dữ liệu đầu vào tự động chi tiết hơn;
- thêm màn hình thống kê trực quan cho người dùng;
- hỗ trợ xuất nhiều định dạng hơn như PDF hoặc CSV;
- tích hợp thêm ghi log thao tác và lịch sử cập nhật.

---

## 11. Ghi chú cho bạn khi bổ sung ảnh

Khi bạn đã chụp xong các ảnh minh họa, hãy lưu vào thư mục [assets](assets) và thay thế các placeholder sau:
- [assets/PLACEHOLDER.png](assets/PLACEHOLDER.png)

Nếu muốn, bạn có thể tạo thêm các ảnh riêng cho từng mục như:
- [assets/upload-data.png](assets/upload-data.png)
- [assets/export-personal.png](assets/export-personal.png)
- [assets/export-working.png](assets/export-working.png)
- [assets/export-resigned.png](assets/export-resigned.png)

---
