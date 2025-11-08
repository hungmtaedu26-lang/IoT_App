
// === PHẦN 1: CẤU HÌNH VÀ KHỞI TẠO BAN ĐẦU ===

// 1. Cấu hình kết nối (QUAN TRỌNG: Sửa lại cho đúng với hệ thống của bạn)
const HOSTNAME = window.location.hostname || 'localhost';
const CONFIG_STORAGE_KEY = 'iotDashboard.config';
const DEFAULT_CONFIG = {
    mqttHost: HOSTNAME,
    mqttPort: 9002,
    mqttPath: '/mqtt',
    useTls: false,
    apiHost: HOSTNAME,
    apiPort: 8000,
    apiProtocol: 'http',
    defaultMac: '90:15:06:D7:36:D4'
};

function loadRuntimeConfig() {
    let stored = {};
    try {
        stored = JSON.parse(localStorage.getItem(CONFIG_STORAGE_KEY)) || {};
    } catch (err) {
        console.warn("Không thể đọc config từ localStorage:", err);
    }

    const urlParams = new URLSearchParams(window.location.search);
    const overrides = {};
    ['mqttHost', 'mqttPort', 'mqttPath', 'apiHost', 'apiPort', 'apiProtocol', 'useTls', 'defaultMac'].forEach((key) => {
        if (urlParams.has(key)) {
            overrides[key] = urlParams.get(key);
        }
    });

    const config = { ...DEFAULT_CONFIG, ...stored, ...overrides };
    config.mqttPort = Number(config.mqttPort) || DEFAULT_CONFIG.mqttPort;
    config.apiPort = Number(config.apiPort) || DEFAULT_CONFIG.apiPort;
    config.useTls = typeof config.useTls === 'string' ? config.useTls === 'true' : !!config.useTls;
    config.mqttPath = config.mqttPath || DEFAULT_CONFIG.mqttPath;
    config.apiProtocol = config.apiProtocol || DEFAULT_CONFIG.apiProtocol;
    config.defaultMac = config.defaultMac || DEFAULT_CONFIG.defaultMac;

    if (Object.keys(overrides).length) {
        localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
    }

    return config;
}

const runtimeConfig = loadRuntimeConfig();

const MQTT_BROKER_HOST = runtimeConfig.mqttHost;
const MQTT_BROKER_PORT = runtimeConfig.mqttPort;
const MQTT_BROKER_PATH = runtimeConfig.mqttPath || '/mqtt';
const USE_MQTT_TLS = runtimeConfig.useTls;
const API_BASE_URL = `${runtimeConfig.apiProtocol || 'http'}://${runtimeConfig.apiHost}:${runtimeConfig.apiPort}`;
const DEFAULT_MAC_ADDRESS = runtimeConfig.defaultMac;

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
    statusChip: document.querySelector('.status-chip.live span'),
    deviceSelect: document.getElementById('deviceSelect'),
    refreshDevicesBtn: document.getElementById('refreshDevicesBtn'),
    currentDeviceLabel: document.getElementById('currentDeviceLabel'),
    configBtn: document.getElementById('configBtn'),
    configPanel: document.getElementById('configPanel'),
    configOverlay: document.getElementById('configOverlay'),
    configCloseBtn: document.getElementById('configCloseBtn'),
    configForm: document.getElementById('configForm'),
    configResetBtn: document.getElementById('configResetBtn')
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
let selectedMac = DEFAULT_MAC_ADDRESS;
let mqttConnected = false;
let currentSubscriptions = { raw: null, ai: null };

if (domElements.deviceSelect) {
    domElements.deviceSelect.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value) {
            handleDeviceChange(value);
        }
    });
}

if (domElements.refreshDevicesBtn) {
    domElements.refreshDevicesBtn.addEventListener('click', () => {
        loadDevices(true);
    });
}

if (domElements.configBtn && domElements.configPanel && domElements.configOverlay) {
    domElements.configBtn.addEventListener('click', openConfigPanel);
    domElements.configOverlay.addEventListener('click', closeConfigPanel);
}

if (domElements.configCloseBtn) {
    domElements.configCloseBtn.addEventListener('click', closeConfigPanel);
}

if (domElements.configForm) {
    domElements.configForm.addEventListener('submit', handleConfigSubmit);
}

