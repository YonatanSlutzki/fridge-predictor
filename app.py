from flask import Flask, request, render_template
import pandas as pd
import os
from werkzeug.utils import secure_filename
import joblib
import matplotlib.pyplot as plt

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['STATIC_FOLDER'] = 'static'

model = joblib.load('model_rf.pkl')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    target_year = int(request.form.get('target_year'))
    target_month = int(request.form.get('target_month'))

    service_file = request.files.get('service_file')
    calibration_file = request.files.get('calibration_file')
    fridge_file = request.files.get('fridge_file')

    files = [service_file, calibration_file, fridge_file]
    dfs = []

    for file in files:
        if file and file.filename.endswith('.xlsx'):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            df = pd.read_excel(file_path)
            dfs.append(df)
        else:
            return "יש להעלות קבצים בפורמט Excel בלבד (.xlsx)"

    try:
        df_service, df_calibration, df_fridges = dfs

        df_service = df_service.rename(columns={'שם לקוח ': 'שם מרפאה', 'תאריך קלקול': 'תאריך'})
        df_service['שעת סיום'] = pd.NA
        df_service['תלונת לקוח'] = pd.NA

        df_merged = df_service.merge(df_calibration, on='מקרר', how='left')
        df_merged = df_merged.merge(df_fridges, on='מקרר', how='left')

        df_merged['הערות'] = df_merged.get('הערות', pd.NA)

        df = df_merged
        df['תאריך'] = pd.to_datetime(df['תאריך'], errors='coerce')
        df['תאריך כיול'] = pd.to_datetime(df['תאריך כיול'], errors='coerce')
        df['Days_Since_Last_Calibration'] = (df['תאריך'] - df['תאריך כיול']).dt.days
        df = df[df['Days_Since_Last_Calibration'] >= 0]

        temp_keywords = ['טמפ', 'טמפרטורה', 'חריג', 'גבוהה']
        df['Temp_Failure_Indicator'] = df.apply(
            lambda row: int(any(kw in str(row.get('מהות הקריאה', '')) or kw in str(row.get('הערות', '')) for kw in temp_keywords)),
            axis=1
        )

        df['is_EVCO'] = (
            df['עבודה שבוצעה'].fillna('').str.contains('EVCO', case=False) |
            df['חלקי חילוף'].fillna('').str.contains('EVCO', case=False) |
            df['הערות'].fillna('').str.contains('EVCO', case=False)
        )

        df['Year-Month'] = df['תאריך'].dt.to_period('M').dt.to_timestamp()
        evco = df[(df['is_EVCO']) & (df['עבודה שבוצעה'].notna())]

        monthly = evco.groupby('Year-Month').agg({
            'Days_Since_Last_Calibration': 'mean',
            'Temp_Failure_Indicator': 'sum'
        })
        monthly['EVCO_Failures_Total'] = evco.groupby('Year-Month').size()
        monthly = monthly.sort_index().reset_index()
        monthly['month'] = monthly['Year-Month'].dt.month
        monthly['year'] = monthly['Year-Month'].dt.year
        monthly['trend'] = range(len(monthly))

        history = monthly[
            (monthly['year'] < target_year) |
            ((monthly['year'] == target_year) & (monthly['month'] <= target_month))
        ]
        if history.empty:
            return f"<h3>לא נמצאו נתונים עבור {target_month}/{target_year}</h3>"

        X_hist = history[['Days_Since_Last_Calibration', 'Temp_Failure_Indicator', 'month', 'trend']]
        y_true_hist = history['EVCO_Failures_Total']
        y_pred_hist = model.predict(X_hist)

        # גרף באנגלית
        plt.figure(figsize=(8, 5))
        plt.plot(history['Year-Month'], y_true_hist, label='Actual', color='blue', marker='o')
        plt.plot(history['Year-Month'], y_pred_hist, label='Forecast', color='red', linestyle='--', marker='x')
        plt.title('Monthly Failure Trend and Forecast', fontsize=14)
        plt.xlabel('Month')
        plt.ylabel('Number of Failures')
        plt.xticks(rotation=45, ha='right')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        chart_path = os.path.join(app.config['STATIC_FOLDER'], 'forecast_chart.png')
        plt.savefig(chart_path)
        plt.close()

        group_criteria = {
            'עומס גבוה': lambda row: row['Days_Since_Last_Calibration'] > 150 and row['Temp_Failure_Indicator'] >= 5,
            'מקרר חדש': lambda row: row['Days_Since_Last_Calibration'] <= 20 and row['Temp_Failure_Indicator'] == 0,
            'מגמה עולה': lambda row: row['trend'] >= 25,
            'שקט עם מגמה עולה': lambda row: row['Temp_Failure_Indicator'] == 0 and row['trend'] >= 25,
            'ירידה אחרי טיפול': lambda row: row['Temp_Failure_Indicator'] <= 1 and row['Days_Since_Last_Calibration'] <= 40,
        }
        group_counts = {}
        for name, func in group_criteria.items():
            group_counts[name] = int(history.apply(func, axis=1).sum())

        table_html = "<table style='width:80%; margin: 30px auto; border-collapse: collapse; font-size: 15px;'>"
        table_html += "<tr style='background-color:#f5f5f5;'><th style='padding:10px; border:1px solid #ccc;'>קבוצה</th><th style='padding:10px; border:1px solid #ccc;'>מספר תקלות חזוי</th></tr>"
        for k, v in group_counts.items():
            table_html += f"<tr><td style='padding:10px; border:1px solid #ccc;'>{k}</td><td style='padding:10px; border:1px solid #ccc;'>{v}</td></tr>"
        table_html += "</table>"

        final_pred = y_pred_hist[-1]
        final_true = y_true_hist.values[-1]
        mae = abs(final_pred - final_true)

        return f'''
        <div style="background-color:#e6f0fa; padding:40px; font-family: 'Roboto', sans-serif;">
            <div style="max-width:800px; margin:auto; background:#fff; padding:30px; border-radius:10px;">
                <h2 style="text-align:center; color:#004F7A; font-family: 'Montserrat', sans-serif;">
                    תוצאות ניתוח תחזוקה מונעת עבור {target_month}/{target_year}
                </h2>
                <p style="text-align:center; font-size:22px; color:#b30000; font-weight:bold;">
                    מספר תקלות חזוי: {final_pred:.2f}
                </p>
                <p style="text-align:center; font-size:16px;">רמת דיוק (MAE): {mae:.2f}</p>
                <img src="/static/forecast_chart.png" style="display:block; margin: 30px auto; width:100%; max-width:700px;">
                <p style="text-align:center; margin-top:10px; color:#333; font-size:15px;">
                    גרף זה מציג את מגמת התקלות ההיסטורית ואת התחזית עבור החודשים שנבחרו.
                </p>
                <h3 style="text-align:center; color:#004F7A;">סיכום תחזית לפי קבוצות:</h3>
                {table_html}
                <div style="text-align:center; margin-top:30px;">
                    <a href="/" style="text-decoration:none; color:white; background-color:#1E90FF;
                    padding:10px 20px; border-radius:6px;">חזרה לעמוד הבית</a>
                </div>
            </div>
        </div>
        '''

    except Exception as e:
        return f"שגיאה: {str(e)}"

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(host='0.0.0.0', port=10000)

