# Thuyết minh về Hệ thống Chuyển tiền Bảo mật dùng zk-SNARK

## 1. Tổng quan dự án
Dự án cung cấp một mô hình chuyển tiền bảo mật giữa hai thiết bị (Device A và Device B) thông qua cơ chế bằng chứng không tiết lộ (Zero-Knowledge Proof – ZKP) thuộc họ zk-SNARK. Kiến trúc được triển khai bằng Python với FastAPI, sử dụng các dịch vụ nền độc lập để phục vụ giao diện người dùng, sinh bằng chứng, mô phỏng hợp đồng thông minh và lưu trữ phân tán. Kho mã nhắm tới hai chế độ vận hành: (i) mô phỏng thuần Python phục vụ kiểm thử nhanh, (ii) tích hợp PySNARK để tạo bằng chứng Groth16 thực sự cho môi trường Unix/MacOS.

## 2. Thành phần chính
### 2.1 Device A – Giao diện người gửi
- `services/device_a/app.py` định nghĩa API FastAPI nhận yêu cầu chuyển tiền, kiểm tra số dư và gọi SNARK Runner để sinh bằng chứng. Ứng dụng cung cấp điểm cuối `/transfer`, trang tình trạng `/state` và giao diện web tối giản ở `/ui`. Trạng thái số dư người gửi lưu trong bộ nhớ và bảo vệ bằng khóa `threading.Lock` để bảo đảm an toàn luồng.
- Thư mục `static/` chứa HTML/CSS/JS tạo biểu mẫu nhập số liệu và hiển thị kết quả chuyển tiền.

### 2.2 SNARK Runner – Trình sinh bằng chứng
- `services/snark_runner/app.py` nhận yêu cầu chuyển tiền từ Device A, tính số dư sau giao dịch và chọn backend SNARK thông qua `resolve_backend`.
- Lớp nền `BaseSnarkBackend` trong `snark_pipeline.py` trừu tượng hóa quy trình sinh bằng chứng. Backend mặc định `MockSnarkBackend` sử dụng hàm băm Poseidon giả lập (triển khai bằng SHA-256) để sinh cam kết và xuất ba gói dữ liệu: bằng chứng, đầu ra công khai, nhân chứng riêng tư.
- Backend thực `PySnarkBackend` (nếu bật `ENABLE_REAL_SNARK`) nhập PySNARK, khởi tạo khóa và thực thi mạch `transfer_circuit.py` nhằm tạo bằng chứng Groth16. Mạch bắt buộc các bất biến: người gửi không âm, cập nhật số dư chính xác, người nhận không âm. Các cam kết trạng thái trước/sau được tính từ số dư và nonce ngẫu nhiên.

### 2.3 Device B – Giao diện người nhận
- `services/device_b/app.py` cung cấp API lấy và cập nhật số dư nhận. SNARK Runner gọi endpoint `/update_balance` để phản ánh số dư mới sau khi chứng minh thành công.

### 2.4 Dịch vụ hợp đồng thông minh mô phỏng
- `services/smart_contract/listener.py` dùng `watchfiles` để theo dõi thư mục bằng chứng, kiểm tra tính nhất quán giữa chứng cứ công khai và nhân chứng, rồi ghi bản ghi xác minh vào `data/transcripts/`. Đây là mô hình hóa hành vi hợp đồng thông minh xác thực bằng chứng trên chuỗi.

### 2.5 Dịch vụ lưu trữ phân tán giả lập
- `services/storage/ipfs.py` mô phỏng việc tải bằng chứng lên IPFS bằng cách băm tệp và ghi siêu dữ liệu CID.
- `services/storage/filecoin.py` theo dõi nhật ký xác minh và sinh mã giao dịch Filecoin giả. Cả hai dịch vụ dùng `watchfiles` để kích hoạt khi có tệp mới.

### 2.6 Thư viện dùng chung
- `shared/config.py` chuẩn hóa cấu hình (cổng dịch vụ, thư mục dữ liệu) và đảm bảo tạo thư mục đích.
- `shared/models.py` định nghĩa các mô hình dữ liệu Pydantic cho yêu cầu chuyển tiền, phản hồi SNARK và trạng thái thiết bị.
- `shared/proof_store.py` chịu trách nhiệm ghi tệp JSON của bằng chứng, tín hiệu công khai và nhân chứng.
- `shared/utils.py` cung cấp công cụ tạo mã vết, thời gian đơn điệu và hàm băm Poseidon giả lập.
- `shared/logging.py` cấu hình định dạng log thống nhất.

## 3. Quy trình vận hành
1. Người dùng ở Device A nhập số dư và số tiền cần chuyển trên giao diện web. Yêu cầu được gửi tới endpoint `/transfer`.
2. Device A sinh `trace_id`, kiểm tra số dư, rồi gửi payload tới SNARK Runner.
3. SNARK Runner tính toán trạng thái sau giao dịch, sinh nonce ngẫu nhiên cho mỗi cam kết, gọi backend SNARK:
   - Với chế độ mô phỏng, backend tạo gói dữ liệu mô phỏng.
   - Với PySNARK, mạch `transfer_circuit` chạy trong môi trường PySNARK để sinh bằng chứng thực.
4. SNARK Runner ghi hiện vật bằng chứng vào đĩa (`data/proofs/<trace_id>/`), thông báo Device B cập nhật số dư và trả về phản hồi chứa số dư mới cùng metadata.
5. Listener hợp đồng thông minh giám sát thư mục chứng cứ, xác minh các bất biến và ghi transcript xác minh.
6. Dịch vụ IPFS/Filecoin theo dõi bằng chứng và transcript để sinh bản ghi lưu trữ phân tán giả lập.