if (domElements.configResetBtn) {
    domElements.configResetBtn.addEventListener('click', () => {
        localStorage.removeItem(CONFIG_STORAGE_KEY);
        window.location.reload();
    });
}

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

const mqttClient = new Paho.Client(
    MQTT_BROKER_HOST,
    Number(MQTT_BROKER_PORT),
    MQTT_BROKER_PATH || '/mqtt',
    "web_client_" + new Date().getTime()
);

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
        useSSL: USE_MQTT_TLS
    });
}

function onConnectSuccess() {
    console.log("Kết nối MQTT thành công!");
    mqttConnected = true;
    domElements.statusChip.textContent = 'Connected';
    subscribeToSelectedTopics();
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
    mqttConnected = false;
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
    if (typeof newData !== 'number') {
        return;
    }
    chart.data.labels.push(label);
    chart.data.datasets[0].data.push(newData);
    
    if (chart.data.labels.length > 30) {
        chart.data.labels.shift(); // Xóa điểm đầu tiên
        chart.data.datasets[0].data.shift();
    }
    chart.update(); // Vẽ lại biểu đồ
}

function openConfigPanel() {
    if (!domElements.configPanel || !domElements.configOverlay) return;
    populateConfigForm();
    domElements.configPanel.classList.remove('hidden');
    domElements.configOverlay.classList.remove('hidden');
}

function closeConfigPanel() {
    if (!domElements.configPanel || !domElements.configOverlay) return;
    domElements.configPanel.classList.add('hidden');
    domElements.configOverlay.classList.add('hidden');
}

function populateConfigForm() {
    if (!domElements.configForm) return;
    domElements.configForm.elements['mqttHost'].value = runtimeConfig.mqttHost || '';
    domElements.configForm.elements['mqttPort'].value = runtimeConfig.mqttPort || '';
    domElements.configForm.elements['mqttPath'].value = runtimeConfig.mqttPath || '';
    domElements.configForm.elements['useTls'].checked = !!runtimeConfig.useTls;
    domElements.configForm.elements['apiHost'].value = runtimeConfig.apiHost || '';
    domElements.configForm.elements['apiPort'].value = runtimeConfig.apiPort || '';
    domElements.configForm.elements['defaultMac'].value = runtimeConfig.defaultMac || '';
}

function handleConfigSubmit(event) {
    event.preventDefault();
    if (!domElements.configForm) return;
    const form = domElements.configForm;
    const updatedConfig = {
        ...runtimeConfig,
        mqttHost: form.elements['mqttHost'].value.trim() || runtimeConfig.mqttHost,
        mqttPort: Number(form.elements['mqttPort'].value) || runtimeConfig.mqttPort,
        mqttPath: form.elements['mqttPath'].value.trim() || '/mqtt',
        useTls: form.elements['useTls'].checked,
        apiHost: form.elements['apiHost'].value.trim() || runtimeConfig.apiHost,
        apiPort: Number(form.elements['apiPort'].value) || runtimeConfig.apiPort,
        defaultMac: form.elements['defaultMac'].value.trim() || runtimeConfig.defaultMac
    };

    localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(updatedConfig));
    closeConfigPanel();
    window.location.reload();
}

async function loadDevices(forceRefresh = false) {
    if (!domElements.deviceSelect) return;
    const previousMac = selectedMac;
    domElements.deviceSelect.disabled = true;
    domElements.deviceSelect.innerHTML = '<option value="">Đang tải...</option>';
    try {
        const response = await fetch(`${API_BASE_URL}/devices`);
        if (!response.ok) throw new Error('Không thể lấy danh sách thiết bị');
        const devices = await response.json();

        if (!Array.isArray(devices) || devices.length === 0) {
            domElements.deviceSelect.innerHTML = '<option value="">Chưa có thiết bị</option>';
            selectedMac = null;
            updateDeviceLabel();
            resetRealtimeState();
            return;
        }

        populateDeviceDropdown(devices);
        const preferredMac = previousMac && devices.includes(previousMac)
            ? previousMac
            : (DEFAULT_MAC_ADDRESS && devices.includes(DEFAULT_MAC_ADDRESS)
                ? DEFAULT_MAC_ADDRESS
                : devices[0]);

        domElements.deviceSelect.value = preferredMac;
        handleDeviceChange(preferredMac, { force: true });
    } catch (error) {
        console.error("Không thể tải danh sách thiết bị:", error);
        domElements.deviceSelect.innerHTML = '<option value="">Không thể tải danh sách</option>';
        updateDeviceLabel();
        if (forceRefresh && selectedMac) {
            handleDeviceChange(selectedMac, { force: true });
        }
    } finally {
        domElements.deviceSelect.disabled = false;
    }
}

