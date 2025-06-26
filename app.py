from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import functools

# --- Inisialisasi Aplikasi Flask ---
app = Flask(__name__, static_folder='static')
app.secret_key = 'kunci-rahasia-yang-paling-aman-dan-unik'

# --- Koneksi ke MongoDB ---
try:
    MONGO_CLIENT = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
    MONGO_CLIENT.server_info()
    DB = MONGO_CLIENT["akademik_db"]
    users_col = DB["users"]
    courses_col = DB["courses"]
    enrollments_col = DB["enrollments"]
    print("Koneksi ke MongoDB berhasil.")
except pymongo.errors.ServerSelectionTimeoutError as err:
    print(f"Koneksi ke MongoDB GAGAL. Pastikan server MongoDB Anda sudah berjalan. Error: {err}")
    exit()

# ===================================================================
# ===== BLOK KODE UNTUK MEMBUAT ADMIN OTOMATIS =====
# ===================================================================
with app.app_context():
    # Cek apakah sudah ada user dengan role 'admin'
    if not users_col.find_one({"role": "admin"}):
        print("Akun admin tidak ditemukan, membuat akun admin default...")
        admin_password = "adminpass"  # Anda bisa ganti password default ini
        hashed_password = generate_password_hash(admin_password)
        users_col.insert_one({
            "username": "admin",
            "password": hashed_password,
            "full_name": "Administrator Sistem",
            "role": "admin",
            "nim": None
        })
        print(f"Akun admin berhasil dibuat dengan username 'admin' dan password '{admin_password}'")
# ===================================================================
# =================== AKHIR BLOK KODE BARU ==========================
# ===================================================================


# --- Decorator untuk Memeriksa Login ---
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash("Anda harus login terlebih dahulu.", "danger")
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

