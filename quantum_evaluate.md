# Đánh giá và Đề xuất Triển khai QKD cho Lưu trữ Filecoin

Tài liệu này trình bày đánh giá về tiềm năng, tính khả thi và hiệu quả của việc tích hợp Phân phối Khóa Lượng tử (QKD) vào quy trình lưu trữ dữ liệu trên Filecoin, cùng với hướng dẫn triển khai chi tiết.

## 1. Đánh giá (Evaluation)

### 1.1. Tiềm năng (Potential)
*   **Bảo mật tối thượng:** QKD cung cấp khả năng bảo mật dựa trên các định luật vật lý lượng tử thay vì độ khó toán học. Về lý thuyết, nó không thể bị bẻ khóa bởi máy tính cổ điển hay máy tính lượng tử trong tương lai.
*   **Giá trị công nghệ cao:** Việc tích hợp QKD vào một dự án IoT/Blockchain (Filecoin) tạo ra một điểm nhấn công nghệ cực kỳ mạnh mẽ, thể hiện sự tiên phong trong việc áp dụng các công nghệ Web3 và Quantum Computing.
*   **Bảo vệ dữ liệu nhạy cảm:** Đối với dữ liệu y tế (nhịp tim, SPO2) được thu thập trong dự án, việc áp dụng lớp bảo mật lượng tử đảm bảo quyền riêng tư tuyệt đối cho người dùng trước khi dữ liệu rời khỏi hệ thống cục bộ để lên mạng lưu trữ phi tập trung (IPFS/Filecoin).

### 1.2. Tính khả thi (Feasibility)
*   **Mô phỏng phần mềm (Software Simulation):** Hoàn toàn khả thi. Dự án hiện tại đã sử dụng thư viện `Qiskit` để mô phỏng các mạch lượng tử. Chúng ta có thể đóng gói logic từ `QKD implementation.ipynb` thành một module Python có thể chạy được trong container `filecoin_uploader`.
*   **Phần cứng:** Trong thực tế, QKD yêu cầu đường truyền cáp quang chuyên dụng và các thiết bị photon đơn lẻ. Tuy nhiên, trong phạm vi dự án này, chúng ta đang thực hiện **mô phỏng giao thức** trên máy tính cổ điển. Điều này hoàn toàn phù hợp với mục đích demo và giáo dục.
*   **Tích hợp hệ thống:** Hệ thống hiện tại được viết bằng Python (FastAPI, script upload), rất thuận tiện để tích hợp code Qiskit (cũng là Python).

### 1.3. Hiệu quả (Efficiency)
*   **Hiệu năng:** Việc mô phỏng mạch lượng tử trên máy tính cổ điển (thông qua Qiskit Aer) tốn nhiều tài nguyên CPU và RAM hơn so với mã hóa cổ điển (như AES).
    *   *Lưu ý:* Với các file transcript lớn, việc tạo ra một khóa OTP (One-Time Pad) có độ dài bằng độ dài file thông qua mô phỏng QKD sẽ rất chậm.
    *   *Giải pháp:* Sử dụng QKD để tạo ra một khóa ngắn (ví dụ: 256 bit), sau đó dùng khóa này cho thuật toán mã hóa đối xứng hiện đại (như AES-256) để mã hóa dữ liệu. Đây là mô hình lai (Hybrid) thường dùng trong thực tế.
*   **Lưu trữ:** Dữ liệu được mã hóa sẽ có kích thước tương đương hoặc lớn hơn một chút so với dữ liệu gốc, không ảnh hưởng đáng kể đến chi phí lưu trữ trên Filecoin.

---

## 2. Mô tả cách hiện thực hóa (Implementation Plan)

Để tích hợp QKD vào quy trình upload Filecoin hiện tại, chúng ta sẽ sửa đổi service `filecoin_uploader`.

### 2.1. Kiến trúc thay đổi
Quy trình hiện tại:
`Transcript JSON` -> `Filecoin Uploader` -> `Lighthouse/Filecoin`

Quy trình mới:
`Transcript JSON` -> **`QKD Module (Alice & Bob Simulation)`** -> `Encrypted Data` -> `Filecoin Uploader` -> `Lighthouse/Filecoin`

### 2.2. Các bước thực hiện chi tiết

#### Bước 1: Tạo Module QKD Service
Tạo một file mới `services/filecoin_uploader/qkd_service.py`. File này sẽ chuyển đổi code từ Jupyter Notebook thành một class Python tái sử dụng được.