function populateDeviceDropdown(devices) {
    if (!domElements.deviceSelect) return;
    domElements.deviceSelect.innerHTML = devices
        .map(mac => `<option value="${mac}">${mac}</option>`)
        .join('');
}

function handleDeviceChange(mac, { force = false } = {}) {
    if (!mac) return;
    if (selectedMac === mac && !force) {
        fetchHistoryData();
        return;
    }
    selectedMac = mac;
    updateDeviceLabel();
    resetRealtimeState();
    subscribeToSelectedTopics();
    fetchHistoryData();
}

function updateDeviceLabel() {
    if (domElements.currentDeviceLabel) {
        domElements.currentDeviceLabel.textContent = selectedMac || '--';
    }
    if (domElements.deviceSelect && selectedMac) {
        domElements.deviceSelect.value = selectedMac;
    }
}

function resetRealtimeState() {
    if (domElements.pulse) domElements.pulse.innerHTML = `-- <span>BPM</span>`;
    if (domElements.spo2) domElements.spo2.innerHTML = `-- <span>%</span>`;
    if (domElements.temp) domElements.temp.innerHTML = `-- <span>°C</span>`;
    if (domElements.activity) domElements.activity.textContent = 'ĐANG CHỜ DỮ LIỆU';

    if (charts.pulse) {
        charts.pulse.data.labels = [];
        charts.pulse.data.datasets[0].data = [];
        charts.pulse.update();
    }
    if (charts.temp) {
        charts.temp.data.labels = [];
        charts.temp.data.datasets[0].data = [];
        charts.temp.update();
    }
    if (charts.accel) {
        charts.accel.data.labels = [];
        charts.accel.data.datasets[0].data = [];
        charts.accel.update();
    }
    if (charts.historyRisk) {
        charts.historyRisk.data.labels = [];
        charts.historyRisk.data.datasets[0].data = [];
        charts.historyRisk.update();
    }
}

function subscribeToSelectedTopics() {
    if (!mqttConnected || !selectedMac) return;
    const rawTopic = `sensors/raw/${selectedMac}`;
    const aiTopic = `sensors/predictions/${selectedMac}`;

    try {
        if (currentSubscriptions.raw && currentSubscriptions.raw !== rawTopic) {
            mqttClient.unsubscribe(currentSubscriptions.raw);
        }
        if (currentSubscriptions.ai && currentSubscriptions.ai !== aiTopic) {
            mqttClient.unsubscribe(currentSubscriptions.ai);
        }
    } catch (error) {
        console.warn("Không thể hủy đăng ký topic cũ:", error);
    }

    mqttClient.subscribe(rawTopic);
    mqttClient.subscribe(aiTopic);
    currentSubscriptions = { raw: rawTopic, ai: aiTopic };
}

function updatePredictionUI(data) {
    // Gốc dữ liệu từ AI worker: probability (0 -> an toàn, 1 -> nguy cơ cao)
    let probability = 0;
    if (typeof data.probability === 'number') {
        probability = data.probability;
    } else if (typeof data.prediction === 'number') {
        probability = data.prediction;
    } else if (data.prediction === 'Bất thường') {
        probability = 0.8;
    } else {
        probability = 0.2;
    }
    const score = Math.min(Math.max(probability * 100, 0), 100);

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
    if (!selectedMac) {
        console.warn("Chưa có thiết bị nào được chọn để lấy lịch sử.");
        return;
    }
    console.log("Đang lấy dữ liệu lịch sử...");
    try {
        const response = await fetch(`${API_BASE_URL}/readings/${selectedMac}?limit=100`);
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
    loadDevices();      // Lấy danh sách thiết bị từ API
    connectMqtt();      // Kết nối MQTT để nhận dữ liệu real-time
});
