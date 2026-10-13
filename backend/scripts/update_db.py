from app.admin.models import SystemSetting
from app.database import SessionLocal

db = SessionLocal()
updates = db.query(SystemSetting).filter(
    SystemSetting.value.in_([
        'meta-llama/llama-4-scout-17b-16e-instruct',
        'meta-llama/llama-4-maverick-17b-128e-instruct'
    ])
).all()

for u in updates:
    u.value = 'llama-3.2-11b-vision-preview'
    print(f"Updated setting {u.category}.{u.key}")

db.commit()
db.close()
