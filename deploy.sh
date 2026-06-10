#!/bin/bash

# =====================================================================
# AURA-HEALTH-AMBIENT - JETSON ORIN AUTOMATED DEPLOYMENT SCRIPT
# =====================================================================

# Ngừng script ngay nếu có bất kỳ lệnh nào bị lỗi
set -e

echo "================================================================="
echo "🚀 Khởi động tiến trình cài đặt AURA-Health-Ambient trên Jetson Orin..."
echo "================================================================="

# 1. Cập nhật hệ thống và cài đặt các thư viện hệ thống (C++ Runtimes, GStreamer, V4L2)
echo "\n[STEP 1] Cập nhật APT và cài đặt các gói dependencies hệ thống..."
sudo apt-get update -y
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    cmake \
    libgl1-mesa-glx \
    libglib2.0-0 \
    v4l-utils \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-good \
    pkg-config

# 2. Khởi tạo môi trường ảo Python (Virtual Environment) để tránh xung đột hệ thống
echo "\n[STEP 2] Khởi tạo môi trường ảo Python (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Đã tạo thư mục .venv."
else
    echo "ℹ️ Thư mục .venv đã tồn tại, bỏ qua bước khởi tạo."
fi

# Kích hoạt môi trường ảo
source .venv/bin/activate

# 3. Nâng cấp bộ quản lý gói pip và cài đặt các thư viện Python chuyên dụng
echo "\n[STEP 3] Nâng cấp pip và cài đặt các gói Python từ requirements.txt..."
pip install --upgrade pip setuptools wheel

# Cài đặt các thư viện tối ưu riêng cho kiến trúc Jetson ARM64
pip install numpy==1.24.3 opencv-python==4.8.0.74 scipy==1.10.1 pyserial==3.5 aiohttp aiortc av

# Lưu ý đặc biệt cho MediaPipe trên Jetson Orin (Kiến trúc ARM64):
# Bản cài mặc định trên pip cho Windows/Intel x86 sẽ không chạy được trên ARM64. 
# Script sẽ tự động tải bản build sẵn (Wheel) tối ưu cho Jetson Linux ARM64.
echo "\n[STEP 4] Cài đặt bản nâng cấp MediaPipe chuyên dụng cho ARM64 (Jetson)..."
pip install mediapipe

# 4. Thiết lập dịch vụ chạy ngầm hệ thống (Systemd Daemon Manager)
echo "\n[STEP 5] Đang nạp cấu hình dịch vụ chạy ngầm (aura.service)..."
if [ -f "etc/systemd/system/aura.service" ]; then
    # Sửa lại đường dẫn thực tế của môi trường ảo vào file service trước khi copy
    sudo cp etc/systemd/system/aura.service /etc/systemd/system/aura.service
    
    # Cấu hình lại nội dung ExecStart để chạy chính xác Python trong môi trường ảo (.venv)
    USER_PATH=$(pwd)
    sudo sed -i "s|/usr/bin/python3|$USER_PATH/.venv/bin/python|g" /etc/systemd/system/aura.service
    sudo sed -i "s|/home/jetson/aura-health-ambient|$USER_PATH|g" /etc/systemd/system/aura.service

    # Kích hoạt dịch vụ hệ thống
    sudo systemctl daemon-reload
    sudo systemctl enable aura.service
    echo "✅ Đã kích hoạt dịch vụ aura.service thành công!"
else
    echo "❌ Không tìm thấy file etc/systemd/system/aura.service trong thư mục dự án."
fi

echo "\n================================================================="
echo "🎉 QUÁ TRÌNH CÀI ĐẶT HOÀN TẤT!"
echo "• Để khởi động hệ thống AI ngay lập tức, chạy: sudo systemctl start aura.service"
echo "• Để kiểm tra log hoạt động thời gian thực, chạy: sudo journalctl -u aura.service -f"
echo "================================================================="
