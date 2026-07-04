# Hướng dẫn triển khai nhanh trên máy công ty

## 1. Copy dự án về máy công ty
- Sao chép toàn bộ thư mục dự án này sang máy công ty bằng USB hoặc mạng nội bộ.
- Đảm bảo thư mục chứa các file: Dockerfile, docker-compose.yml, backend/, frontend/, database/, data/.

## 2. Cài đặt Docker Desktop
- Tải Docker Desktop tại: https://www.docker.com/products/docker-desktop/
- Cài đặt theo hướng dẫn mặc định.
- Sau khi cài xong, mở Docker Desktop và chờ đến khi trạng thái chạy ổn định.

## 3. Build và chạy ứng dụng
Mở Terminal/PowerShell trong thư mục dự án và chạy:

```bash
docker-compose up -d --build
```

Nếu hệ thống đã cài Docker Compose cũ, dùng:

```bash
docker compose up -d --build
```

## 4. Kiểm tra ứng dụng
- FastAPI: http://<địa_chỉ_ip_máy>:8000/docs
- Streamlit: http://<địa_chỉ_ip_máy>:8501

## 5. Xem địa chỉ IP nội bộ của máy
Trên Windows, mở Command Prompt rồi chạy:

```cmd
ipconfig
```

Tìm dòng "IPv4 Address" (thường là dạng 192.168.x.x).

## 6. Cho người khác dùng chung trong mạng LAN
- Mỗi người chỉ cần mở Chrome và truy cập vào:
  - http://<địa_chỉ_ip_máy>:8501
- Nếu gặp vấn đề, kiểm tra tường lửa Windows cho phép cổng 8501.
