import pandas as pd
import numpy as np
import os
import glob
import re
from scipy.stats import skew, kurtosis
from sklearn.feature_selection import mutual_info_classif
from scipy.stats import pointbiserialr
import warnings

warnings.filterwarnings('ignore')

# --- ĐỊNH NGHĨA CÁC ĐƯỜNG DẪN THƯ MỤC ---
# Giả định bạn chạy script này từ bên trong thư mục /ai_model_training/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_FOLDER = os.path.join(BASE_DIR, 'data', 'raw')
PROCESSED_DATA_FOLDER = os.path.join(BASE_DIR,'data', 'processed')

# Đảm bảo thư mục processed tồn tại
os.makedirs(PROCESSED_DATA_FOLDER, exist_ok=True)

# --- CELL 1: HỢP NHẤT DỮ LIỆU THÔ ---
def merge_data_robustly(folder_path, output_path):
    """
    Hợp nhất tất cả các tệp CSV từ folder_path và lưu vào output_path.
    """
    print("--- Bắt đầu: 1. Hợp nhất Dữ liệu Thô ---")
    all_files = sorted(glob.glob(os.path.join(folder_path, "*.csv")),
                       key=lambda x: int(re.search(r'(\d+)', os.path.basename(x)).group()))

    if not all_files:
        print(f"[LỖI] Không tìm thấy tệp CSV nào trong: {folder_path}")
        return None

    list_of_dfs = []
    column_names = ['accel_x', 'temperature', 'pulse_rate', 'spo2', 'label']

    for filename in all_files:
        participant_id = os.path.splitext(os.path.basename(filename))[0]
        print(f"Đang xử lý file: {participant_id}")
        try:
            temp_df = pd.read_csv(
                filename,
                header=None,
                usecols=range(5),
                names=column_names
            )
            temp_df['participant_id'] = participant_id
            list_of_dfs.append(temp_df)
        except Exception as e:
            print(f"  -> Cảnh báo: Không thể xử lý file {participant_id}. Lỗi: {e}.")
            continue

    if not list_of_dfs:
        print("Không có file nào được xử lý thành công. Dừng.")
        return None

    merged_df = pd.concat(list_of_dfs, ignore_index=True)
    final_columns = ['participant_id'] + column_names
    merged_df = merged_df[final_columns]
    merged_df['label'] = merged_df.groupby('participant_id')['label'].transform(lambda x: x.ffill().bfill())
    
    merged_df.to_csv(output_path, index=False)
    print(f"--- Hoàn tất: 1. Đã lưu dữ liệu đã gộp vào '{output_path}' ---")
    return merged_df

# --- CELL 2: LÀM SẠCH VÀ ĐIỀN DỮ LIỆU ---
sensor_cols = ['accel_x', 'temperature', 'pulse_rate', 'spo2']

