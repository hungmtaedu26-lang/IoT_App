# Mô tả Dự án: Quantum Key Distribution (QKD) Protocol Implementation

## 1. Tổng quan Dự án
Dự án này là một mô phỏng giao thức **Phân phối Khóa Lượng tử (Quantum Key Distribution - QKD)**, cụ thể là giao thức **BB84**, được thực hiện trên môi trường giả lập lượng tử.

- **Mục tiêu:** Minh họa cách thức hai bên (thường gọi là Alice và Bob) có thể tạo ra một khóa bí mật chung an toàn dựa trên các nguyên lý cơ học lượng tử, đồng thời phát hiện sự hiện diện của kẻ nghe lén (Eve).
- **Công nghệ sử dụng:**
  - Ngôn ngữ lập trình: **Python**
  - Thư viện lượng tử: **Qiskit** (của IBM)
  - Môi trường: **Jupyter Notebook**

## 2. Cấu trúc và Quy trình Hoạt động
Dự án được trình bày dưới dạng một file Jupyter Notebook (`QKD Implementation.ipynb`) với các bước (Phase) rõ ràng:

### Phase 1: Alice tạo và gửi khóa (Generate & Send)
- **Alice** tạo ra một chuỗi các bit ngẫu nhiên (0 hoặc 1).
- Cô ấy cũng chọn ngẫu nhiên các cơ sở đo (bases) là **Z** (cơ sở chuẩn) hoặc **X** (cơ sở Hadamard).
- Dựa trên bit và cơ sở đã chọn, Alice mã hóa thông tin vào các trạng thái lượng tử (qubit) và gửi chúng đi qua kênh lượng tử.

### Phase 2: Kịch bản Kẻ nghe lén (Eve Interception)
- Đây là phần minh họa tính bảo mật. **Eve** chặn các qubit trên đường truyền.
- Vì Eve không biết cơ sở đo của Alice, cô ấy phải đoán ngẫu nhiên cơ sở để đo các qubit này.
- Hành động đo lường của Eve sẽ làm **thay đổi trạng thái lượng tử** của các qubit (do nguyên lý sụp đổ hàm sóng), để lại "dấu vết" mà Alice và Bob có thể phát hiện sau này.
- Sau khi đo, Eve gửi lại các qubit (đã bị biến đổi) cho Bob.

### Phase 3: Bob nhận và đo (Receive & Measure)
- **Bob** nhận các qubit (có thể đã bị Eve can thiệp hoặc không).
- Bob cũng chọn ngẫu nhiên các cơ sở đo (Z hoặc X) để đo các qubit này mà không biết cơ sở Alice đã dùng.

### Phase 4: So sánh và Sàng lọc (Sifting & Security Check)
Đây là giai đoạn quan trọng để biến dữ liệu thô thành khóa bí mật an toàn.

1.  **Sàng lọc cơ sở (Sifting):**
    - Alice và Bob sử dụng kênh cổ điển (công khai) để trao đổi danh sách các **cơ sở đo** (bases) mà họ đã dùng cho mỗi photon (ví dụ: photon 1 dùng cơ sở +, photon 2 dùng cơ sở x...).
    - **Quan trọng:** Họ *không* tiết lộ kết quả bit (0 hay 1), chỉ tiết lộ loại cơ sở.
    - Họ so sánh và chỉ giữ lại các bit tại những vị trí mà **cơ sở của Alice và Bob trùng khớp**.
    - Các bit tại vị trí lệch cơ sở sẽ bị loại bỏ (vì kết quả đo là ngẫu nhiên 50/50, không có giá trị).

2.  **Kiểm tra bảo mật (Security Check / Error Estimation):**
    - Để phát hiện Eve, Alice và Bob chọn ngẫu nhiên một phần của chuỗi bit đã sàng lọc (ví dụ: 50% số bit) và công khai so sánh chúng.
    - **Tính tỷ lệ lỗi (QBER - Quantum Bit Error Rate):**
        - Nếu không có Eve: Các bit này phải hoàn toàn trùng khớp (QBER = 0%).
        - Nếu có Eve: Do hành động đo lường của Eve làm sụp đổ trạng thái lượng tử, xác suất Eve chọn sai cơ sở là 50%, và khi Bob đo lại cũng có xác suất sai khác. Điều này tạo ra tỷ lệ lỗi khoảng 25% trong chuỗi bit.
    - **Quyết định:**
        - Nếu QBER < Ngưỡng cho phép (thường là 11%): Kênh được coi là an toàn. Họ loại bỏ các bit đã dùng để kiểm tra và giữ phần còn lại làm khóa bí mật (Raw Key).
        - Nếu QBER > Ngưỡng: Có kẻ nghe lén. Hủy toàn bộ quá trình và bắt đầu lại.

### Phase 5: Mã hóa tin nhắn (Encryption)
Sau khi có khóa bí mật chung (Shared Secret Key), họ sử dụng nó để mã hóa dữ liệu theo phương pháp **One-Time Pad (OTP)** - phương pháp bảo mật tuyệt đối về mặt lý thuyết thông tin.

- **Mã hóa (Alice):**
    - Tin nhắn văn bản được chuyển thành chuỗi bit (Binary).
    - Thực hiện phép toán **XOR** từng bit của tin nhắn với từng bit của khóa.
    - `Ciphertext = Message XOR Key`
- **Gửi tin:** Alice gửi `Ciphertext` cho Bob qua kênh công khai.
- **Giải mã (Bob):**
    - Bob nhận `Ciphertext`.
    - Thực hiện phép toán **XOR** lại với khóa bí mật của mình (giống hệt khóa Alice).
    - `Message = Ciphertext XOR Key` (vì `A XOR B XOR B = A`).
- **Lưu ý:** Khóa chỉ được dùng một lần duy nhất cho mỗi tin nhắn để đảm bảo an toàn.

## 3. Ý nghĩa
Dự án này giúp người xem hình dung trực quan về sức mạnh của mật mã lượng tử:
- **Tính an toàn tuyệt đối:** Dựa trên vật lý thay vì toán học.
- **Khả năng phát hiện xâm nhập:** Bất kỳ nỗ lực nghe lén nào cũng sẽ thay đổi trạng thái vật lý của thông tin và bị phát hiện.
