# import library yang dibutuhkan
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
from functools import wraps

app = Flask(__name__)
app.secret_key = "ganti_dengan_secret_key_aman_123"  # secret key untuk session

# konfigurasi database
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "arin12345",
    "database": "kasirbaru"
}

# fungsi buat konek database
def get_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn

# supaya halaman tertentu cuma bisa dibuka setelah login
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "kasir" not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# halaman awal
@app.route('/')
def index():
    if "kasir" in session:
        return redirect(url_for('dashboard'))  # kalau sudah login langsung ke dashboard
    return redirect(url_for('login'))

# halaman login
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')

        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM kasir WHERE username=%s", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        # cek username & password
        if row and row['password'] == password:
            session['kasir'] = {
                "id_kasir": row['id_kasir'],
                "nama": row['nama_kasir'],
                "username": row['username']
            }
            flash("Login berhasil.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Username / password salah.", "danger")

    return render_template('login.html')

# logout user
@app.route('/logout')
def logout():
    session.pop('kasir', None)
    session.pop('cart', None)  # kosongkan keranjang
    flash("Anda telah logout.", "info")
    return redirect(url_for('login'))

# dashboard setelah login
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', kasir=session['kasir'])

# halaman produk
@app.route('/produk', methods=['GET','POST'])
@login_required
def produk():
    q = ''  # kata kunci pencarian
    if request.method == 'POST':
        q = request.form.get('q','').strip()

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # kalau ada pencarian
    if q:
        cur.execute("SELECT * FROM barang WHERE nama_barang LIKE %s ORDER BY nama_barang", (f"%{q}%",))
    else:
        cur.execute("SELECT * FROM barang ORDER BY nama_barang")

    items = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('produk.html', items=items, q=q)

# fungsi buat inisialisasi keranjang
def init_cart():
    if 'cart' not in session:
        session['cart'] = []

# tambah barang ke keranjang
@app.route('/cart/add', methods=['POST'])
@login_required
def cart_add():
    init_cart()
    id_barang = int(request.form.get('id_barang'))
    jumlah = int(request.form.get('jumlah',1))

    # ambil data barang dari database
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM barang WHERE id_barang=%s", (id_barang,))
    barang = cur.fetchone()
    cur.close()
    conn.close()

    if not barang:
        flash("Produk tidak ditemukan.", "danger")
        return redirect(url_for('produk'))

    cart = session['cart']

    # kalau barang sudah ada di keranjang → tambah jumlahnya
    for it in cart:
        if it['id_barang'] == id_barang:
            it['jumlah'] += jumlah
            it['subtotal'] = it['jumlah'] * it['harga']
            session.modified = True
            flash(f"Menambahkan {jumlah} x {barang['nama_barang']} ke keranjang.", "success")
            return redirect(url_for('transaksi'))

    # kalau belum ada → masukin barang baru
    cart.append({
        'id_barang': barang['id_barang'],
        'nama_barang': barang['nama_barang'],
        'harga': barang['harga'],
        'jumlah': jumlah,
        'subtotal': barang['harga'] * jumlah
    })
    session['cart'] = cart

    flash(f"Menambahkan {jumlah} x {barang['nama_barang']} ke keranjang.", "success")
    return redirect(url_for('transaksi'))

# update keranjang
@app.route('/cart/update', methods=['POST'])
@login_required
def cart_update():
    init_cart()
    action = request.form.get('action')

    if action == 'update':
        updates = request.form.getlist('jumlah')
        ids = request.form.getlist('id_barang')

        new_cart = []
        for idx, bid in enumerate(ids):
            jumlah = int(updates[idx])
            if jumlah <= 0:
                continue
            new_cart.append({
                'id_barang': int(bid),
                'nama_barang': request.form.getlist('nama_barang')[idx],
                'harga': int(request.form.getlist('harga')[idx]),
                'jumlah': jumlah,
                'subtotal': int(request.form.getlist('harga')[idx]) * jumlah
            })

        session['cart'] = new_cart
        flash("Keranjang diperbarui.", "success")

    elif action == 'clear':
        session.pop('cart', None)
        flash("Keranjang dikosongkan.", "info")

    return redirect(url_for('transaksi'))

# halaman transaksi (checkout)
@app.route('/transaksi', methods=['GET','POST'])
@login_required
def transaksi():
    init_cart()

    # ambil data pelanggan
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM pelanggan ORDER BY nama_pelanggan")
    pelanggan = cur.fetchall()
    cur.close()
    conn.close()

    if request.method == 'POST':
        # kalau keranjang kosong
        if not session['cart']:
            flash("Keranjang kosong.", "danger")
            return redirect(url_for('transaksi'))

        id_pelanggan = int(request.form.get('id_pelanggan', 2))
        id_kasir = session['kasir']['id_kasir']
        total = sum([item['subtotal'] for item in session['cart']])

        try:
            conn = get_db()
            cur = conn.cursor()

            # simpan transaksi utama
            cur.execute(
                "INSERT INTO transaksi (id_pelanggan, id_kasir, total) VALUES (%s, %s, %s)",
                (id_pelanggan, id_kasir, total)
            )
            id_transaksi = cur.lastrowid

            # simpan detail barang
            for it in session['cart']:
                cur.execute(
                    "INSERT INTO detail_transaksi (id_transaksi, id_barang, jumlah, subtotal) VALUES (%s,%s,%s,%s)",
                    (id_transaksi, it['id_barang'], it['jumlah'], it['subtotal'])
                )

            conn.commit()
            cur.close()
            conn.close()

            session.pop('cart', None)  # kosongkan cart setelah selesai
            flash(f"Transaksi berhasil (ID {id_transaksi}). Total: Rp {total:,}", "success")
            return redirect(url_for('history'))

        except Error as e:
            flash("Terjadi kesalahan saat menyimpan transaksi: " + str(e), "danger")
            return redirect(url_for('transaksi'))

    return render_template('transaksi.html', cart=session['cart'], pelanggan=pelanggan)

# halaman riwayat transaksi
@app.route('/history')
@login_required
def history():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT t.id_transaksi, t.total, t.tanggal, p.nama_pelanggan, k.nama_kasir
        FROM transaksi t
        LEFT JOIN pelanggan p ON p.id_pelanggan = t.id_pelanggan
        LEFT JOIN kasir k ON k.id_kasir = t.id_kasir
        ORDER BY t.tanggal DESC LIMIT 100
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('history.html', rows=rows)

 # detail transaksi
@app.route("/detail/<int:id_transaksi>")
@login_required
def detail_transaksi(id_transaksi):

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Ambil data transaksi
    cursor.execute("""
        SELECT t.id_transaksi, t.total, t.tanggal,
               p.nama_pelanggan, k.nama_kasir
        FROM transaksi t
        JOIN pelanggan p ON t.id_pelanggan = p.id_pelanggan
        JOIN kasir k ON t.id_kasir = k.id_kasir
        WHERE t.id_transaksi = %s
    """, (id_transaksi,))
    trx = cursor.fetchone()

    # Ambil detail barang
    cursor.execute("""
        SELECT d.jumlah, d.subtotal, b.nama_barang, b.harga
        FROM detail_transaksi d
        JOIN barang b ON d.id_barang = b.id_barang
        WHERE d.id_transaksi = %s
    """, (id_transaksi,))
    detail = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("detail_transaksi.html", trx=trx, detail=detail)


# jalankan aplikasi
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
