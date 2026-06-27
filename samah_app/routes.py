import json
import os
import io
import random
import string
from datetime import datetime, date

import qrcode
from flask import (render_template, request, session, redirect, url_for,
                   flash, jsonify, send_file, current_app)

from models import db, Pilgrim, PilgrimGroup, Border, SystemSetting, TrafficHistory, AnnualRegistration
from . import samah_bp


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def generate_group_code():
    prefix = "SM"
    year = datetime.now().year % 100
    rand = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}{year}{rand}"


def generate_registration_number():
    rand = ''.join(random.choices(string.digits, k=8))
    return f"SMH{datetime.now().year}{rand}"


def get_insurance_amount():
    val = SystemSetting.get('insurance_amount', '500000')
    return int(val)


def persian_to_english(text):
    """Convert Persian/Arabic numerals to English"""
    persian = '۰۱۲۳۴۵۶۷۸۹'
    arabic = '٠١٢٣٤٥٦٧٨٩'
    for i, (p, a) in enumerate(zip(persian, arabic)):
        text = text.replace(p, str(i)).replace(a, str(i))
    return text


def validate_national_id(nid):
    nid = persian_to_english(str(nid)).strip()
    if not nid.isdigit() or len(nid) != 10:
        return False
    if len(set(nid)) == 1:
        return False
    check = int(nid[9])
    total = sum(int(nid[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    return (remainder < 2 and check == remainder) or (remainder >= 2 and check == 11 - remainder)


def mock_civil_registry(national_id, birth_date):
    """Mock civil registry web service - returns fake data for demo"""
    mock_data = {
        '0012345678': {'first_name': 'علی', 'last_name': 'احمدی', 'father_name': 'محمد', 'id_number': '12345', 'gender': 'male'},
        '0987654321': {'first_name': 'فاطمه', 'last_name': 'محمدی', 'father_name': 'حسین', 'id_number': '67890', 'gender': 'female'},
    }
    if national_id in mock_data:
        return mock_data[national_id]
    # Generate random data for demo
    gender = 'female' if national_id[-2] in '02468' else 'male'
    return {
        'first_name': 'کاربر',
        'last_name': 'آزمایشی',
        'father_name': 'ولی',
        'id_number': ''.join(random.choices(string.digits, k=6)),
        'gender': gender
    }


def generate_qr_codes(pilgrim, group):
    """Generate 4 QR codes for pilgrim on one A4 row"""
    qr_dir = os.path.join(current_app.root_path, 'static', 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)

    data = json.dumps({
        'reg': pilgrim.registration_number,
        'nid': pilgrim.national_id,
        'name': pilgrim.full_name,
        'passport': pilgrim.passport_number,
        'group': group.group_code,
        'exit_border': group.exit_border.name_fa if group.exit_border else '',
        'departure': group.departure_date,
        'return': group.return_date,
    }, ensure_ascii=False)

    codes = []
    for i in range(4):
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        filename = f"{pilgrim.registration_number}_qr{i+1}.png"
        filepath = os.path.join(qr_dir, filename)
        img.save(filepath)
        codes.append(f"/samah-static/qrcodes/{filename}")

    return codes


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@samah_bp.route('/')
def index():
    return render_template('landing.html')


@samah_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Simulate SSO login - in production redirect to real SSO"""
    if request.method == 'POST':
        national_id = persian_to_english(request.form.get('national_id', '').strip())
        phone = persian_to_english(request.form.get('phone', '').strip())

        if not validate_national_id(national_id):
            flash('کد ملی وارد شده معتبر نمی‌باشد.', 'danger')
            return render_template('login.html')

        if not phone or len(phone) != 11 or not phone.startswith('09'):
            flash('شماره تلفن همراه معتبر نیست.', 'danger')
            return render_template('login.html')

        session['auth_national_id'] = national_id
        session['auth_phone'] = phone
        session['authenticated'] = True
        session.permanent = True

        existing = Pilgrim.query.filter_by(national_id=national_id, is_group_head=True).first()
        if existing and existing.group and existing.group.status == 'paid':
            session['pilgrim_id'] = existing.id
            session['group_id'] = existing.group_id
            return redirect(url_for('samah.receipt', group_id=existing.group_id))

        return redirect(url_for('samah.step1'))

    return render_template('login.html')


@samah_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('samah.index'))


def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('samah.login'))
        return f(*args, **kwargs)
    return decorated


# ── STEP 1: Group Members Registration ──

@samah_bp.route('/register/step1', methods=['GET', 'POST'])
@require_auth
def step1():
    national_id = session['auth_national_id']
    phone = session['auth_phone']
    max_group = int(SystemSetting.get('max_group_size', '10'))

    # Load or create draft group
    group_id = session.get('group_id')
    group = PilgrimGroup.query.get(group_id) if group_id else None

    if group and group.status == 'paid':
        return redirect(url_for('samah.receipt', group_id=group.id))

    if not group:
        group = PilgrimGroup(group_code=generate_group_code(), status='draft')
        db.session.add(group)
        db.session.flush()
        session['group_id'] = group.id

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_member':
            return _add_member(group, national_id, phone, max_group)

        elif action == 'edit_member':
            return _edit_member(group)

        elif action == 'delete_member':
            return _delete_member(group, national_id)

        elif action == 'set_head':
            return _set_head(group, national_id)

        elif action == 'next':
            if not group.members:
                flash('حداقل باید یک عضو گروه ثبت شود.', 'danger')
            else:
                db.session.commit()
                return redirect(url_for('samah.step2'))

    members = Pilgrim.query.filter_by(group_id=group.id).all()
    provinces = _get_provinces()
    is_head_registered = any(m.national_id == national_id for m in members)

    return render_template('step1.html',
                           group=group,
                           members=members,
                           national_id=national_id,
                           phone=phone,
                           max_group=max_group,
                           provinces=provinces,
                           is_head_registered=is_head_registered,
                           insurance_amount=get_insurance_amount())


def _add_member(group, head_national_id, head_phone, max_group):
    members = Pilgrim.query.filter_by(group_id=group.id).all()
    if len(members) >= max_group:
        flash(f'حداکثر تعداد اعضای گروه {max_group} نفر می‌باشد.', 'danger')
        return redirect(url_for('samah.step1'))

    nid = persian_to_english(request.form.get('national_id', '').strip())
    birth_date = persian_to_english(request.form.get('birth_date', '').strip())

    if not validate_national_id(nid):
        flash('کد ملی معتبر نیست.', 'danger')
        return redirect(url_for('samah.step1'))

    existing = Pilgrim.query.filter_by(national_id=nid, group_id=group.id).first()
    if existing:
        flash('این کد ملی قبلاً در گروه ثبت شده است.', 'warning')
        return redirect(url_for('samah.step1'))

    # Check if already registered in another paid group
    already = Pilgrim.query.filter_by(national_id=nid).join(PilgrimGroup).filter(
        PilgrimGroup.status == 'paid').first()
    if already:
        flash('این کد ملی قبلاً در سامانه ثبت نام کرده است.', 'danger')
        return redirect(url_for('samah.step1'))

    # Civil registry lookup
    civil_data = mock_civil_registry(nid, birth_date)

    is_first = len(members) == 0
    phone = head_phone if is_first else persian_to_english(request.form.get('phone', '').strip())
    emergency_phone = persian_to_english(request.form.get('emergency_phone', '').strip())

    pilgrim = Pilgrim(
        national_id=nid,
        first_name=civil_data['first_name'],
        last_name=civil_data['last_name'],
        father_name=civil_data['father_name'],
        id_number=civil_data['id_number'],
        gender=civil_data.get('gender', 'male'),
        birth_date=birth_date,
        phone=phone,
        emergency_phone=emergency_phone,
        passport_number=persian_to_english(request.form.get('passport_number', '').strip()),
        passport_letter=request.form.get('passport_letter', '').strip().upper(),
        passport_expiry=request.form.get('passport_expiry', '').strip(),
        has_disease=request.form.get('has_disease') == 'yes',
        diseases=request.form.get('diseases', '[]'),
        insurance_selected=True,
        insurance_amount=get_insurance_amount(),
        group_id=group.id,
        is_group_head=is_first,
        payment_status='pending',
        registration_number=generate_registration_number(),
    )

    if is_first:
        group.province = request.form.get('province', '')
        group.city = request.form.get('city', '')
        group.address = request.form.get('address', '')
        group.postal_code = persian_to_english(request.form.get('postal_code', '').strip())
        group.phone_landline = persian_to_english(request.form.get('phone_landline', '').strip())

    db.session.add(pilgrim)
    db.session.flush()

    if is_first:
        group.head_member_id = pilgrim.id

    db.session.commit()
    flash(f'زائر {pilgrim.full_name} با موفقیت به گروه اضافه شد.', 'success')
    return redirect(url_for('samah.step1'))


def _edit_member(group):
    member_id = int(request.form.get('member_id', 0))
    pilgrim = Pilgrim.query.filter_by(id=member_id, group_id=group.id).first()
    if not pilgrim:
        flash('عضو مورد نظر یافت نشد.', 'danger')
        return redirect(url_for('samah.step1'))

    pilgrim.emergency_phone = persian_to_english(request.form.get('emergency_phone', '').strip())
    pilgrim.passport_number = persian_to_english(request.form.get('passport_number', '').strip())
    pilgrim.passport_letter = request.form.get('passport_letter', '').strip().upper()
    pilgrim.passport_expiry = request.form.get('passport_expiry', '').strip()
    pilgrim.has_disease = request.form.get('has_disease') == 'yes'
    pilgrim.diseases = request.form.get('diseases', '[]')
    db.session.commit()
    flash('اطلاعات عضو با موفقیت ویرایش شد.', 'success')
    return redirect(url_for('samah.step1'))


def _delete_member(group, head_national_id):
    member_id = int(request.form.get('member_id', 0))
    pilgrim = Pilgrim.query.filter_by(id=member_id, group_id=group.id).first()
    if not pilgrim:
        flash('عضو مورد نظر یافت نشد.', 'danger')
        return redirect(url_for('samah.step1'))

    members_count = Pilgrim.query.filter_by(group_id=group.id).count()
    if pilgrim.is_group_head and members_count > 1:
        flash('برای حذف سرگروه ابتدا سرگروه را تغییر دهید.', 'warning')
        return redirect(url_for('samah.step1'))

    db.session.delete(pilgrim)
    db.session.commit()
    flash('عضو حذف شد.', 'success')
    return redirect(url_for('samah.step1'))


def _set_head(group, current_head_national_id):
    member_id = int(request.form.get('member_id', 0))
    new_head = Pilgrim.query.filter_by(id=member_id, group_id=group.id).first()
    if not new_head:
        flash('عضو مورد نظر یافت نشد.', 'danger')
        return redirect(url_for('samah.step1'))

    # Under-18 check: needs birth_date comparison
    # Pilgrims under 18 cannot be group head
    Pilgrim.query.filter_by(group_id=group.id).update({'is_group_head': False})
    new_head.is_group_head = True
    group.head_member_id = new_head.id
    db.session.commit()
    flash(f'{new_head.full_name} به عنوان سرگروه انتخاب شد.', 'success')
    return redirect(url_for('samah.step1'))


# ── STEP 2: Border & Travel Dates ──

@samah_bp.route('/register/step2', methods=['GET', 'POST'])
@require_auth
def step2():
    group_id = session.get('group_id')
    group = PilgrimGroup.query.get_or_404(group_id)

    if request.method == 'POST':
        group.exit_border_id = int(request.form.get('exit_border_id', 0)) or None
        group.entry_border_id = int(request.form.get('entry_border_id', 0)) or None
        group.departure_date = request.form.get('departure_date', '')
        group.return_date = request.form.get('return_date', '')

        if not group.exit_border_id or not group.departure_date or not group.return_date:
            flash('لطفاً تمام فیلدهای اجباری را پر کنید.', 'danger')
        else:
            db.session.commit()
            return redirect(url_for('samah.step3'))

    borders = Border.query.filter_by(is_active=True).order_by(Border.display_order).all()

    # Traffic data for chart
    current_year_data = _get_current_year_traffic()
    last_year_data = _get_last_year_traffic()
    chart_labels = _get_chart_labels()

    departure_start = SystemSetting.get('departure_start', '')
    departure_end = SystemSetting.get('departure_end', '')
    max_stay_days = int(SystemSetting.get('max_stay_days', '10'))

    return render_template('step2.html',
                           group=group,
                           borders=borders,
                           current_year_data=json.dumps(current_year_data),
                           last_year_data=json.dumps(last_year_data),
                           chart_labels=json.dumps(chart_labels),
                           departure_start=departure_start,
                           departure_end=departure_end,
                           max_stay_days=max_stay_days)


def _get_chart_labels():
    records = TrafficHistory.query.order_by(TrafficHistory.day_number).all()
    if records:
        return list(dict.fromkeys([r.shamsi_date or f"روز {r.day_number}" for r in records]))
    return [f"روز {i}" for i in range(1, 26)]


def _get_current_year_traffic():
    records = AnnualRegistration.query.order_by(AnnualRegistration.shamsi_date).all()
    if records:
        return [r.count for r in records]
    # Demo data
    return [500, 1200, 3000, 8000, 15000, 25000, 38000, 70000, 125000, 147000,
            175000, 170000, 165000, 130000, 98000, 165000, 163000, 65000, 68000,
            95000, 10000, 12000, 8000, 15000, 1000]


def _get_last_year_traffic():
    records = TrafficHistory.query.filter_by(is_current_year=False).order_by(TrafficHistory.day_number).all()
    if records:
        return [r.count for r in records]
    return [0, 0, 0, 0, 70000, 35000, 120000, 100000, 0, 60000,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


# ── STEP 3: Transportation ──

@samah_bp.route('/register/step3', methods=['GET', 'POST'])
@require_auth
def step3():
    group_id = session.get('group_id')
    group = PilgrimGroup.query.get_or_404(group_id)

    if request.method == 'POST':
        group.transport_to_border = request.form.get('transport_to_border', '')
        group.transport_return = request.form.get('transport_return', '')
        group.offer_ride = request.form.get('offer_ride') == 'on'

        plates_raw = request.form.getlist('plate[]')
        plates = [p.strip() for p in plates_raw if p.strip()]
        group.vehicle_plates = json.dumps(plates)

        db.session.commit()
        return redirect(url_for('samah.step4'))

    members = Pilgrim.query.filter_by(group_id=group.id).all()
    return render_template('step3.html', group=group, members=members)


# ── STEP 4: Confirmation ──

@samah_bp.route('/register/step4', methods=['GET', 'POST'])
@require_auth
def step4():
    group_id = session.get('group_id')
    group = PilgrimGroup.query.get_or_404(group_id)
    members = Pilgrim.query.filter_by(group_id=group.id).all()

    if request.method == 'POST':
        # Calculate total amount
        insurance = get_insurance_amount()
        total = insurance * len(members)
        group.total_amount = total
        for m in members:
            m.insurance_amount = insurance
        group.status = 'pending_payment'
        db.session.commit()
        return redirect(url_for('samah.payment'))

    total = get_insurance_amount() * len(members)
    plates = json.loads(group.vehicle_plates or '[]')
    return render_template('step4.html', group=group, members=members,
                           total=total, plates=plates,
                           insurance_amount=get_insurance_amount())


# ── PAYMENT (Simulated) ──

@samah_bp.route('/register/payment', methods=['GET', 'POST'])
@require_auth
def payment():
    group_id = session.get('group_id')
    group = PilgrimGroup.query.get_or_404(group_id)

    if group.status == 'paid':
        return redirect(url_for('samah.receipt', group_id=group.id))

    if request.method == 'POST':
        # Simulate successful payment
        ref = 'PAY' + ''.join(random.choices(string.digits, k=12))
        group.payment_ref = ref
        group.payment_date = datetime.utcnow()
        group.status = 'paid'

        members = Pilgrim.query.filter_by(group_id=group.id).all()
        for m in members:
            m.payment_status = 'paid'
            # Generate QR codes
            codes = generate_qr_codes(m, group)
            m.qr_code_path = json.dumps(codes)

        # Update registration stats
        today_shamsi = _today_shamsi()
        stat = AnnualRegistration.query.filter_by(shamsi_date=today_shamsi).first()
        if stat:
            stat.count += len(members)
        else:
            db.session.add(AnnualRegistration(shamsi_date=today_shamsi, count=len(members)))

        db.session.commit()
        return redirect(url_for('samah.receipt', group_id=group.id))

    return render_template('payment.html', group=group)


def _today_shamsi():
    try:
        from persiantools.jdatetime import JalaliDate
        jd = JalaliDate.today()
        return jd.strftime('%Y/%m/%d')
    except Exception:
        return datetime.now().strftime('%Y/%m/%d')


# ── STEP 5: Receipt ──

@samah_bp.route('/receipt/<int:group_id>')
@require_auth
def receipt(group_id):
    group = PilgrimGroup.query.get_or_404(group_id)
    members = Pilgrim.query.filter_by(group_id=group.id).all()
    plates = json.loads(group.vehicle_plates or '[]')

    members_with_qr = []
    for m in members:
        qr_codes = json.loads(m.qr_code_path or '[]')
        members_with_qr.append((m, qr_codes))

    return render_template('receipt.html', group=group, members=members_with_qr, plates=plates)


# ── API: Civil Registry Lookup ──

@samah_bp.route('/api/lookup', methods=['POST'])
@require_auth
def api_lookup():
    data = request.get_json()
    nid = persian_to_english(data.get('national_id', '').strip())
    birth_date = persian_to_english(data.get('birth_date', '').strip())

    if not validate_national_id(nid):
        return jsonify({'success': False, 'error': 'کد ملی معتبر نیست'})

    civil_data = mock_civil_registry(nid, birth_date)
    return jsonify({'success': True, 'data': civil_data})


# ── API: Cancel member ──

@samah_bp.route('/cancel/<int:pilgrim_id>', methods=['POST'])
@require_auth
def cancel_member(pilgrim_id):
    group_id = session.get('group_id')
    pilgrim = Pilgrim.query.filter_by(id=pilgrim_id, group_id=group_id).first_or_404()

    if pilgrim.is_group_head:
        flash('برای انصراف سرگروه ابتدا سرگروه را تغییر دهید.', 'warning')
        return redirect(url_for('samah.receipt', group_id=group_id))

    iban = request.form.get('iban', '').strip()
    if not iban or len(iban) < 24:
        flash('شماره شبا معتبر نیست.', 'danger')
        return redirect(url_for('samah.receipt', group_id=group_id))

    pilgrim.iban = iban
    pilgrim.payment_status = 'cancelled'
    pilgrim.cancellation_date = datetime.utcnow()
    # Refund = insurance - penalty (10%)
    pilgrim.refund_amount = int(pilgrim.insurance_amount * 0.9)
    pilgrim.refund_date = datetime.utcnow()
    db.session.commit()

    flash(f'انصراف {pilgrim.full_name} با موفقیت ثبت شد. مبلغ {pilgrim.refund_amount:,} ریال پس از کسر خسارت به شبای ارائه شده واریز خواهد شد.', 'success')
    return redirect(url_for('samah.receipt', group_id=group_id))


# ── Helper ──

def _get_provinces():
    return [
        'تهران', 'اصفهان', 'خراسان رضوی', 'فارس', 'خوزستان',
        'مازندران', 'البرز', 'آذربایجان شرقی', 'آذربایجان غربی',
        'کرمانشاه', 'گیلان', 'لرستان', 'کرمان', 'هرمزگان',
        'سیستان و بلوچستان', 'همدان', 'گلستان', 'مرکزی', 'بوشهر',
        'زنجان', 'اردبیل', 'سمنان', 'چهارمحال و بختیاری',
        'کهگیلویه و بویراحمد', 'ایلام', 'قم', 'قزوین',
        'خراسان شمالی', 'خراسان جنوبی', 'گلستان', 'یزد'
    ]