Chức năng chính của class `QKDSimulator`:
1.  **`generate_key(length)`**: Thực hiện giao thức BB84 (Alice gửi, Eve chặn - tùy chọn, Bob nhận, Sifting) để tạo ra một chuỗi bit chung (Shared Key).
2.  **`encrypt_data(data, key)`**: Sử dụng khóa vừa tạo để mã hóa dữ liệu transcript.
    *   *Khuyến nghị:* Sử dụng AES-GCM với khóa được sinh ra từ QKD để đảm bảo hiệu năng và tính toàn vẹn dữ liệu.

#### Bước 2: Cập nhật Dependencies
Cần thêm các thư viện vào `services/filecoin_uploader/requirements.txt`:
*   `qiskit`: Để chạy mô phỏng lượng tử.
*   `qiskit-aer`: Backend giả lập cho Qiskit.
*   `cryptography`: Để thực hiện mã hóa AES (nếu dùng mô hình lai).

#### Bước 3: Tích hợp vào `main.py` của `filecoin_uploader`
Sửa hàm `handle_upload` hoặc `process_transcript_file` trong `services/filecoin_uploader/main.py`:

1.  **Đọc dữ liệu gốc:** Đọc file JSON transcript.
2.  **Chạy mô phỏng QKD:**
    *   Khởi tạo `QKDSimulator`.
    *   Gọi hàm tạo khóa (ví dụ: tạo khóa 256 bit).
    *   Lưu ý: Trong mô phỏng này, "Alice" là tiến trình uploader, và "Bob" cũng là tiến trình uploader (hoặc một module giả lập người nhận hợp pháp). Vì chúng ta đang lưu trữ lên Filecoin (công khai), nên hành động này giống như "Alice tự mã hóa dữ liệu bằng khóa lượng tử trước khi đẩy lên cloud".
3.  **Mã hóa dữ liệu:** Dùng khóa QKD để mã hóa nội dung JSON.
4.  **Upload:** Upload dữ liệu **đã mã hóa** lên Lighthouse/Filecoin thay vì dữ liệu gốc.
5.  **Lưu Metadata:** Trong file metadata (ví dụ `lighthouse_CID.json`), cần lưu thêm thông tin (không mật) về quá trình QKD để minh bạch hóa (ví dụ: độ dài khóa, tỷ lệ lỗi QBER đo được), nhưng **TUYỆT ĐỐI KHÔNG** lưu khóa bí mật.

### 2.3. Ví dụ Code (Giả mã)

```python
# services/filecoin_uploader/qkd_service.py

from qiskit import QuantumCircuit, execute, Aer
from cryptography.fernet import Fernet
import hashlib
import base64

class QKDSimulator:
    def __init__(self):
        self.backend = Aer.get_backend('qasm_simulator')

    def run_bb84_protocol(self, key_length=128):
        # ... (Logic từ notebook chuyển sang đây) ...
        # 1. Alice tạo bit & basis
        # 2. Encode qubits
        # 3. Bob đo (Measure)
        # 4. Sifting (So sánh basis)
        # 5. Trả về final_key (list of bits)
        pass

    def get_aes_key_from_qkd(self, qkd_bits):
        # Chuyển đổi list bit thành chuỗi bytes cho AES key
        bit_str = "".join(qkd_bits)
        # Hash để đảm bảo độ dài và độ ngẫu nhiên phù hợp cho AES
        digest = hashlib.sha256(bit_str.encode()).digest()
        return base64.urlsafe_b64encode(digest)

def encrypt_with_qkd(data_bytes):
    qkd = QKDSimulator()
    # Chạy BB84 để lấy raw bits
    raw_key_bits = qkd.run_bb84_protocol(key_length=256) 
    
    # Tạo key mã hóa thực tế
    fernet_key = qkd.get_aes_key_from_qkd(raw_key_bits)
    cipher = Fernet(fernet_key)
    
    # Mã hóa dữ liệu
    encrypted_data = cipher.encrypt(data_bytes)
    return encrypted_data, fernet_key
```

### 2.4. Lưu ý quan trọng
*   **Quản lý khóa:** Sau khi mã hóa và upload lên Filecoin, dữ liệu trên mạng là an toàn. Tuy nhiên, để giải mã lại sau này (khi tải về từ Dashboard), người dùng cần có **Khóa**.
*   Trong mô hình thực tế, khóa này nằm ở phía người nhận (Bob).
*   Trong mô hình lưu trữ này, chúng ta cần một cơ chế lưu trữ khóa an toàn cục bộ (ví dụ: lưu vào database `mariadb` nhưng ở bảng riêng được bảo vệ, hoặc xuất ra file key riêng cho admin) để sau này Dashboard có thể lấy khóa đó giải mã dữ liệu hiển thị cho người xem.

---
**Kết luận:** Việc thực hiện chức năng này sẽ nâng tầm dự án, biến nó thành một hệ thống **IoT - Blockchain - Quantum Safe** hoàn chỉnh.
