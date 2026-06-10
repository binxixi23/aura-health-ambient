import os
import pandas as pd
import matplotlib.pyplot as plt

def plot_health_trends(csv_path="data/vitals_history/hrv_seasonal_trends.csv"):
    if not os.path.exists(csv_path):
        print(f"❌ Cannot find log file at {csv_path}. Run main_hub.py first to collect data!")
        return

    # Load data
    df = pd.read_csv(csv_path)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    # Setup plotting windows
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle('⚡ AURA-Health-Ambient Vitals & Weather Analytics', fontsize=14)

    # Plot Heart Rate
    ax1.plot(df['Timestamp'], df['Calculated_BPM'], color='red', marker='o', linestyle='-', linewidth=2)
    ax1.set_ylabel('Heart Rate (BPM)', color='red')
    ax1.grid(True, linestyle='--')

    # Plot HRV (RMSSD)
    ax2.plot(df['Timestamp'], df['HRV_RMSSD_ms'], color='cyan', marker='s', linestyle='-', linewidth=2)
    ax2.set_ylabel('HRV RMSSD (ms)', color='cyan')
    ax2.set_xlabel('Timeline')
    ax2.grid(True, linestyle='--')

    # Accentuate points matching critical atmospheric weather swings
    for idx, row in df.iterrows():
        if row['Cardiac_Risk_Index'] in ['CRITICAL_RISK_WARNING', 'ELEVATED_VULNERABILITY']:
            ax2.annotate('⚠️ Risk Strike', (row['Timestamp'], row['HRV_RMSSD_ms']),
                         textcoords="offset points", xytext=(0,10), ha='center',
                         color='yellow', weight='bold')

    plt.tight_layout()
    print("📊 Generating vital analytics chart... Displaying plot now.")
    plt.show()

if __name__ == "__main__":
    plot_health_trends()
