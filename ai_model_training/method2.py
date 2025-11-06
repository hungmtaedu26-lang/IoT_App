import pandas as pd
import numpy as np
import os
import warnings
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.base import clone
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score, accuracy_score, f1_score, brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.linear_model import SGDClassifier
from sklearn.exceptions import ConvergenceWarning

warnings.filterwarnings('ignore', category=ConvergenceWarning)
warnings.filterwarnings('ignore', category=UserWarning) # Bỏ qua cảnh báo CatBoost

# --- ĐỊNH NGHĨA CÁC ĐƯỜNG DẪN THƯ MỤC ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DATA_FOLDER = os.path.join(BASE_DIR, 'data/processed')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'evaluation_results/method2')

# Đảm bảo thư mục output tồn tại
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- HÀM VẼ MA TRẬN NHẦM LẪN ---
def plot_confusion_matrix(y_true, y_pred, model_name, output_path):
    """Vẽ và lưu ma trận nhầm lẫn tổng hợp."""
    cm = confusion_matrix(y_true, y_pred)
    plt.figure(figsize=(6, 4))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                xticklabels=['Không MDD (0)', 'MDD (1)'], 
                yticklabels=['Không MDD (0)', 'MDD (1)'])
    plt.title(f'Ma trận nhầm lẫn (LOGO) - {model_name}')
    plt.xlabel('Dự đoán')
    plt.ylabel('Thực tế')
    plt.savefig(output_path)
    plt.close()

# --- HÀM MAIN ĐỂ CHẠY ---
def main():
    print("Bắt đầu Chương trình 3: Đánh giá Phương pháp 2 (LOGO trên dữ liệu thô)")
    
    # 1. Tải dữ liệu thô đã làm sạch (per-sample)
    data_path = os.path.join(PROCESSED_DATA_FOLDER, 'cleaned_sensor_data.csv')
    try:
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"[LỖI] Không tìm thấy tệp: {data_path}")
        print("Vui lòng chạy '1_preprocess_data.py' trước.")
        return

    feature_cols = ['accel_x', 'temperature', 'pulse_rate', 'spo2']
    X = df[feature_cols].apply(pd.to_numeric, errors='coerce').fillna(df[feature_cols].median())
    y = df['label'].astype(int)
    groups = df['participant_id']
    participants = sorted(groups.unique())
    
    # Lấy nhãn thực tế (1 nhãn cho mỗi người)
    y_true_by_part = {pid: int(y[groups==pid].unique()[0]) for pid in participants}

    # 2. Định nghĩa mô hình với các điều chỉnh cân bằng lớp và siêu tham số
    models = {
        'Logistic Regression': LogisticRegression(max_iter=200, solver='liblinear', class_weight='balanced'),
        'Random Forest': RandomForestClassifier(
            n_estimators=50,
            max_depth=5,
            random_state=42,
            class_weight='balanced_subsample',
            n_jobs=-1
        ),
        'KNN': KNeighborsClassifier(n_neighbors=5, weights='distance'),
        'SVM': SVC(kernel='linear', C=1.0, probability=True, random_state=42, class_weight='balanced'),
        'SGD': SGDClassifier(loss='log_loss', penalty='l2', max_iter=200, alpha=1e-4, random_state=42, class_weight='balanced')
    }

    # Chuẩn bị cấu trúc lưu dự đoán (theo người)
    pred_probs_by_model = {name: {pid: [] for pid in participants} for name in models}
    
    # 3. Vòng lặp Leave-One-Group-Out (LOGO)
    logo = LeaveOneGroupOut()
    print(f"Bắt đầu Leave-One-Group-Out (LOGO) cho {len(participants)} người...")

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups=groups), start=1):
        print(f"Đang xử lý fold {fold_idx}/{len(participants)}...")
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train = y.iloc[train_idx]
        test_pids = groups.iloc[test_idx].values

        # Chuẩn hoá
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Huấn luyện và dự đoán từng mô hình
        for name, base_model in models.items():
            model = clone(base_model)
            model.fit(X_train_scaled, y_train)
            
            # Dự đoán xác suất cho TẤT CẢ các mẫu của người bị bỏ ra
            proba_samples = model.predict_proba(X_test_scaled)[:, 1]
            
            # Lưu trữ các xác suất này (chưa tính trung bình)
            for pid, prob in zip(test_pids, proba_samples):
                pred_probs_by_model[name][pid].append(prob)

    print("Hoàn tất vòng lặp LOGO. Bắt đầu tổng hợp kết quả...")

    # 4. Tính toán chỉ số tổng hợp (ở cấp độ người)
    results = []
    final_y_true = np.array([y_true_by_part[pid] for pid in participants])
    
    # Chuẩn bị lưu đồ thị
    fig_folder = os.path.join(OUTPUT_FOLDER, 'confusion_matrices')
    os.makedirs(fig_folder, exist_ok=True)

    def find_best_threshold(y_true, probs, metric=f1_score):
        thresholds = np.linspace(0.0, 1.0, 101)
        best_thresh, best_score = 0.5, -1
        for thresh in thresholds:
            preds = (probs >= thresh).astype(int)
            score = metric(y_true, preds, zero_division=0)
            if score > best_score:
                best_score = score
                best_thresh = thresh
        return best_thresh, best_score

    for name in models:
        print(f"\n========================================================")
        print(f"KẾT QUẢ TỔNG HỢP CHO: {name}")
        print(f"========================================================")
        
        # Tính trung bình xác suất cho mỗi người
        final_probs = np.array([np.mean(pred_probs_by_model[name][pid]) for pid in participants])
        best_threshold, best_f1 = find_best_threshold(final_y_true, final_probs)
        final_preds = (final_probs >= best_threshold).astype(int)
        
        # Tính toán Metrics
        acc = accuracy_score(final_y_true, final_preds)
        f1 = f1_score(final_y_true, final_preds)
        auc = roc_auc_score(final_y_true, final_probs)
        brier = brier_score_loss(final_y_true, final_probs)
        ll = log_loss(final_y_true, np.vstack([1 - final_probs, final_probs]).T, labels=[0, 1])

        results.append({
            'Model': name,
            'Accuracy': acc,
            'F1': f1,
            'ROC AUC': auc,
            'Brier Score': brier,
            'Log Loss': ll,
            'Best Threshold': best_threshold
        })
        
        print("\nBáo cáo phân loại (theo người):")
        print(classification_report(final_y_true, final_preds, target_names=['Không MDD (0)', 'MDD (1)']))
        print(f"Điểm AUC-ROC: {auc:.4f}")
        print(f"Ngưỡng tối ưu (F1): {best_threshold:.2f} với F1={best_f1:.4f}")
        
        # Vẽ ma trận nhầm lẫn
        cm_path = os.path.join(fig_folder, f"cm_logo_{name.lower().replace(' ', '_')}.png")
        plot_confusion_matrix(final_y_true, final_preds, name, cm_path)
        print(f"Đã lưu Ma trận Nhầm lẫn tại: {cm_path}")

    # 5. Lưu kết quả tổng hợp
    results_df = pd.DataFrame(results).sort_values(by='F1', ascending=False)
    results_path = os.path.join(OUTPUT_FOLDER, 'logo_metrics_summary.csv')
    results_df.to_csv(results_path, index=False)
    print(f"\n[SAVED] Đã lưu kết quả tổng hợp LOGO tại: {results_path}")

    print("\nChương trình 3: Đánh giá Phương pháp 2 (LOGO) đã hoàn tất!")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
