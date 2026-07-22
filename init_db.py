"""
init_db.py — 初始化学籍管理数据库
用法：python init_db.py [--seed]  # 加 --seed 会插入模拟数据用于演示
"""
import sqlite3, sys, os

DB_PATH = os.path.join(os.path.dirname(__file__), "学籍管理.db")

SCHEMA_SQL = """
-- 专业表
CREATE TABLE IF NOT EXISTS majors (
    major_code   TEXT PRIMARY KEY,        -- 国标6位码
    major_name   TEXT NOT NULL,            -- 专业名称
    department   TEXT NOT NULL,            -- 所属学院
    dept_code    TEXT NOT NULL             -- 二级学院专业代码(2位)
);

-- 班级表
CREATE TABLE IF NOT EXISTS classes (
    class_name   TEXT PRIMARY KEY,         -- 班级名，如 "24机电一体化1班"
    major_code   TEXT NOT NULL REFERENCES majors(major_code),
    counselor_id TEXT                      -- 辅导员工号
);

-- 教师表
CREATE TABLE IF NOT EXISTS teachers (
    teacher_id   TEXT PRIMARY KEY,         -- 工号
    name         TEXT NOT NULL,            -- 姓名
    department   TEXT NOT NULL,            -- 所属学院
    role         TEXT NOT NULL DEFAULT '教师'  -- 角色：辅导员/教师/教务管理员
);

-- 学生表（核心表）
CREATE TABLE IF NOT EXISTS students (
    student_id     TEXT PRIMARY KEY,       -- 学号（10位）
    name           TEXT NOT NULL,          -- 姓名
    gender         TEXT DEFAULT '未知',
    major_code     TEXT NOT NULL REFERENCES majors(major_code),
    class_name     TEXT REFERENCES classes(class_name),
    enrollment_year TEXT,                  -- 入学年份，如 '2024'
    status         TEXT NOT NULL DEFAULT '在校',  -- 在校/休学/退学/毕业/复学
    counselor      TEXT,                   -- 辅导员姓名（冗余方便直接查）
    notes          TEXT DEFAULT ''
);

-- 状态变更日志（追踪谁什么时候被迁移了）
CREATE TABLE IF NOT EXISTS status_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   TEXT NOT NULL REFERENCES students(student_id),
    from_status  TEXT NOT NULL,
    to_status    TEXT NOT NULL,
    changed_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    reason       TEXT DEFAULT ''
);

-- 课程库（全校课程主数据）
CREATE TABLE IF NOT EXISTS courses (
    course_id     TEXT PRIMARY KEY,        -- 课程代码
    course_name   TEXT NOT NULL,
    category      TEXT,                    -- 公共基础/专业基础/专业核心/实践教学
    req_direction TEXT                     -- 要求师资方向，如 '无人机'/'财会'
);

-- 师资资质（谁会教什么——这是人培预审的关键输入）
CREATE TABLE IF NOT EXISTS faculty_qualifications (
    teacher_id   TEXT NOT NULL REFERENCES teachers(teacher_id),
    direction    TEXT NOT NULL,           -- 能教方向，如 '无人机'
    level        TEXT,                    -- 学历专业/职业证书/实际授课经历
    cert_name    TEXT,
    PRIMARY KEY (teacher_id, direction)
);

-- 人培方案（按 专业+版本年）
CREATE TABLE IF NOT EXISTS programs (
    program_id   TEXT PRIMARY KEY,        -- 如 '460301-2024'
    major_code   TEXT NOT NULL REFERENCES majors(major_code),
    year         TEXT NOT NULL,           -- 方案版本年
    total_credits INTEGER,
    status       TEXT DEFAULT '草稿'
);

-- 方案课程（人培方案里列了哪些课）
CREATE TABLE IF NOT EXISTS program_courses (
    program_id   TEXT NOT NULL REFERENCES programs(program_id),
    course_id    TEXT NOT NULL REFERENCES courses(course_id),
    semester     TEXT,
    credits      INTEGER,
    PRIMARY KEY (program_id, course_id)
);
"""

