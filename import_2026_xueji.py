"""
import_2026_xueji.py — 导入 2026 上半年学籍异动真实数据到学籍管理.db

用法: python import_2026_xueji.py
"""
import pandas as pd
import sqlite3, os, sys, re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "学籍管理.db")
BASE = r"./data"

# 异动类型 → 系统状态映射
TYPE_TO_STATUS = {
    "休学": "休学",
    "退学": "退学",
    "复学": "复学",
    "保留学籍": "保留学籍",
    "应征入伍": "保留学籍",
    "休转退": "退学",
    "注销学籍": "退学",
    "改名": None,  # 不改状态
}

MONTHS = {
    "2026-3月": r"./data",
    "2026-4月": r"./data",
    "2026-5月": r"./data",
    "2026-6月": r"./data",
}

def extract_year(grade_val):
    """从'2023级'或'2023'里提取入学年份"""
    if pd.isna(grade_val):
        return None
    g = str(grade_val).strip()
    m = re.search(r'(\d{4})', g)
    return m.group(1) if m else None

def parse_date(date_val):
    """统一日期格式"""
    if pd.isna(date_val):
        return None
    d = str(date_val).strip()
    # 处理 '2026-3-1' → '2026-03-01'
    parts = d.split()[0].split('-')
    if len(parts) == 3:
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return d

def normalize_month(month_label):
    """月份标签转数字"""
    return month_label.replace("月", "").replace("2026-", "")

def import_all():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")  # 导入时放松约束

    # 收集所有唯一的 院部+专业 对
    dept_major_pairs = set()
    all_records = []

    for month_label, filepath in MONTHS.items():
        print(f"\n读取 {month_label} ...")
        df = pd.read_excel(filepath, sheet_name=0, dtype=str)
        print(f"  {len(df)} 条记录")

        for _, row in df.iterrows():
            dept = str(row.get("院部", "")).strip() if pd.notna(row.get("院部")) else ""
            major = str(row.get("专业", "")).strip() if pd.notna(row.get("专业")) else ""
            if dept and major:
                dept_major_pairs.add((dept, major))

            year = extract_year(row.get("年级"))
            change_type = str(row.get("异动类型", "")).strip() if pd.notna(row.get("异动类型")) else ""

            all_records.append({
                "month": month_label,
                "student_id": str(row["学号"]).strip() if pd.notna(row.get("学号")) else None,
                "ksh": str(row["考生号"]).strip() if pd.notna(row.get("考生号")) else None,
                "name": str(row["姓名"]).strip() if pd.notna(row.get("姓名")) else "",
                "gender": str(row["性别"]).strip() if pd.notna(row.get("性别")) else "未知",
                "department": dept,
                "major": major,
                "year": year,
                "class_name": str(row.get("班级", "")).strip() if pd.notna(row.get("班级")) else None,
                "change_type": change_type,
                "change_reason": str(row.get("异动原因", "")).strip() if pd.notna(row.get("异动原因")) else "",
                "reclass": str(row.get("复学班级", "")).strip() if pd.notna(row.get("复学班级")) else None,
                "change_date": parse_date(row.get("异动日期")),
            })

    print(f"\n共收集 {len(all_records)} 条异动记录，{len(dept_major_pairs)} 个专业/学院对")

    # 插入院系/专业映射
    dept_to_code = {}
    code_counter = 900001
    for dept, major in sorted(dept_major_pairs):
        code = f"{code_counter}"
        dept_to_code[(dept, major)] = code
        conn.execute("INSERT OR IGNORE INTO majors (major_code, major_name, department, dept_code) VALUES (?,?,?,?)",
                  (code, major, dept, code[-2:]))
        code_counter += 1
    print(f"已插入 {len(dept_major_pairs)} 个专业条目")

    # 收集所有唯一学生（最新一条记录的状态作为当前状态）
    students = {}
    student_changes = {}

    for r in all_records:
        sid = r["student_id"]
        if not sid or sid == "nan":
            continue
        # 当前状态：取该批次最后一条
        students[sid] = {
            "name": r["name"],
            "gender": r["gender"],
            "major_key": (r["department"], r["major"]),
            "year": r["year"],
            "class_name": r["class_name"] if r["class_name"] and r["class_name"] != "nan" else None,
        }
        student_changes.setdefault(sid, []).append(r)

    print(f"共 {len(students)} 个唯一学生")

    # 确定每个学生当前状态：取最后一条变更的新状态
    current_statuses = {}
    for sid, changes in student_changes.items():
        # 按文献+日期排序（6月>5月>4月>3月）
        month_order = {"2026-6月": 0, "2026-5月": 1, "2026-4月": 2, "2026-3月": 3}
        changes.sort(key=lambda x: (month_order.get(x["month"], 99), x["change_date"] or ""))

        # 最后一条的异动决定当前状态（仅对休学/退学/复学/保留学籍的有效）
        last = changes[-1]
        status = TYPE_TO_STATUS.get(last["change_type"])
        if status is None:
            # 改名等不改变状态 → 看前一条或默认在校
            # 找最近的状态变更
            status = "在校"
            for ch in reversed(changes):
                s = TYPE_TO_STATUS.get(ch["change_type"])
                if s:
                    status = s
                    break
        current_statuses[sid] = status

    # 插入/更新学生
    inserted_s, updated_s = 0, 0
    for sid, info in students.items():
        major_code = dept_to_code.get(info["major_key"], "900000")
        status = current_statuses.get(sid, "在校")

        # 检查是否已存在
        cur = conn.execute("SELECT student_id FROM students WHERE student_id=?", (sid,))
        exist = cur.fetchone()
        if exist:
            conn.execute("""UPDATE students SET name=?, gender=?, status=?, notes=? WHERE student_id=?""",
                      (info["name"], info["gender"], status,
                       f"最后异动: {info['major_key'][0]}/{info['major_key'][1]}", sid))
            updated_s += 1
        else:
            conn.execute("""INSERT INTO students (student_id, name, gender, major_code, class_name, enrollment_year, status)
                         VALUES (?,?,?,?,?,?,?)""",
                      (sid, info["name"], info["gender"], major_code,
                       info["class_name"], info["year"], status))
            inserted_s += 1
    print(f"学生: 新增 {inserted_s}，更新 {updated_s}")

    # 插入状态变更日志
    log_count = 0
    for sid, changes in student_changes.items():
        for r in changes:
            change_type = r["change_type"]
            target = TYPE_TO_STATUS.get(change_type)
            if target is None:
                # 改名不写日志
                continue
            # 估计 from_status: 看前一条
            from_status = "在校"
            cur2 = conn.execute("SELECT to_status FROM status_log WHERE student_id=? ORDER BY id DESC LIMIT 1", (sid,))
            prev = cur2.fetchone()
            if prev:
                from_status = prev[0]

            conn.execute("""INSERT INTO status_log (student_id, from_status, to_status, changed_at, reason)
                         VALUES (?,?,?,?,?)""",
                      (sid, from_status, target, r["change_date"] or datetime.now().strftime("%Y-%m-%d"),
                       r["change_reason"]))
            log_count += 1
    print(f"状态变更日志: {log_count} 条")

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()
    print(f"\n导入完成！数据库: {DB_PATH}")

if __name__ == "__main__":
    import_all()
