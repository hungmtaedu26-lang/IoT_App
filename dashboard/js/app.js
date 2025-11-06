// === PHẦN 1: CẤU HÌNH VÀ KHỞI TẠO BAN ĐẦU ===

// 1. Cấu hình kết nối (QUAN TRỌNG: Sửa lại cho đúng với hệ thống của bạn)
const MQTT_BROKER_HOST = 'localhost';
const MQTT_BROKER_PORT = 8883; // Cổng WebSockets mặc định của HiveMQ
const API_BASE_URL = 'http://localhost:8883'; // Địa chỉ API Server FastAPI
const TARGET_MAC_ADDRESS = '90:15:06:D7:36:D4'; // <--- THAY ĐỊA CHỈ MAC CỦA BẠN VÀO ĐÂY

// 2. Lấy các element từ HTML để cập nhật sau này
const domElements = {
    pulse: document.querySelector('.vital-card:nth-child(1) .value'),
    spo2: document.querySelector('.vital-card:nth-child(2) .value'),
    temp: document.querySelector('.vital-card:nth-child(3) .value'),
    activity: document.querySelector('.vital-card:nth-child(4) .value'),
    gauge: document.querySelector('.gauge'),
    gaugeValue: document.querySelector('.gauge-value'),
    riskText: document.querySelector('.risk-text'),
    riskLogList: document.querySelector('.risk-log ul'),
    statusChip: document.querySelector('.status-chip.live span')
};

// 3. Tạo các element <canvas> cho biểu đồ (vì file HTML hiện chỉ có thẻ div rỗng)
function injectCanvases() {
    document.querySelector('.chart-body.pulse').innerHTML = '<canvas id="pulseChartCanvas"></canvas>';
    document.querySelector('.chart-body.temp').innerHTML = '<canvas id="tempChartCanvas"></canvas>';
    document.querySelector('.chart-body.accel').innerHTML = '<canvas id="accelChartCanvas"></canvas>';
    document.querySelector('.chart-body.history-risk').innerHTML = '<canvas id="historyRiskChartCanvas"></canvas>';
    document.querySelector('.chart-body.history-correlation').innerHTML = '<canvas id="historyCorrChartCanvas"></canvas>';
}

// Gọi ngay hàm tạo canvas
injectCanvases();

// Biến lưu trữ các đối tượng biểu đồ
let charts = {};

// === PHẦN 2: KHỞI TẠO CÁC BIỂU ĐỒ (CHART.JS) ===

function initializeCharts() {
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // Tắt animation để real-time mượt hơn
        scales: {
            x: { display: false }, // Ẩn trục X cho gọn
            y: { grid: { color: 'rgba(255, 255, 255, 0.1)' } }
        },
        plugins: { legend: { display: false } }
    };

    // 1. Biểu đồ Nhịp tim (Pulse) Real-time
    charts.pulse = new Chart(document.getElementById('pulseChartCanvas'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'BPM',
                data: [],
                borderColor: '#3dd598', // Màu xanh lá
                borderWidth: 3,
                tension: 0.4, // Làm mượt đường cong
                pointRadius: 0
            }]
        },
        options: { ...commonOptions, scales: { y: { min: 40, max: 150 } } }
    });

    // 2. Biểu đồ Nhiệt độ (Temp) Mini
    charts.temp = new Chart(document.getElementById('tempChartCanvas'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Temp (°C)',
                data: [],
                borderColor: '#ff9f43', // Màu cam
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.4,
                fill: true,
                backgroundColor: 'rgba(255, 159, 67, 0.1)'
            }]
        },
        options: commonOptions
    });

    // 3. Biểu đồ Gia tốc (Accel) Mini
    charts.accel = new Chart(document.getElementById('accelChartCanvas'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Accel X',
                data: [],
                borderColor: '#54a0ff', // Màu xanh dương
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.4
            }]
        },
        options: commonOptions
    });

    console.log("Đã khởi tạo xong 3 biểu đồ real-time.");
}


// === PHẦN 3: KẾT NỐI MQTT ===

const mqttClient = new Paho.MQTT.Client(MQTT_BROKER_HOST, MQTT_BROKER_PORT, "web_client_" + new Date().getTime());

