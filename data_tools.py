"""
data_tools.py — 学籍数据自然语言操作引擎
通过命令行参数接收操作指令，输出结构化的查询/操作结果。
小布会解析用户自然语言并转成这个工具的调用。

用法：
  # 查询
  python data_tools.py query count         --status 在校                           # 统计某状态学生数
  python data_tools.py query count         --major "机电一体化技术"                # 某专业人数
  python data_tools.py query count         --class "24机电一体化1班"               # 某班级人数
  python data_tools.py query list          --major "机电一体化技术" --status 在校   # 列出学生
  python data_tools.py query detail        2024010001                               # 查单个学生详情
  python data_tools.py query summary                                               # 汇总统计

  # 操作
  python data_tools.py move 2024010001     --to 休学     --reason "因病休学"      # 迁移状态
  python data_tools.py update 2024010001   --field counselor --value "王建国"     # 更新字段
  python data_tools.py add student         --name "张三" --major "460301" ...      # 新增学生
  python data_tools.py delete student      2024010001                              # 删除（+日志）
"""
import sqlite3, os, sys, json, argparse

DB_PATH = os.path.join(os.path.dirname(__file__), "学籍管理.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ─── 查询 ───

def cmd_query(args):
    conn = get_conn()
    sub = args.subcommand  # count / list / detail / summary

    if sub == "count":
        where_clauses = []
        params = []
        if args.status:
            where_clauses.append("s.status = ?"); params.append(args.status)
        if args.major:
            where_clauses.append("m.major_name = ?"); params.append(args.major)
        if args.dept:
            where_clauses.append("m.department = ?"); params.append(args.dept)
        if args.class_name:
            where_clauses.append("s.class_name = ?"); params.append(args.class_name)
        if args.year:
            where_clauses.append("s.enrollment_year = ?"); params.append(args.year)
        if args.counselor:
            where_clauses.append("s.counselor = ?"); params.append(args.counselor)

        where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        sql = f"SELECT COUNT(*) as cnt FROM students s LEFT JOIN majors m ON s.major_code = m.major_code {where}"
        row = conn.execute(sql, params).fetchone()
        result = {"type": "count", "count": row["cnt"]}

    elif sub == "list":
        where_clauses = []
        params = []
        if args.status:
            where_clauses.append("s.status = ?"); params.append(args.status)
        if args.major:
            where_clauses.append("m.major_name = ?"); params.append(args.major)
        if args.dept:
            where_clauses.append("m.department = ?"); params.append(args.dept)
        if args.class_name:
            where_clauses.append("s.class_name = ?"); params.append(args.class_name)
        if args.year:
            where_clauses.append("s.enrollment_year = ?"); params.append(args.year)
        if args.counselor:
            where_clauses.append("s.counselor = ?"); params.append(args.counselor)

        where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        sql = f"""SELECT s.student_id, s.name, s.gender, m.major_name, s.class_name,
                         s.enrollment_year, s.status, s.counselor, s.notes
                  FROM students s LEFT JOIN majors m ON s.major_code = m.major_code
                  {where} ORDER BY s.student_id"""
        rows = conn.execute(sql, params).fetchall()
        result = {"type": "list", "count": len(rows),
                  "students": [dict(r) for r in rows]}

    elif sub == "detail":
        sql = """SELECT s.*, m.major_name, m.department
                 FROM students s LEFT JOIN majors m ON s.major_code = m.major_code
                 WHERE s.student_id = ?"""
        row = conn.execute(sql, (args.student_id,)).fetchone()
        if row:
            result = {"type": "detail", "student": dict(row)}
        else:
            result = {"type": "error", "message": f"未找到学号 {args.student_id}"}

    elif sub == "summary":
        # 各状态人数
        status_counts = conn.execute("SELECT status, COUNT(*) as cnt FROM students GROUP BY status").fetchall()
        # 各专业人数
        major_counts = conn.execute("""SELECT m.major_name, COUNT(*) as cnt FROM students s
                                        JOIN majors m ON s.major_code = m.major_code
                                        GROUP BY m.major_name ORDER BY cnt DESC""").fetchall()
        # 各班级人数
        class_counts = conn.execute("SELECT class_name, COUNT(*) as cnt FROM students GROUP BY class_name ORDER BY class_name").fetchall()
        total = conn.execute("SELECT COUNT(*) as cnt FROM students").fetchone()["cnt"]
        result = {
            "type": "summary",
            "total": total,
            "status": {r["status"]: r["cnt"] for r in status_counts},
            "majors": [dict(r) for r in major_counts],
            "classes": [dict(r) for r in class_counts],
        }

    conn.close()
    return result


# ─── 操作 ───

def cmd_move(args):
    """迁移学生状态（休学/复学/退学/毕业）"""
    conn = get_conn()
    student = conn.execute("SELECT student_id, name, status FROM students WHERE student_id = ?",
                          (args.student_id,)).fetchone()
    if not student:
        conn.close()
        return {"type": "error", "message": f"未找到学号 {args.student_id}"}

    from_status = student["status"]
    to_status = args.to_status
    if from_status == to_status:
        conn.close()
        return {"type": "warning", "message": f"{student['name']}({args.student_id}) 当前状态已经是「{to_status}」，无需操作"}

    conn.execute("UPDATE students SET status = ? WHERE student_id = ?", (to_status, args.student_id))
    conn.execute("""INSERT INTO status_log (student_id, from_status, to_status, reason)
                    VALUES (?, ?, ?, ?)""", (args.student_id, from_status, to_status, args.reason or ""))
    conn.commit()
    conn.close()
    return {
        "type": "success",
        "action": "move",
        "student_name": student["name"],
        "student_id": args.student_id,
        "from": from_status,
        "to": to_status,
        "reason": args.reason or "无备注"
    }


def cmd_update(args):
    conn = get_conn()
    student = conn.execute("SELECT name FROM students WHERE student_id = ?",
                          (args.student_id,)).fetchone()
    if not student:
        conn.close()
        return {"type": "error", "message": f"未找到学号 {args.student_id}"}

    allowed_fields = {
        "name": "姓名", "gender": "性别", "status": "状态",
        "class_name": "班级", "counselor": "辅导员", "major_code": "专业代码",
        "enrollment_year": "入学年份", "notes": "备注"
    }
    if args.field not in allowed_fields:
        conn.close()
        return {"type": "error", "message": f"不允许修改字段「{args.field}」。允许：{','.join(allowed_fields.keys())}"}

    old_value = conn.execute(f"SELECT {args.field} FROM students WHERE student_id = ?",
                            (args.student_id,)).fetchone()[0]
    conn.execute(f"UPDATE students SET {args.field} = ? WHERE student_id = ?",
                (args.value, args.student_id))
    conn.commit()
    conn.close()
    return {
        "type": "success",
        "action": "update",
        "student_name": student["name"],
        "student_id": args.student_id,
        "field": allowed_fields[args.field],
        "from": old_value,
        "to": args.value
    }


def cmd_add(args):
    conn = get_conn()
    sid = args.student_id or ""
    name = args.name or ""
    if not sid or not name:
        conn.close()
        return {"type": "error", "message": "学号和姓名为必填项"}

    # 检查是否已存在
    existing = conn.execute("SELECT 1 FROM students WHERE student_id = ?", (sid,)).fetchone()
    if existing:
        conn.close()
        return {"type": "error", "message": f"学号 {sid} 已存在，不能重复添加"}

    conn.execute("""INSERT INTO students (student_id, name, gender, major_code, class_name,
                   enrollment_year, status, counselor, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (sid, name, args.gender or "未知", args.major_code or "",
                 args.class_name or "", args.year or "", args.status or "在校",
                 args.counselor or "", args.notes or ""))
    conn.commit()
    conn.close()
    return {"type": "success", "action": "add", "student_id": sid, "name": name}


def cmd_delete(args):
    conn = get_conn()
    student = conn.execute("SELECT name FROM students WHERE student_id = ?",
                          (args.student_id,)).fetchone()
    if not student:
        conn.close()
        return {"type": "error", "message": f"未找到学号 {args.student_id}"}

    # 删除前记录日志
    conn.execute("""INSERT INTO status_log (student_id, from_status, to_status, reason)
                    VALUES (?, (SELECT status FROM students WHERE student_id = ?), '已删除', ?)""",
                (args.student_id, args.student_id, args.reason or "手动删除"))
    conn.execute("DELETE FROM students WHERE student_id = ?", (args.student_id,))
    conn.commit()
    conn.close()
    return {"type": "success", "action": "delete", "student_name": student["name"], "student_id": args.student_id}


# ─── CLI 解析 ───

def main():
    parser = argparse.ArgumentParser(description="学籍数据操作工具")
    sub = parser.add_subparsers(dest="mode")

    # query
    q = sub.add_parser("query")
    q_sub = q.add_subparsers(dest="subcommand")
    q_cnt = q_sub.add_parser("count")
    q_lst = q_sub.add_parser("list")
    q_det = q_sub.add_parser("detail")
    q_sum = q_sub.add_parser("summary")
    for p in [q_cnt, q_lst]:
        p.add_argument("--status")
        p.add_argument("--major")
        p.add_argument("--dept")
        p.add_argument("--class", dest="class_name")
        p.add_argument("--year")
        p.add_argument("--counselor")
    q_det.add_argument("student_id")

    # move
    m = sub.add_parser("move")
    m.add_argument("student_id")
    m.add_argument("--to", dest="to_status", required=True)
    m.add_argument("--reason", default="")

    # update
    u = sub.add_parser("update")
    u.add_argument("student_id")
    u.add_argument("--field", required=True)
    u.add_argument("--value", required=True)

    # add
    a = sub.add_parser("add")
    a.add_argument("--sid", dest="student_id", required=False)
    a.add_argument("--name", required=False)
    a.add_argument("--gender")
    a.add_argument("--major", dest="major_code")
    a.add_argument("--class", dest="class_name")
    a.add_argument("--year")
    a.add_argument("--status")
    a.add_argument("--counselor")
    a.add_argument("--notes")

    # delete
    d = sub.add_parser("delete")
    d.add_argument("student_id")
    d.add_argument("--reason", default="")

    args = parser.parse_args()
    if not hasattr(args, "mode") or not args.mode:
        parser.print_help()
        sys.exit(1)

    if args.mode == "query":
        if not hasattr(args, "subcommand") or not args.subcommand:
            parser.print_help()
            sys.exit(1)
        result = cmd_query(args)
    elif args.mode == "move":
        result = cmd_move(args)
    elif args.mode == "update":
        result = cmd_update(args)
    elif args.mode == "add":
        result = cmd_add(args)
    elif args.mode == "delete":
        result = cmd_delete(args)
    else:
        result = {"type": "error", "message": f"未知命令 {args.mode}"}

    # 输出 JSON（方便小布解析）
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