## 4. Cơ sở lý thuyết và mô hình bảo mật
### 4.1 zk-SNARK Groth16
Groth16 là giao thức zk-SNARK thời gian hằng số, đảm bảo tính âm thầm (zero-knowledge) và xác minh nhanh. Trong dự án, mạch chuyển tiền được chuyển thành dạng ràng buộc bậc hai (R1CS) bởi PySNARK. Proving key và verifying key được thiết lập một lần thông qua `initialize_pysnark`. Khi chạy mạch, PySNARK xuất chứng cứ (`proof`) và giá trị công khai (`io`). Backend mô phỏng tái hiện cấu trúc đầu ra (bằng chứng, public signals, witness) để giữ nguyên đường đi dữ liệu.

### 4.2 Cam kết trạng thái
Các trạng thái số dư trước/sau được cam kết bằng hàm Poseidon-like (ở đây dùng SHA-256 thay thế để tránh phụ thuộc ngoài). Cam kết đảm bảo rằng người xác minh chỉ thấy giá trị băm, không thấy số dư thực nhưng vẫn xác thực được sự nhất quán nếu cần đối chiếu với nhân chứng.

### 4.3 Bảo toàn số dư và tính toàn vẹn
Mạch và backend đều thực thi các điều kiện:
- `sender_before - amount == sender_after`
- `receiver_before + amount == receiver_after`
- Các số dư sau giao dịch không âm.
Điều này bảo đảm giao dịch không thể tạo tiền hoặc khiến số dư âm. Listener mô phỏng hợp đồng thông minh kiểm tra lại các bất biến từ bằng chứng và nhân chứng đã lưu, tạo thêm lớp bảo vệ.

### 4.4 Ngẫu nhiên hóa và tính riêng tư
Nonce ngẫu nhiên (251 bit) được sinh qua `secrets.randbits` nhằm ẩn số dư thực trong cam kết. Tính riêng tư phụ thuộc vào bí mật của nonce và tính chất chống xung đột của hàm Poseidon-like. Khi sử dụng PySNARK, bằng chứng Groth16 bảo đảm không rò rỉ thông tin ngoài các giá trị công khai (số tiền và số dư sau giao dịch).

## 5. Công cụ và quy trình triển khai
- **FastAPI & Uvicorn**: triển khai các dịch vụ HTTP nhẹ, dễ tích hợp. Các dịch vụ chạy đồng thời được điều phối bởi script `scripts/run_all.py` thông qua `subprocess` và xử lý tín hiệu để tắt đồng bộ.
- **Watchfiles**: cơ chế bất đồng bộ theo dõi thay đổi hệ thống tệp, dùng cho listener hợp đồng thông minh và mô phỏng IPFS/Filecoin.
- **PySNARK**: thư viện xây dựng mạch zk-SNARK Groth16 bằng Python, cung cấp API `Var`, `vc_p`, `prove`. Tệp `snark_init.py` đặt biến môi trường và thư mục cần thiết cho qaptools.
- **Pydantic**: đảm bảo xác thực dữ liệu đầu vào/ra giữa các dịch vụ.
- **dotenv**: nạp biến môi trường cấu hình từ tệp `.env` nếu có.

## 6. Tổ chức dữ liệu và lưu trữ
Thư mục `data/` chứa toàn bộ hiện vật khi hệ thống chạy:
- `proofs/<trace_id>/` lưu trữ `proof.json`, `public.json`, `witness.json`.
- `transcripts/` chứa kết quả xác minh của listener.
- `ipfs/` và `filecoin/` lưu bản ghi mô phỏng việc pinning và deal submission.
Cấu trúc này hỗ trợ kiểm toán hậu kiểm, cho phép đối chiếu giữa các lớp dịch vụ.

## 7. Quy trình mở rộng và bảo trì
- **Bật backend thật**: đặt `ENABLE_REAL_SNARK=true` trong môi trường để `resolve_backend` tạo `PySnarkBackend`. Khi đó cần cài PySNARK và qaptools.
- **Thay đổi tham số**: `shared/config.py` gom toàn bộ cài đặt, dễ tùy biến cổng, host, thư mục hoặc URL cập nhật Device B.
- **Bảo mật sản xuất**: nên bổ sung xác thực API giữa các dịch vụ, mã hóa AES với khóa từ `AES_KEY` để mã hóa nhân chứng khi ghi đĩa, và triển khai Poseidon thật thay cho hàm băm SHA-256 mô phỏng.
- **Triển khai phân tán**: có thể chuyển từng dịch vụ vào container độc lập; script `run_all.py` là điểm khởi đầu để viết cấu hình Docker Compose hoặc hệ thống điều phối khác.

## 8. Kết luận
Kho mã xây dựng một hệ sinh thái dịch vụ minh họa chuyển tiền bảo mật với zk-SNARK. Thiết kế mô-đun tách bạch logic sinh bằng chứng, xác minh và lưu trữ, tạo nền tảng linh hoạt để nghiên cứu hoặc chuyển giao vào môi trường blockchain thực tế. Việc hỗ trợ cả backend mô phỏng và PySNARK giúp dễ dàng thử nghiệm, đồng thời tạo cơ sở đánh giá hiệu năng và bảo mật của giao thức Groth16 trong bối cảnh chuyển tiền bí mật.
