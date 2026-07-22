"""rebuild_roster.py — 重建在校生名单库 v3：字段完整，去SX/ZP/BZ/班级名"""
import pandas as pd, sqlite3

SRC = r"./data"
DB = r"D:\AI实践案例\2026-07-22_AI数据库\在校生名单.db"
DEPT = {"康养康育学院":"教育学院","食品药品学院":"健康学院","数字财贸学院":"财经学院","汽车与交通学院":"车辆工程学院"}

df = pd.read_excel(SRC, sheet_name=0, dtype=str)

conn = sqlite3.connect(DB)
conn.execute("DROP TABLE IF EXISTS students")
conn.execute("DROP TABLE IF EXISTS majors")
conn.execute("DROP TABLE IF EXISTS import_log")

# 建 students：原表29列 - SX,ZP,BZ,班级名称=25列 + dept,xsh(归一化),major_code,status,notes = 30
conn.execute('''CREATE TABLE students (
    ksh TEXT, syssdm TEXT, student_id TEXT PRIMARY KEY,
    name TEXT, gender TEXT, birthday TEXT, zzmm TEXT, mz TEXT,
    yxdm TEXT, yxmc TEXT, zydm TEXT, zymc TEXT,
    fy TEXT, dept TEXT, xsh TEXT, bh TEXT, cc TEXT, xz TEXT, xxxs TEXT,
    dqszj TEXT, rx_date TEXT, yjby_date TEXT, zczt TEXT,
    xgsj TEXT, cxsj TEXT, major_cat TEXT,
    major_code TEXT, status TEXT, notes TEXT
)''')
conn.execute("CREATE TABLE majors (major_code TEXT PRIMARY KEY, major_name TEXT, department TEXT, major_cat TEXT)")

# 专业去重
maj = {}
for _, r in df.iterrows():
    z = str(r["ZYMC"]).strip() if pd.notna(r["ZYMC"]) else ""
    f = str(r["FY"]).strip() if pd.notna(r["FY"]) else ""
    d = DEPT.get(f, f)
    k = (z, d)
    if k not in maj:
        cat = str(r.get("专业大类", "")).strip()
        maj[k] = (str(abs(hash(k)) % 90000 + 10000).zfill(5), z, d, cat)

for code, name, dept, cat in maj.values():
    conn.execute("INSERT OR IGNORE INTO majors VALUES (?,?,?,?)", (code, name, dept, cat))

S = lambda r, k: str(r[k]).strip() if pd.notna(r.get(k)) else ""

n = 0
g = 0
for _, r in df.iterrows():
    sid = S(r, "XH")
    fv = S(r, "FY")
    dv = DEPT.get(fv, fv)
    zv = S(r, "ZYMC")
    mc = maj.get((zv, dv), ("99999",))[0]
    isg = S(r, "YJBYRQ") == "20260620"
    if isg:
        g += 1
    n += 1

    xsh_v = S(r, "XSH")
    if xsh_v:
        xsh_v = DEPT.get(xsh_v, xsh_v)  # XSH也归一化

    vals = (
        S(r,"KSH"), S(r,"SYSSDM"), sid,
        S(r,"XM"), S(r,"XB"), S(r,"CSRQ"), S(r,"ZZMM"), S(r,"MZ"),
        S(r,"YXDM"), S(r,"YXMC"), S(r,"ZYDM"), zv,
        fv, dv, xsh_v,
        S(r,"BH"), S(r,"CC"), S(r,"XZ"), S(r,"XXXS"), S(r,"DQSZJ"),
        S(r,"RXRQ"), S(r,"YJBYRQ"), S(r,"ZCZT"),
        S(r,"XGSJ"), S(r,"CXSJ"), S(r,"专业大类"),
        mc, "在校", "待毕业20260620" if isg else ""
    )
    conn.execute("INSERT INTO students VALUES (" + ",".join("?" for _ in vals) + ")", vals)

conn.execute("""CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now','localtime')),
    source TEXT, action TEXT, rows_count INTEGER, notes TEXT
)""")
conn.execute("INSERT INTO import_log (source, action, rows_count, notes) VALUES (?,?,?,?)",
             ("2026-7-15总名单", "v3重建-去SX/ZP/BZ/班级名", len(df),
              f"专业{len(maj)}个；{g}人待毕业"))

conn.commit()
conn.close()

# 验证
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
n_stu = c.execute("SELECT COUNT(*) FROM students").fetchone()[0]
n_grad = c.execute("SELECT COUNT(*) FROM students WHERE notes LIKE '%20260620%'").fetchone()[0]
print(f"学生: {n_stu}  待毕业: {n_grad}  {'PASS' if n_stu==9945 and n_grad==14 else 'FAIL'}")

n_xsh = c.execute("SELECT COUNT(DISTINCT xsh) FROM students").fetchone()[0]
print(f"XSH unique: {n_xsh} (应7)")

print("XZ分布:")
for r in c.execute("SELECT xz, COUNT(*) n FROM students GROUP BY xz ORDER BY xz"): print(f"  学制{r['xz']}: {r['n']}")
print("XXXS:")
for r in c.execute("SELECT xxxs, COUNT(*) n FROM students GROUP BY xxxs"): print(f"  {r['xxxs']}: {r['n']}")
print("毕业年份分布:")
for r in c.execute("SELECT yjby_date, COUNT(*) n FROM students GROUP BY yjby_date ORDER BY yjby_date"): print(f"  {r['yjby_date']}: {r['n']}")
c.close()
