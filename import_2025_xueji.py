"""
import_2025_xueji.py — 导入 2025 全年学籍异动数据到学籍管理.db
"""
import pandas as pd
import sqlite3, os, re
from datetime import datetime, timedelta

DB_PATH = r"D:\AI实践案例\2026-07-22_AI数据库\学籍管理.db"
BASE = r"./data"

FILES = {
    "2025春": os.path.join(BASE, "2025春学籍异动总表.xlsx"),
    "2025秋": os.path.join(BASE, "2025秋学籍异动总表.xlsx"),
}

TYPE_TO_STATUS = {
    "休学": "休学", "退学": "退学", "复学": "复学",
    "保留学籍": "保留学籍", "应征入伍": "保留学籍",
    "休转退": "退学", "注销学籍": "退学", "改名": None,
}

# 学院名称统一映射（原始数据名 → 数据库标准名）
DEPT_MAP = {
    "汽车与交通学院": "车辆工程学院",
    "数字财贸学院": "财经学院",
}

def serial_to_date(val):
    if pd.isna(val): return None
    s = str(val).strip()
    try:
        # Excel serial number (5 digits)
        n = int(float(s))
        if 45000 < n < 47000:
            d = datetime(1899, 12, 30) + timedelta(days=n)
            return d.strftime("%Y-%m-%d")
    except: pass
    parts = s.replace("-", "/").split()[0].split("/")
    if len(parts) == 3:
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return s

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = OFF")

all_records = [] ; unique_students = {}

for label, filepath in FILES.items():
    print(f"\n读取 {label} ...")
    df = pd.read_excel(filepath, sheet_name=0, dtype=str)
    print(f"  {len(df)} 条记录")
    for _, row in df.iterrows():
        if pd.isna(row.get("学号")): continue
        sid = str(row["学号"]).strip()
        dept = str(row.get("院部", "")).strip() if pd.notna(row.get("院部")) else ""
        major = str(row.get("专业", "")).strip() if pd.notna(row.get("专业")) else ""
        change_type = str(row.get("异动类型", "")).strip() if pd.notna(row.get("异动类型")) else ""
        grade = str(row.get("年级", "")).strip() if pd.notna(row.get("年级")) else ""
        year = re.search(r"(\d{4})", grade)
        enrollment_year = year.group(1) if year else None

        # 学院名称归一化
        dept = DEPT_MAP.get(dept, dept)

        rec = {
            "student_id": sid,
            "ksh": str(row.get("考生号", "")).strip() if pd.notna(row.get("考生号")) else "",
            "name": str(row.get("姓名", "")).strip() if pd.notna(row.get("姓名")) else "",
            "gender": str(row.get("性别", "")).strip() if pd.notna(row.get("性别")) else "未知",
            "department": dept, "major": major, "year": enrollment_year,
            "class_name": str(row.get("班级", "")).strip() if pd.notna(row.get("班级")) else None,
            "change_type": change_type,
            "change_reason": str(row.get("异动原因", "")).strip() if pd.notna(row.get("异动原因")) else "",
            "reclass": str(row.get("复学班级", "")).strip() if pd.notna(row.get("复学班级")) else None,
            "change_date": serial_to_date(row.get("异动日期")),
            "source": label,
        }
        all_records.append(rec)

        # Update or create student record
        if sid not in unique_students or label == "2025秋":
            unique_students[sid] = rec

print(f"\n共 {len(all_records)} 条记录, {len(unique_students)} 个学生")

# 插入/更新学生
imported = 0
for sid, rec in unique_students.items():
    # 先看库里有没
    exist = conn.execute("SELECT student_id FROM students WHERE student_id=?", (sid,)).fetchone()
    if not exist:
        # 需要插入 → 找个专业code
        code = "900000"
        for row in conn.execute("SELECT major_code FROM majors WHERE major_name=? AND department=?",
                               (rec["major"], rec["department"])):
            code = row[0]; break
        if code == "900000":
            # 动态创建专业（用自增计数器代替len hack）
            next_code = conn.execute("SELECT MAX(CAST(major_code AS INTEGER)) FROM majors").fetchone()[0]
            next_code = (next_code or 900000) + 1
            conn.execute("INSERT OR IGNORE INTO majors (major_code, major_name, department, dept_code) VALUES (?,?,?,?)",
                        (f"{next_code:06d}", rec["major"], rec["department"], str(next_code)[-2:]))
            code = f"{next_code:06d}"
        conn.execute("""INSERT OR IGNORE INTO students (student_id, name, gender, major_code, class_name, enrollment_year, status)
                     VALUES (?,?,?,?,?,?,?)""",
                    (sid, rec["name"], rec["gender"], code,
                     rec["class_name"] if rec["class_name"] and rec["class_name"] != "nan" else None,
                     rec["year"], "在校"))
        imported += 1

print(f"学生: 新增 {imported}")

# 插入状态变更日志
log_count = 0
for rec in all_records:
    target = TYPE_TO_STATUS.get(rec["change_type"])
    if target is None: continue
    from_status = "在校"
    prev = conn.execute("SELECT to_status FROM status_log WHERE student_id=? ORDER BY id DESC LIMIT 1",
                       (rec["student_id"],)).fetchone()
    if prev: from_status = prev[0]
    conn.execute("""INSERT INTO status_log (student_id, from_status, to_status, changed_at, reason)
                   VALUES (?,?,?,?,?)""",
                (rec["student_id"], from_status, target,
                 rec["change_date"] or "2025-01-01", rec["change_reason"]))
    log_count += 1

conn.commit()
conn.execute("PRAGMA foreign_keys = ON")
conn.close()
print(f"日志: 新增 {log_count} 条")
print("\n2025 数据导入完成！")