DEMO_DATA = {
    "majors": [
        ("460301", "机电一体化技术", "智能制造学院", "01"),
        ("530302", "大数据与会计",    "财经学院",     "02"),
        ("510201", "计算机应用技术",  "人工智能学院", "07"),
        ("570102K","学前教育",        "教育学院",     "06"),
    ],
    "teachers": [
        ("T001", "王建国", "智能制造学院", "辅导员"),
        ("T002", "李明芳", "财经学院",     "辅导员"),
        ("T003", "赵小红", "人工智能学院", "辅导员"),
        ("T004", "张小雨", "教育学院",     "辅导员"),
        ("T005", "陈主任", "教务处",       "教务管理员"),
    ],
    "classes": [
        ("24机电一体化1班", "460301", "T001"),
        ("24机电一体化2班", "460301", "T001"),
        ("24大数据会计1班", "530302", "T002"),
        ("24计算机应用1班", "510201", "T003"),
        ("24学前教育1班",   "570102K","T004"),
    ],
    "students": [
        ("2024010001", "张伟",   "男", "460301", "24机电一体化1班", "2024"),
        ("2024010002", "李娜",   "女", "460301", "24机电一体化1班", "2024"),
        ("2024010003", "王磊",   "男", "530302", "24大数据会计1班", "2024"),
        ("2024010004", "赵敏",   "女", "510201", "24计算机应用1班", "2024"),
        ("2024010005", "刘洋",   "男", "570102K","24学前教育1班",   "2024"),
        ("2024010006", "陈静",   "女", "460301", "24机电一体化2班", "2024"),
        ("2024010007", "周涛",   "男", "460301", "24机电一体化2班", "2024"),
        ("2024010008", "吴芳",   "女", "530302", "24大数据会计1班", "2024"),
        ("2024010009", "孙权",   "男", "510201", "24计算机应用1班", "2024"),
        ("2024010010", "黄丽",   "女", "570102K","24学前教育1班",   "2024"),
        # 模拟几个非在校状态
        ("2023010050", "马超",   "男", "460301", "23机电一体化1班", "2023", "休学"),
        ("2023010051", "林小红", "女", "530302", "23大数据会计1班", "2023", "休学"),
        ("2022010100", "何大壮", "男", "510201", "22计算机应用1班", "2022", "退学"),
    ],
    # 课程库：含一门"无人机应用技术"，要求师资方向=无人机
    "courses": [
        ("KC001", "机械制图",       "专业基础", "机械"),
        ("KC002", "电工电子技术",   "专业基础", "电子"),
        ("KC003", "无人机应用技术", "专业核心", "无人机"),
        ("KC004", "会计基础",       "专业基础", "财会"),
        ("KC005", "Python程序设计", "专业核心", "软件"),
    ],
    # 师资资质：注意——没有任何老师有"无人机"方向资质
    "faculty_qualifications": [
        ("T001", "机械", "学历专业", "机械工程"),
        ("T001", "电子", "实际授课", "电工电子"),
        ("T002", "财会", "学历专业", "会计学"),
        ("T003", "软件", "职业证书", "软考中级"),
    ],
    # 人培方案：机电一体化 2024 版
    "programs": [
        ("460301-2024", "460301", "2024", 130, "执行中"),
        ("530302-2024", "530302", "2024", 125, "执行中"),
    ],
    # 方案课程：机电方案里列了无人机课，但师资表里没人会
    "program_courses": [
        ("460301-2024", "KC001", "1", 4),
        ("460301-2024", "KC002", "1", 4),
        ("460301-2024", "KC003", "2", 3),
        ("530302-2024", "KC004", "1", 4),
        ("530302-2024", "KC005", "2", 3),
    ],
}

def init_database(seed=False):
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    if seed:
        conn.executemany("INSERT OR IGNORE INTO majors VALUES (?,?,?,?)", DEMO_DATA["majors"])
        conn.executemany("INSERT OR IGNORE INTO teachers VALUES (?,?,?,?)", DEMO_DATA["teachers"])
        conn.executemany("INSERT OR IGNORE INTO classes VALUES (?,?,?)", DEMO_DATA["classes"])
        for s in DEMO_DATA["students"]:
            sid, name, gender, major, cls, year = s[:6]
            status = s[6] if len(s) > 6 else "在校"
            conn.execute("INSERT OR IGNORE INTO students (student_id,name,gender,major_code,class_name,enrollment_year,status) VALUES (?,?,?,?,?,?,?)",
                        (sid, name, gender, major, cls, year, status))
        conn.executemany("INSERT OR IGNORE INTO courses VALUES (?,?,?,?)", DEMO_DATA["courses"])
        conn.executemany("INSERT OR IGNORE INTO faculty_qualifications VALUES (?,?,?,?)", DEMO_DATA["faculty_qualifications"])
        conn.executemany("INSERT OR IGNORE INTO programs VALUES (?,?,?,?,?)", DEMO_DATA["programs"])
        conn.executemany("INSERT OR IGNORE INTO program_courses VALUES (?,?,?,?)", DEMO_DATA["program_courses"])
        print(f"已插入 {len(DEMO_DATA['majors'])} 个专业、{len(DEMO_DATA['teachers'])} 位教师、"
              f"{len(DEMO_DATA['classes'])} 个班级、{len(DEMO_DATA['students'])} 名学生、"
              f"{len(DEMO_DATA['courses'])} 门课程、{len(DEMO_DATA['programs'])} 份人培方案（含模拟数据）")

    conn.commit()
    conn.close()
    print(f"数据库初始化完成：{DB_PATH}")


if __name__ == "__main__":
    seed = "--seed" in sys.argv
    init_database(seed=seed)