// Thiết lập các sự kiện
mqttClient.onConnectionLost = onConnectionLost;
mqttClient.onMessageArrived = onMessageArrived;

function connectMqtt() {
    domElements.statusChip.textContent = 'Connecting...';
    console.log("Đang kết nối MQTT...");
    mqttClient.connect({
        onSuccess: onConnectSuccess,
        onFailure: onConnectFailure,
        keepAliveInterval: 30,
        useSSL: false // Đặt là false nếu chạy local không có SSL
    });
}

function onConnectSuccess() {
    console.log("Kết nối MQTT thành công!");
    domElements.statusChip.textContent = 'Connected';
    
    // Đăng ký nhận tin nhắn từ 2 topic
    mqttClient.subscribe(`sensors/raw/${TARGET_MAC_ADDRESS}`);
    mqttClient.subscribe(`sensors/predictions/${TARGET_MAC_ADDRESS}`);
}

function onConnectFailure(response) {
    console.log("Kết nối MQTT thất bại: " + response.errorMessage);
    domElements.statusChip.textContent = 'Failed (Retrying...)';
    setTimeout(connectMqtt, 5000); // Thử lại sau 5s
}

function onConnectionLost(response) {
    if (response.errorCode !== 0) {
        console.log("Mất kết nối MQTT: " + response.errorMessage);
        domElements.statusChip.textContent = 'Disconnected';
        setTimeout(connectMqtt, 5000);
    }
}

function onMessageArrived(message) {
    const topic = message.destinationName;
    const payloadStr = message.payloadString;
    try {
        const data = JSON.parse(payloadStr);
        console.log(`[${topic}] Dữ liệu mới:`, data);

        // Phân luồng xử lý dựa trên tên topic
        if (topic.includes('sensors/raw')) {
            updateRealtimeUI(data);
        } else if (topic.includes('sensors/predictions')) {
            updatePredictionUI(data);
        }
    } catch (e) {
        console.error("Lỗi parse JSON từ MQTT:", e);
    }
}

// === PHẦN 4: CẬP NHẬT GIAO DIỆN (UI) ===

function updateRealtimeUI(data) {
    // 1. Cập nhật các con số (Vitals)
    domElements.pulse.innerHTML = `${data.bpm || '--'} <span>BPM</span>`;
    domElements.spo2.innerHTML = `${data.spo2 || '--'} <span>%</span>`;
    domElements.temp.innerHTML = `${data.temp ? data.temp.toFixed(1) : '--'} <span>°C</span>`;
    
    // Đánh giá mức vận động dựa trên ax_g
    let activityText = 'VẬN ĐỘNG THẤP';
    if (Math.abs(data.ax_g) > 1.5) activityText = 'VẬN ĐỘNG CAO';
    else if (Math.abs(data.ax_g) > 0.8) activityText = 'VẬN ĐỘNG NHẸ';
    domElements.activity.textContent = activityText;

    // 2. Cập nhật biểu đồ (thêm điểm mới, xóa điểm cũ)
    const nowLabel = new Date().toLocaleTimeString();
    addDataToChart(charts.pulse, nowLabel, data.bpm);
    addDataToChart(charts.temp, nowLabel, data.temp);
    addDataToChart(charts.accel, nowLabel, data.ax_g);
}

// Hàm phụ trợ để thêm dữ liệu vào biểu đồ và giữ lại tối đa 30 điểm
function addDataToChart(chart, label, newData) {
    chart.data.labels.push(label);
    chart.data.datasets[0].data.push(newData);
    
    if (chart.data.labels.length > 30) {
        chart.data.labels.shift(); // Xóa điểm đầu tiên
        chart.data.datasets[0].data.shift();
    }
    chart.update(); // Vẽ lại biểu đồ
}