def clean_and_impute_data(df, output_path):
    """
    Làm sạch và điền dữ liệu cảm biến.
    """
    print("\n--- Bắt đầu: 2. Làm sạch và Điền dữ liệu ---")
    df_imputed = df.copy()

    for col in sensor_cols:
        df_imputed[col] = pd.to_numeric(df_imputed[col], errors='coerce')

    print("Lọc các giá trị ngoài ngưỡng sinh lý...")
    df_imputed.loc[:, 'spo2'] = df_imputed['spo2'].apply(lambda x: x if 70 <= x <= 100 else np.nan)
    df_imputed.loc[:, 'pulse_rate'] = df_imputed['pulse_rate'].apply(lambda x: x if 40 <= x <= 220 else np.nan)
    df_imputed.loc[:, 'temperature'] = df_imputed['temperature'].apply(lambda x: x if 30 <= x <= 45 else np.nan)

    for col in sensor_cols:
        df_imputed[col] = df_imputed[col].astype(float)

    def advanced_imputation_and_fill(series):
        series = series.interpolate(method='polynomial', order=2, limit_direction='both')
        series = series.interpolate(method='linear', limit_direction='forward', limit=5)
        series = series.interpolate(method='linear', limit_direction='backward', limit=5)
        series = series.ffill().bfill()
        return series

    print("Thực hiện Nội suy, Ngoại suy...")
    for col in sensor_cols:
        df_imputed[col] = df_imputed.groupby('participant_id')[col].transform(advanced_imputation_and_fill)

    print("Làm sạch cột 'label'...")
    df_imputed['label'] = pd.to_numeric(df_imputed['label'], errors='coerce')
    df_imputed['label'] = df_imputed.groupby('participant_id')['label'].transform(lambda x: x.ffill().bfill())
    df_imputed.dropna(subset=['label'], inplace=True)
    df_imputed['label'] = df_imputed['label'].astype(int)

    print("Xác thực dữ liệu sau khi điền...")
    initial_rows = len(df_imputed)
    df_validated = df_imputed[
        (df_imputed['spo2'] >= 70) & (df_imputed['spo2'] <= 100) &
        (df_imputed['pulse_rate'] >= 30) & (df_imputed['pulse_rate'] <= 220) &
        (df_imputed['temperature'] >= 30) & (df_imputed['temperature'] <= 45)
    ].copy()
    rows_dropped = initial_rows - len(df_validated)
    if rows_dropped > 0:
        print(f"Đã loại bỏ {rows_dropped} hàng không hợp lệ sau khi điền.")

    df_validated.dropna(inplace=True)
    
    df_validated.to_csv(output_path, index=False)
    print(f"--- Hoàn tất: 2. Đã lưu dữ liệu sạch vào '{output_path}' ---")
    return df_validated

# --- CELL 3: TRÍCH XUẤT ĐẶC TRƯNG CƠ BẢN ---
def extract_statistical_features(df, output_path):
    """
    Trích xuất các đặc trưng thống kê cơ bản.
    """
    print("\n--- Bắt đầu: 3. Trích xuất Đặc trưng Thống kê (Cơ bản) ---")
    
    def iqr(x): return x.quantile(0.75) - x.quantile(0.25)
    def range_val(x): return x.max() - x.min()

    statistical_features_list = []
    for col in sensor_cols:
        features = df.groupby('participant_id')[col].agg(
            mean='mean', median='median', std='std', min='min', max='max',
            skew=skew, kurt=kurtosis, range=range_val, iqr=iqr
        ).add_prefix(f'{col}_')
        statistical_features_list.append(features)

    feature_df = pd.concat(statistical_features_list, axis=1)
    labels = df.groupby('participant_id')['label'].first()
    final_df = feature_df.join(labels).reset_index()
    
    final_df.to_csv(output_path, index=False)
    print(f"--- Hoàn tất: 3. Đã lưu bộ đặc trưng cơ bản vào '{output_path}' ---")
    return final_df