# --- Rute Otentikasi & Dashboard Utama ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users_col.find_one({"username": username})

        if user and check_password_hash(user.get('password', ''), password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['full_name']
            session['user_role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah berhasil logout.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('user_role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'dosen':
        return redirect(url_for('lecturer_dashboard'))
    elif role == 'mahasiswa':
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

# --- Rute untuk ADMIN ---

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    
    all_users = list(users_col.find())
    all_courses = list(courses_col.find())
    all_lecturers = list(users_col.find({"role": "dosen"}))

    return render_template('admin_dashboard.html', users=all_users, courses=all_courses, lecturers=all_lecturers)

@app.route('/admin/register', methods=['POST'])
@login_required
def register_user():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))

    full_name = request.form.get('full_name')
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    nim = request.form.get('nim') if role == 'mahasiswa' else None

    if users_col.find_one({"username": username}):
        flash(f"Username '{username}' sudah digunakan.", "danger")
        return redirect(url_for('admin_dashboard'))

    hashed_password = generate_password_hash(password)
    users_col.insert_one({
        "full_name": full_name, "username": username, "password": hashed_password,
        "role": role, "nim": nim
    })
    flash(f"Pengguna '{full_name}' dengan peran {role} berhasil didaftarkan.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<user_id>')
@login_required
def delete_user(user_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    
    user_to_delete_id = ObjectId(user_id)
    if str(user_to_delete_id) == session.get('user_id'):
        flash("Anda tidak dapat menghapus akun Anda sendiri.", "danger")
        return redirect(url_for('admin_dashboard'))

    users_col.delete_one({"_id": user_to_delete_id})
    enrollments_col.delete_many({"student_id": user_to_delete_id})
    flash("Pengguna berhasil dihapus.", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/add_course', methods=['POST'])
@login_required
def add_course():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    
    course_id = request.form.get('course_id')
    if courses_col.find_one({"_id": course_id}):
        flash(f"Mata Kuliah dengan kode {course_id} sudah ada!", "danger")
    else:
        courses_col.insert_one({
            "_id": course_id,
            "name": request.form.get('course_name'),
            "sks": int(request.form.get('sks')),
            "lecturer_id": ObjectId(request.form.get('lecturer_id'))
        })
        flash("Mata Kuliah baru berhasil ditambahkan.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_course/<course_id>')
@login_required
def delete_course(course_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    enrollments_col.delete_many({"course_id": course_id})
    courses_col.delete_one({"_id": course_id})
    flash(f"Mata Kuliah {course_id} dan data pendaftaran terkait berhasil dihapus.", "success")
    return redirect(url_for('admin_dashboard'))

# --- Rute untuk MAHASISWA ---

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if session.get('user_role') != 'mahasiswa':
        return redirect(url_for('dashboard'))
    
    student_id = ObjectId(session['user_id'])
    
    schedule_pipeline = [
        {"$match": {"student_id": student_id}},
        {"$lookup": {"from": "courses", "localField": "course_id", "foreignField": "_id", "as": "course"}},
        {"$unwind": "$course"},
        {"$lookup": {"from": "users", "localField": "course.lecturer_id", "foreignField": "_id", "as": "lecturer"}},
        {"$unwind": "$lecturer"},
        {"$project": {"_id": 0, "kode_mk": "$course_id", "nama_mk": "$course.name", "sks": "$course.sks", "dosen": "$lecturer.full_name"}}
    ]
    schedule_data = list(enrollments_col.aggregate(schedule_pipeline))

    gpa_pipeline = [
        {"$match": {"student_id": student_id, "grade": {"$ne": None, "$exists": True}}},
        {"$lookup": {"from": "courses", "localField": "course_id", "foreignField": "_id", "as": "c"}},
        {"$unwind": "$c"},
        {"$project": {"grade": 1, "sks": "$c.sks", "course_name": "$c.name", "course_id": 1, "bobot": {"$switch": {"branches": [{"case": {"$eq": ["$grade", "A"]}, "then": 4.0}, {"case": {"$eq": ["$grade", "B"]}, "then": 3.0}, {"case": {"$eq": ["$grade", "C"]}, "then": 2.0}, {"case": {"$eq": ["$grade", "D"]}, "then": 1.0}], "default": 0.0}}}},
        {"$group": {"_id": "$student_id", "total_sks": {"$sum": "$sks"}, "total_bobot_x_sks": {"$sum": {"$multiply": ["$sks", "$bobot"]}}, "transcript_items": {"$push": {"kode_mk": "$course_id", "nama_mk": "$course_name", "sks": "$sks", "nilai": "$grade"}}}},
        {"$project": {"_id": 0, "transcript_items": 1, "total_sks": 1, "ipk": {"$cond": {"if": {"$eq": ["$total_sks", 0]}, "then": 0, "else": {"$divide": ["$total_bobot_x_sks", "$total_sks"]}}}}}
    ]
    gpa_result = list(enrollments_col.aggregate(gpa_pipeline))
    transcript_data = gpa_result[0] if gpa_result else None

    return render_template('student_dashboard.html', schedule=schedule_data, transcript=transcript_data)

@app.route('/student/enroll')
@login_required
def enroll_courses():
    if session.get('user_role') != 'mahasiswa':
        return redirect(url_for('dashboard'))

    student_id = ObjectId(session['user_id'])
    enrolled_courses_docs = list(enrollments_col.find({"student_id": student_id}, {"_id": 0, "course_id": 1}))
    enrolled_course_ids = [doc['course_id'] for doc in enrolled_courses_docs]

    all_courses = list(courses_col.find())
    return render_template('available_courses.html', courses=all_courses, enrolled_ids=enrolled_course_ids)

@app.route('/student/enroll/action/<course_id>', methods=['POST'])
@login_required
def enroll_action(course_id):
    if session.get('user_role') != 'mahasiswa':
        return redirect(url_for('dashboard'))

    student_id = ObjectId(session['user_id'])
    if enrollments_col.find_one({"student_id": student_id, "course_id": course_id}):
        flash("Anda sudah terdaftar di mata kuliah ini.", "danger")
    else:
        enrollments_col.insert_one({"student_id": student_id, "course_id": course_id, "grade": None})
        flash(f"Berhasil mengambil mata kuliah {course_id}.", "success")
    return redirect(url_for('enroll_courses'))

# --- Rute untuk DOSEN ---

@app.route('/lecturer/dashboard')
@login_required
def lecturer_dashboard():
    if session.get('user_role') != 'dosen':
        return redirect(url_for('dashboard'))
    
    lecturer_id = ObjectId(session['user_id'])
    courses = list(courses_col.find({"lecturer_id": lecturer_id}))
    
    for course in courses:
        pipeline = [
            {"$match": {"course_id": course['_id']}},
            {"$lookup": {"from": "users", "localField": "student_id", "foreignField": "_id", "as": "student"}},
            {"$unwind": "$student"},
            {"$project": {"_id": 1, "grade": 1, "student_name": "$student.full_name", "student_nim": "$student.nim"}}
        ]
        course['students'] = list(enrollments_col.aggregate(pipeline))
        
    return render_template('lecturer_dashboard.html', courses=courses)

@app.route('/lecturer/input_grade', methods=['POST'])
@login_required
def input_grade():
    if session.get('user_role') != 'dosen':
        return redirect(url_for('dashboard'))
    
    enrollment_id = ObjectId(request.form['enrollment_id'])
    new_grade = request.form.get('grade').upper()

    if new_grade in ['A', 'B', 'C', 'D', 'E']:
        enrollments_col.update_one({"_id": enrollment_id}, {"$set": {"grade": new_grade}})
        flash('Nilai berhasil diperbarui!', 'success')
    else:
        flash('Format nilai tidak valid.', 'danger')
    return redirect(url_for('lecturer_dashboard'))

# --- Jalankan Aplikasi ---

if __name__ == '__main__':
    # Menambahkan reloader_type='stat' untuk kompatibilitas yang lebih baik di Windows
    app.run(debug=True, port=5001, reloader_type='stat')