function updatePredictionUI(data) {
    // Giả sử data.prediction là một con số từ 0 (bình thường) đến 1 (nguy hiểm)
    // Nếu API trả về "Bình thường", "Bất thường", ta cần chuyển đổi
    let score = data.prediction === 'Bất thường' ? 80 : 20; // Ví dụ đơn giản
    if (typeof data.prediction === 'number') {
        score = data.prediction * 100; // Nếu là xác suất 0.0 - 1.0
    }

    // Cập nhật đồng hồ gauge
    domElements.gauge.style.setProperty('--value', score);
    domElements.gaugeValue.textContent = `${Math.round(score)}%`;

    // Cập nhật văn bản kết luận
    if (score > 70) {
        domElements.riskText.textContent = 'KẾT LUẬN: NGUY CƠ CAO (MDD)';
        domElements.riskText.className = 'risk-text high';
        addLogEntry(score, 'danger');
    } else if (score > 40) {
        domElements.riskText.textContent = 'KẾT LUẬN: NGUY CƠ TRUNG BÌNH';
        domElements.riskText.className = 'risk-text medium'; // Cần thêm CSS cho class này
        addLogEntry(score, 'warning');
    } else {
        domElements.riskText.textContent = 'KẾT LUẬN: NGUY CƠ THẤP';
        domElements.riskText.className = 'risk-text low'; // Cần thêm CSS cho class này
    }
}

// Hàm thêm nhật ký
function addLogEntry(score, level) {
    const li = document.createElement('li');
    li.className = `log-entry ${level}`;
    const timeStr = new Date().toLocaleTimeString();
    
    let icon = '✓';
    if (level === 'danger') icon = '!';
    if (level === 'warning') icon = 'i';
    
    li.innerHTML = `
        <span class="icon">${icon}</span>
        <div>
            <p class="time">${timeStr} · ${level.toUpperCase()}</p>
            <p>Nguy cơ MDD ${level === 'danger' ? 'tăng cao' : 'ổn định'} (Score: ${Math.round(score)}%)</p>
        </div>
    `;
    
    // Thêm vào đầu danh sách và xóa bớt nếu quá dài
    domElements.riskLogList.prepend(li);
    if (domElements.riskLogList.children.length > 5) {
        domElements.riskLogList.lastChild.remove();
    }
}

// === PHẦN 5: LẤY DỮ LIỆU LỊCH SỬ TỪ API ===

async function fetchHistoryData() {
    console.log("Đang lấy dữ liệu lịch sử...");
    try {
        const response = await fetch(`${API_BASE_URL}/readings/${TARGET_MAC_ADDRESS}?limit=100`);
        if (!response.ok) throw new Error('Lỗi API');
        const dataList = await response.json();
        
        console.log(`Đã nhận ${dataList.length} bản ghi lịch sử.`);
        // Đảo ngược mảng để hiển thị theo thời gian tăng dần
        dataList.reverse();

        // Vẽ biểu đồ lịch sử (ví dụ: biểu đồ BPM lịch sử)
        drawHistoryChart(dataList);

    } catch (error) {
        console.error("Không thể lấy dữ liệu lịch sử:", error);
    }
}

function drawHistoryChart(dataList) {
    // Chuẩn bị dữ liệu
    const labels = dataList.map(d => new Date(d.received_at).toLocaleTimeString());
    const bpmData = dataList.map(d => d.bpm);

    // Khởi tạo biểu đồ lịch sử (nếu chưa có)
    if (!charts.historyRisk) {
        charts.historyRisk = new Chart(document.getElementById('historyRiskChartCanvas'), {
            type: 'bar', // Thử biểu đồ cột
            data: {
                labels: labels,
                datasets: [{
                    label: 'Nhịp tim (BPM) Lịch sử',
                    data: bpmData,
                    backgroundColor: 'rgba(61, 213, 152, 0.5)',
                    borderColor: '#3dd598',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: false } },
                plugins: { legend: { display: false } }
            }
        });
    } else {
        // Nếu đã có thì cập nhật data
        charts.historyRisk.data.labels = labels;
        charts.historyRisk.data.datasets[0].data = bpmData;
        charts.historyRisk.update();
    }
}

// === PHẦN 6: KHỞI CHẠY ===

document.addEventListener('DOMContentLoaded', () => {
    console.log("Ứng dụng bắt đầu khởi chạy...");
    initializeCharts(); // Tạo khung biểu đồ
    connectMqtt();      // Kết nối MQTT để nhận dữ liệu real-time
    fetchHistoryData(); // Gọi API lấy dữ liệu cũ
});