# --- CELL 4: TRÍCH XUẤT ĐẶC TRƯNG NÂNG CAO ---
def extract_advanced_features(df, stat_features_df, output_path):
    """
    Trích xuất đặc trưng FFT và Chênh lệch, sau đó gộp vào file stat_features_df.
    """
    print("\n--- Bắt đầu: 4. Trích xuất Đặc trưng Nâng cao (FFT, Diff) ---")
    
    # FFT
    print("Trích xuất FFT...")
    def get_fft_features(series):
        if len(series) < 2: return pd.Series({'fft_mean': np.nan, 'fft_std': np.nan, 'fft_max': np.nan, 'fft_energy': np.nan})
        fft_vals = np.fft.fft(series)
        fft_magnitudes = np.abs(fft_vals[1:len(fft_vals)//2])
        if len(fft_magnitudes) == 0:
             return pd.Series({'fft_mean': np.nan, 'fft_std': np.nan, 'fft_max': np.nan, 'fft_energy': np.nan})
        return pd.Series({'fft_mean': np.mean(fft_magnitudes), 'fft_std': np.std(fft_magnitudes), 'fft_max': np.max(fft_magnitudes), 'fft_energy': np.sum(fft_magnitudes**2)})

    fft_features = df.groupby('participant_id')['accel_x'].apply(get_fft_features).add_prefix('accel_x_')

    # Diff
    print("Trích xuất Diff (thay đổi)...")
    df_diff = df.groupby('participant_id')[sensor_cols].diff().add_suffix('_diff')
    change_features_list = []
    for col in sensor_cols:
        features = df_diff.groupby(df['participant_id'])[f'{col}_diff'].agg(
            mean_diff='mean', std_diff='std'
        ).add_prefix(f'{col}_')
        change_features_list.append(features)
    change_features = pd.concat(change_features_list, axis=1)

    # Gộp tất cả
    # Đặt 'participant_id' làm chỉ mục để join
    final_df = stat_features_df.set_index('participant_id')
    final_df = pd.concat([final_df, fft_features, change_features], axis=1)
    final_df = final_df.drop(columns=['label']).join(df.groupby('participant_id')['label'].first())
    final_df.fillna(0, inplace=True)
    final_df.reset_index(inplace=True)
    
    final_df.to_csv(output_path, index=False)
    print(f"--- Hoàn tất: 4. Đã lưu bộ đặc trưng nâng cao vào '{output_path}' ---")
    return final_df

# --- CELL 5: CHỌN LỌC ĐẶC TRƯNG ---
def select_features(features_df, label_series, output_path, top_n=20):
    """
    Chọn top_n đặc trưng tốt nhất dựa trên Mutual Information và Correlation.
    """
    print(f"\n--- Bắt đầu: 5. Chọn lọc {top_n} Đặc trưng Tốt nhất ---")
    
    X = features_df.drop(columns=['participant_id', 'label']).fillna(0)
    y = label_series
    
    mi_scores = pd.Series(mutual_info_classif(X, y, random_state=42), index=X.columns)
    
    abs_corr = {}
    for col in X.columns:
        corr, _ = pointbiserialr(y, X[col])
        abs_corr[col] = abs(corr)
    corr_scores = pd.Series(abs_corr)
    
    metrics_df = pd.DataFrame({
        'Mutual Information': mi_scores,
        'Abs Correlation': corr_scores
    }).sort_values(by='Mutual Information', ascending=False)
    
    selected_features = metrics_df.head(top_n).index.tolist()
    print(f"Các đặc trưng được chọn: {selected_features}")
    
    new_df = features_df[['participant_id'] + selected_features + ['label']]
    new_df.to_csv(output_path, index=False)
    print(f"--- Hoàn tất: 5. Đã lưu bộ đặc trưng đã chọn lọc vào '{output_path}' ---")
    return new_df

# --- HÀM MAIN ĐỂ CHẠY TOÀN BỘ QUY TRÌNH ---
def main():
    print("Bắt đầu quy trình tiền xử lý và trích xuất đặc trưng...")
    
    # Định nghĩa các đường dẫn tệp
    path_raw_folder = RAW_DATA_FOLDER
    path_merged = os.path.join(PROCESSED_DATA_FOLDER, 'merged_sensor_data.csv')
    path_cleaned = os.path.join(PROCESSED_DATA_FOLDER, 'cleaned_sensor_data.csv')
    path_features_basic = os.path.join(PROCESSED_DATA_FOLDER, 'features.csv')
    path_features_advanced = os.path.join(PROCESSED_DATA_FOLDER, 'features_advanced.csv')
    path_features_selected = os.path.join(PROCESSED_DATA_FOLDER, 'features_selected.csv')

    # Chạy các bước
    merged_df = merge_data_robustly(path_raw_folder, path_merged)
    if merged_df is None:
        return

    cleaned_df = clean_and_impute_data(merged_df, path_cleaned)
    if cleaned_df is None:
        return
        
    features_basic_df = extract_statistical_features(cleaned_df, path_features_basic)
    if features_basic_df is None:
        return

    _ = extract_advanced_features(cleaned_df, features_basic_df.copy(), path_features_advanced)
    
    _ = select_features(features_basic_df.copy(), features_basic_df['label'], path_features_selected, top_n=20)

    print("\nQuy trình tiền xử lý và trích xuất đặc trưng hoàn tất!")

if __name__ == "__main__":
    # Thiết lập thư mục làm việc là thư mục chứa script này
    # Điều này đảm bảo các đường dẫn tương đối (../data) hoạt động chính xác
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()