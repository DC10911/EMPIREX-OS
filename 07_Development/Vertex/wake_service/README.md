# שירות ה-Wake Word של Vertex — "היי וורטקס"

שירות זה **לא יעבוד "מהקופסה"** ללא שלב אימון קצר, כי מילת ההפעלה מותאמת
אישית לקול שלך (לא מודל גנרי) — בדיוק כפי שהמפרט ההנדסי דורש (§2.2),
כדי למנוע הפעלות שווא ולשמור על פרטיות (שום אודיו לא נשלח לרשת).

## שלבי האימון (חד-פעמי, כ-20 דקות)

1. **הקלטת דוגמאות חיוביות** — אתה אומר "היי וורטקס" בגוונים/מרחקים שונים:
   ```
   python record_samples.py --label positive --count 50
   ```
2. **הקלטת דוגמאות שליליות** — דיבור רגיל, טלוויזיה, מוזיקה (כדי למנוע
   false triggers):
   ```
   python record_samples.py --label negative --count 200
   ```
3. **אימון מודל openWakeWord** קל-משקל (ONNX, <5MB):
   ```
   python -m openwakeword.train \
       --positive-dir training_samples/positive \
       --negative-dir training_samples/negative \
       --output models/hey_vertex.onnx
   ```
   (הפקודה המדויקת עשויה להשתנות בין גרסאות openwakeword — ר' התיעוד
   הרשמי של הספרייה בזמן ההטמעה.)
4. **כיול סף רגישות** בקובץ `config.yaml` (`wake_word_threshold`) — יעד:
   False Accept < 1 ל-24 שעות, False Reject < 5%.

## הרצה

```
python listener.py
```

השירות ירוץ ברקע (מותקן כ-Scheduled Task ע"י המתקין הראשי, ר'
`scripts/install_windows.ps1`) ויאזין באופן רציף ברמת עומס נמוכה
(<3% ליבת CPU בודדת). ללא "היי וורטקס" בתחילת המשפט — Vertex לא נפתח
ולא מגיב, בדיוק כפי שהוגדר במפרט.
