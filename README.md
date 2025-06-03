# Fridge Maintenance Predictor (Amco-Yam)

מערכת תחזוקה מונעת למקררים תעשייתיים. האתר מאפשר למשתמש:
- להעלות שלושה קבצי נתונים (תקלות, כיולים, מקררים)
- לבחור חודש ושנה
- לקבל תחזית תקלות לכל קבוצת מקררים
- לצפות בגרף מגמה ובמדדי ביצועים (MAE)

### פריסה על Render:
1. העלה את הקוד ל-GitHub (עם כל הקבצים מהתיקייה)
2. התחבר ל-Render.com → לחץ New Web Service
3. בחר את הריפוזיטורי
4. הגדר:
   - Build Command: pip install -r requirements.txt
   - Start Command: python app.py
   - Environment: Python 3
5. לחץ Deploy