import json
from datetime import datetime
from functools import wraps

from flask import (render_template, request, session, redirect, url_for,
                   flash, jsonify)
from werkzeug.security import generate_password_hash

from models import db, AdminUser, Border, SystemSetting, PilgrimGroup, Pilgrim, TrafficHistory
from . import admin_bp


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('samahadmin.login'))
        return f(*args, **kwargs)
    return decorated


def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('samahadmin.login'))
        if session.get('admin_role') not in ('superadmin', 'admin'):
            flash('دسترسی کافی ندارید.', 'danger')
            return redirect(url_for('samahadmin.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Auth ──

@admin_bp.route('/', methods=['GET', 'POST'])
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('samahadmin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = AdminUser.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            session['admin_logged_in'] = True
            session['admin_id'] = user.id
            session['admin_username'] = user.username
            session['admin_role'] = user.role
            session['admin_full_name'] = user.full_name or user.username
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('samahadmin.dashboard'))
        flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')

    return render_template('admin_login.html')


@admin_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('samahadmin.login'))


# ── Dashboard ──

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    total_groups = PilgrimGroup.query.filter_by(status='paid').count()
    total_pilgrims = Pilgrim.query.filter_by(payment_status='paid').count()
    total_revenue = db.session.query(db.func.sum(PilgrimGroup.total_amount)).filter_by(status='paid').scalar() or 0
    recent_groups = PilgrimGroup.query.filter_by(status='paid').order_by(PilgrimGroup.payment_date.desc()).limit(10).all()

    border_stats = db.session.query(
        Border.name_fa,
        db.func.count(PilgrimGroup.id)
    ).join(PilgrimGroup, PilgrimGroup.exit_border_id == Border.id).filter(
        PilgrimGroup.status == 'paid'
    ).group_by(Border.id).all()

    return render_template('dashboard.html',
                           total_groups=total_groups,
                           total_pilgrims=total_pilgrims,
                           total_revenue=total_revenue,
                           recent_groups=recent_groups,
                           border_stats=border_stats)


# ── Settings ──

@admin_bp.route('/settings', methods=['GET', 'POST'])
@superadmin_required
def settings():
    if request.method == 'POST':
        keys = [
            'max_group_size', 'insurance_amount', 'max_stay_days',
            'departure_start', 'departure_end', 'arbaeen_date',
            'registration_open', 'site_message',
            'insurer_name', 'insurer_contact', 'emergency_number',
            'insurance_terms', 'card_year', 'card_recommendations',
        ]
        for key in keys:
            val = request.form.get(key, '')
            SystemSetting.set(key, val)
        flash('تنظیمات با موفقیت ذخیره شد.', 'success')
        return redirect(url_for('samahadmin.settings'))

    settings_data = {
        'max_group_size': SystemSetting.get('max_group_size', '10'),
        'insurance_amount': SystemSetting.get('insurance_amount', '500000'),
        'max_stay_days': SystemSetting.get('max_stay_days', '10'),
        'departure_start': SystemSetting.get('departure_start', ''),
        'departure_end': SystemSetting.get('departure_end', ''),
        'arbaeen_date': SystemSetting.get('arbaeen_date', ''),
        'registration_open': SystemSetting.get('registration_open', 'true'),
        'site_message': SystemSetting.get('site_message', ''),
        'insurer_name': SystemSetting.get('insurer_name', 'بیمه ایران'),
        'insurer_contact': SystemSetting.get('insurer_contact', '۰۹۶۶۸'),
        'emergency_number': SystemSetting.get('emergency_number', '۱۲۸'),
        'insurance_terms': SystemSetting.get('insurance_terms', ''),
        'card_year': SystemSetting.get('card_year', '۱۴۰۵'),
        'card_recommendations': SystemSetting.get('card_recommendations', ''),
    }
    return render_template('settings.html', s=settings_data)


# ── Borders ──

@admin_bp.route('/borders', methods=['GET', 'POST'])
@superadmin_required
def borders():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            b = Border(
                name=request.form.get('name', ''),
                name_fa=request.form.get('name_fa', ''),
                border_type=request.form.get('border_type', 'land'),
                is_active=request.form.get('is_active') == 'on',
                is_exit=request.form.get('is_exit') == 'on',
                is_entry=request.form.get('is_entry') == 'on',
                max_daily_capacity=int(request.form.get('max_daily_capacity', 0) or 0),
                display_order=int(request.form.get('display_order', 0) or 0),
            )
            db.session.add(b)
            db.session.commit()
            flash('مرز با موفقیت اضافه شد.', 'success')
        elif action == 'edit':
            bid = int(request.form.get('border_id', 0))
            b = Border.query.get(bid)
            if b:
                b.name = request.form.get('name', b.name)
                b.name_fa = request.form.get('name_fa', b.name_fa)
                b.border_type = request.form.get('border_type', b.border_type)
                b.is_active = request.form.get('is_active') == 'on'
                b.is_exit = request.form.get('is_exit') == 'on'
                b.is_entry = request.form.get('is_entry') == 'on'
                b.max_daily_capacity = int(request.form.get('max_daily_capacity', 0) or 0)
                b.display_order = int(request.form.get('display_order', 0) or 0)
                db.session.commit()
                flash('مرز با موفقیت ویرایش شد.', 'success')
        elif action == 'toggle':
            bid = int(request.form.get('border_id', 0))
            b = Border.query.get(bid)
            if b:
                b.is_active = not b.is_active
                db.session.commit()
        return redirect(url_for('samahadmin.borders'))

    all_borders = Border.query.order_by(Border.display_order).all()
    return render_template('borders.html', borders=all_borders)


# ── Admin Users ──

@admin_bp.route('/users', methods=['GET', 'POST'])
@superadmin_required
def admin_users():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            if AdminUser.query.filter_by(username=request.form.get('username')).first():
                flash('این نام کاربری قبلاً وجود دارد.', 'danger')
            else:
                u = AdminUser(
                    username=request.form.get('username', ''),
                    email=request.form.get('email', ''),
                    full_name=request.form.get('full_name', ''),
                    role=request.form.get('role', 'operator'),
                    is_active=True,
                )
                u.set_password(request.form.get('password', ''))
                db.session.add(u)
                db.session.commit()
                flash('کاربر با موفقیت اضافه شد.', 'success')
        elif action == 'toggle':
            uid = int(request.form.get('user_id', 0))
            u = AdminUser.query.get(uid)
            if u and u.id != session['admin_id']:
                u.is_active = not u.is_active
                db.session.commit()
        elif action == 'reset_password':
            uid = int(request.form.get('user_id', 0))
            u = AdminUser.query.get(uid)
            if u:
                u.set_password(request.form.get('new_password', ''))
                db.session.commit()
                flash('رمز عبور با موفقیت تغییر یافت.', 'success')
        return redirect(url_for('samahadmin.admin_users'))

    users = AdminUser.query.order_by(AdminUser.created_at.desc()).all()
    return render_template('admin_users.html', users=users)


# ── Registrations Report ──

@admin_bp.route('/registrations')
@admin_required
def registrations():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    q = request.args.get('q', '')
    status_filter = request.args.get('status', '')
    border_filter = request.args.get('border_id', '', type=str)

    query = PilgrimGroup.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if border_filter:
        query = query.filter_by(exit_border_id=int(border_filter))
    if q:
        query = query.join(Pilgrim, Pilgrim.group_id == PilgrimGroup.id).filter(
            db.or_(
                Pilgrim.national_id.contains(q),
                Pilgrim.first_name.contains(q),
                Pilgrim.last_name.contains(q),
                PilgrimGroup.group_code.contains(q),
            )
        )

    pagination = query.order_by(PilgrimGroup.created_at.desc()).paginate(page=page, per_page=per_page)
    borders = Border.query.filter_by(is_active=True).all()
    return render_template('registrations.html', pagination=pagination,
                           borders=borders, q=q, status_filter=status_filter,
                           border_filter=border_filter)


@admin_bp.route('/registrations/<int:group_id>')
@admin_required
def registration_detail(group_id):
    group = PilgrimGroup.query.get_or_404(group_id)
    members = Pilgrim.query.filter_by(group_id=group.id).all()
    plates = json.loads(group.vehicle_plates or '[]')
    return render_template('registration_detail.html', group=group, members=members, plates=plates)


# ── Traffic Data Management ──

@admin_bp.route('/traffic', methods=['GET', 'POST'])
@superadmin_required
def traffic():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            t = TrafficHistory(
                year=int(request.form.get('year', 0)),
                day_number=int(request.form.get('day_number', 0)),
                shamsi_date=request.form.get('shamsi_date', ''),
                count=int(request.form.get('count', 0)),
                is_current_year=request.form.get('is_current_year') == 'on',
            )
            db.session.add(t)
            db.session.commit()
            flash('داده ترافیکی اضافه شد.', 'success')
        elif action == 'bulk_import':
            data_json = request.form.get('data_json', '')
            try:
                rows = json.loads(data_json)
                for row in rows:
                    t = TrafficHistory(
                        year=row.get('year', 0),
                        day_number=row.get('day', 0),
                        shamsi_date=row.get('date', ''),
                        count=row.get('count', 0),
                        is_current_year=row.get('current', False),
                    )
                    db.session.add(t)
                db.session.commit()
                flash(f'{len(rows)} رکورد وارد شد.', 'success')
            except Exception as e:
                flash(f'خطا در وارد کردن داده: {e}', 'danger')
        return redirect(url_for('samahadmin.traffic'))

    records = TrafficHistory.query.order_by(TrafficHistory.year, TrafficHistory.day_number).all()
    return render_template('traffic.html', records=records)


# ── Reports ──

@admin_bp.route('/reports')
@admin_required
def reports():
    # Border distribution
    border_data = db.session.query(
        Border.name_fa,
        db.func.count(PilgrimGroup.id).label('cnt')
    ).outerjoin(PilgrimGroup, PilgrimGroup.exit_border_id == Border.id).filter(
        PilgrimGroup.status == 'paid'
    ).group_by(Border.id).all()

    # Province distribution
    province_data = db.session.query(
        PilgrimGroup.province,
        db.func.count(PilgrimGroup.id).label('cnt')
    ).filter_by(status='paid').group_by(PilgrimGroup.province).order_by(db.desc('cnt')).limit(15).all()

    # Daily registrations
    daily_data = db.session.query(
        PilgrimGroup.payment_date,
        db.func.count(PilgrimGroup.id).label('cnt')
    ).filter_by(status='paid').group_by(
        db.func.date(PilgrimGroup.payment_date)
    ).order_by(PilgrimGroup.payment_date).all()

    # Transport breakdown
    transport_data = db.session.query(
        PilgrimGroup.transport_to_border,
        db.func.count(PilgrimGroup.id).label('cnt')
    ).filter_by(status='paid').group_by(PilgrimGroup.transport_to_border).all()

    transport_labels = {
        'personal': 'شخصی', 'bus': 'اتوبوس', 'minibus': 'مینی بوس',
        'taxi': 'تاکسی', 'train': 'قطار'
    }

    return render_template('reports.html',
                           border_data=json.dumps([{'name': r[0], 'count': r[1]} for r in border_data]),
                           province_data=json.dumps([{'name': r[0] or 'نامشخص', 'count': r[1]} for r in province_data]),
                           daily_data=json.dumps([{'date': str(r[0])[:10] if r[0] else '', 'count': r[1]} for r in daily_data]),
                           transport_data=json.dumps([{'name': transport_labels.get(r[0], r[0] or 'نامشخص'), 'count': r[1]} for r in transport_data]))


# ── API ──

@admin_bp.route('/api/stats')
@admin_required
def api_stats():
    return jsonify({
        'total_groups': PilgrimGroup.query.filter_by(status='paid').count(),
        'total_pilgrims': Pilgrim.query.filter_by(payment_status='paid').count(),
        'pending': PilgrimGroup.query.filter_by(status='pending_payment').count(),
        'total_revenue': db.session.query(db.func.sum(PilgrimGroup.total_amount)).filter_by(status='paid').scalar() or 0,
    })
