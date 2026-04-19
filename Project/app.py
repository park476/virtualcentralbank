import os
import random
import time
from datetime import datetime
from flask import Flask, jsonify, render_template, session, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# 1. 기본 설정 및 경로 확보
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, 
            template_folder=os.path.join(basedir, 'templates'),
            static_folder=os.path.join(basedir, 'static'))

app.secret_key = os.environ.get("SECRET_KEY", "ssack_dook_secret")

# 2. 데이터베이스 설정 (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'bank.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 3. 데이터베이스 모델 정의
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    account = db.Column(db.String(20), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True) # 계좌 활성화 상태
    history = db.relationship('History', backref='user', lazy=True, cascade="all, delete-orphan")
    portfolios = db.relationship('Portfolio', backref='user', lazy=True, cascade="all, delete-orphan")

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(20), default='일반')
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.String(20), db.ForeignKey('user.username'), nullable=False)
    author_name = db.Column(db.String(20)) # 작성자 이름 스냅샷
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_name = db.Column(db.String(100), nullable=False)
    # 답글(대댓글) 시스템을 위한 셀프 참조
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship(
        'Comment',
        backref=db.backref('parent', remote_side=[id]),
        lazy=True,
        cascade="all, delete-orphan",
        single_parent=True,
    )

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    target = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False) # 주식명
    symbol = db.Column(db.String(10), unique=True)   # 종목코드
    current_price = db.Column(db.Integer, default=10000)
    prev_price = db.Column(db.Integer, default=10000)
    listed_price = db.Column(db.Integer, default=10000)
    change_rate = db.Column(db.Float, default=0.0)
    volatility = db.Column(db.Float, default=0.03)
    is_listed = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_tick_bucket = db.Column(db.Integer, default=0)
    pending_action = db.Column(db.String(20), nullable=True)
    pending_percent = db.Column(db.Float, default=0.0)
    pending_target_price = db.Column(db.Integer, nullable=True)

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'))
    quantity = db.Column(db.Integer, default=0) 
    avg_price = db.Column(db.Integer, default=0) 
    stock = db.relationship('Stock', backref='portfolios')

def alert_back(message):
    return f"<script>alert('{message}'); history.back();</script>"

def current_user():
    username = session.get('user_id')
    if not username:
        return None
    return User.query.filter_by(username=username).first()

def require_login():
    user = current_user()
    if not user:
        return None, redirect(url_for('index'))
    if not user.is_active:
        session.pop('user_id', None)
        return None, "<script>alert('해당 계좌는 일시 정지 상태입니다.'); location.href='/';</script>"
    return user, None

def parse_positive_float(value, label='금액'):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None, f'{label}을 정확히 입력하세요.'
    if amount <= 0:
        return None, f'{label}은 0보다 커야 합니다.'
    return amount, None

def parse_positive_int(value, label='수량'):
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None, f'{label}을 정확히 입력하세요.'
    if amount <= 0:
        return None, f'{label}은 0보다 커야 합니다.'
    return amount, None

def parse_stock_price(value, label='가격'):
    price, error = parse_positive_int(value, label)
    if error:
        return None, error
    if price < 1:
        return None, f'{label}은 1 이상이어야 합니다.'
    return price, None

def generate_unique_account():
    for _ in range(100):
        account = f"110-{random.randint(100, 999)}-{random.randint(10, 99)}"
        if not User.query.filter_by(account=account).first():
            return account
    raise RuntimeError('계좌번호 생성에 실패했습니다.')

def ensure_schema_columns():
    # create_all은 기존 테이블에 새 컬럼을 추가하지 않으므로, 작은 SQLite 보강만 직접 처리합니다.
    with db.engine.connect() as conn:
        user_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(user)").fetchall()}
        post_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(post)").fetchall()}
        stock_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(stock)").fetchall()}

        if 'is_active' not in user_columns:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1")
        if 'likes' not in post_columns:
            conn.exec_driver_sql("ALTER TABLE post ADD COLUMN likes INTEGER DEFAULT 0")
        if 'prev_price' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN prev_price INTEGER DEFAULT 10000")
            conn.exec_driver_sql("UPDATE stock SET prev_price = current_price WHERE prev_price IS NULL OR prev_price = 10000")
        if 'listed_price' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN listed_price INTEGER DEFAULT 10000")
            conn.exec_driver_sql("UPDATE stock SET listed_price = current_price WHERE listed_price IS NULL OR listed_price = 10000")
        if 'volatility' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN volatility FLOAT DEFAULT 0.03")
        if 'is_listed' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN is_listed BOOLEAN DEFAULT 1")
        if 'updated_at' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN updated_at DATETIME")
        if 'last_tick_bucket' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN last_tick_bucket INTEGER DEFAULT 0")
        if 'pending_action' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN pending_action VARCHAR(20)")
        if 'pending_percent' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN pending_percent FLOAT DEFAULT 0")
        if 'pending_target_price' not in stock_columns:
            conn.exec_driver_sql("ALTER TABLE stock ADD COLUMN pending_target_price INTEGER")
        conn.commit()

def seed_default_stocks():
    stocks_data = [
        ("대한청아", "DHCA", 37050),
        ("명텐도", "MYUNG", 172000),
        ("쇼케이미디어그룹", "SKI", 9380),
        ("시나노", "SNN", 86700),
        ("와가사메트로", "WM", 35000),
        ("월본제철", "WPST", 2445),
        ("조원금융", "JF", 27900),
        ("코니", "KONY", 57100),
        ("헤라", "HERA", 3185),
        ("현성자동차", "HSM", 44800),
        ("현성전자", "HSEL", 251500),
    ]

    for name, symbol, price in stocks_data:
        stock = Stock.query.filter_by(symbol=symbol).first()
        if not stock:
            db.session.add(Stock(
                name=name,
                symbol=symbol,
                current_price=price,
                prev_price=price,
                listed_price=price,
                change_rate=0.0,
                volatility=0.03,
                is_listed=True,
                updated_at=datetime.utcnow(),
                last_tick_bucket=int(time.time() // 10),
            ))

    legacy_sample = Stock.query.filter_by(symbol='GCB001').first()
    if legacy_sample and legacy_sample.name == '가상중앙은행(GCB)' and not legacy_sample.portfolios:
        legacy_sample.is_listed = False
    db.session.commit()

def update_stock_prices():
    current_bucket = int(time.time() // 10)
    stocks = Stock.query.filter_by(is_listed=True).all()
    changed = False
    for stock in stocks:
        if (stock.last_tick_bucket or 0) >= current_bucket:
            continue

        previous_price = stock.current_price
        pending_action = stock.pending_action

        if pending_action == 'set' and stock.pending_target_price:
            stock.current_price = max(1, int(stock.pending_target_price))
        elif pending_action == 'up':
            stock.current_price = max(1, int(stock.current_price * (1 + (stock.pending_percent or 0) / 100)))
        elif pending_action == 'down':
            stock.current_price = max(1, int(stock.current_price * (1 - (stock.pending_percent or 0) / 100)))
        elif pending_action == 'reset':
            stock.current_price = max(1, int(stock.listed_price or stock.current_price))
        else:
            volatility = stock.volatility or 0.03
            change = random.uniform(-volatility, volatility)
            stock.current_price = max(1, int(stock.current_price * (1 + change)))

        stock.prev_price = max(1, int(previous_price))
        base_price = stock.prev_price or stock.listed_price or stock.current_price
        stock.change_rate = round(((stock.current_price - base_price) / base_price) * 100, 2)
        stock.updated_at = datetime.utcnow()
        stock.last_tick_bucket = current_bucket
        stock.pending_action = None
        stock.pending_percent = 0.0
        stock.pending_target_price = None
        changed = True
    if changed:
        db.session.commit()
    return stocks

def stock_payload(stock):
    return {
        'id': stock.id,
        'name': stock.name,
        'symbol': stock.symbol,
        'current_price': stock.current_price,
        'prev_price': stock.prev_price,
        'listed_price': stock.listed_price,
        'change_rate': stock.change_rate,
        'is_listed': bool(stock.is_listed),
        'pending_action': stock.pending_action,
        'pending_percent': stock.pending_percent or 0,
        'pending_target_price': stock.pending_target_price,
        'next_tick_in': max(0, 10 - int(time.time()) % 10),
        'updated_at': stock.updated_at.strftime('%H:%M:%S') if stock.updated_at else '',
    }

def generate_chart_data(stock, points=18):
    seed = sum(ord(ch) for ch in stock.symbol) + stock.current_price
    rng = random.Random(seed)
    price = max(1, stock.prev_price or stock.listed_price or stock.current_price)
    candles = []
    for index in range(points):
        drift = rng.uniform(-0.018, 0.022)
        open_price = max(1, int(price))
        close_price = max(1, int(open_price * (1 + drift)))
        high_price = max(open_price, close_price, int(max(open_price, close_price) * (1 + rng.uniform(0.003, 0.022))))
        low_price = max(1, min(open_price, close_price, int(min(open_price, close_price) * (1 - rng.uniform(0.003, 0.02)))))
        volume = rng.randint(650, 8000) * (1 + index // 6)
        candles.append({
            'label': f'{index + 1}일',
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume,
        })
        price = close_price

    if candles:
        candles[-1]['close'] = stock.current_price
        candles[-1]['high'] = max(candles[-1]['high'], stock.current_price)
        candles[-1]['low'] = min(candles[-1]['low'], stock.current_price)
    return candles

def build_orderbook(stock):
    price = stock.current_price
    ask_prices = [max(1, int(price * (1 + rate))) for rate in (0.012, 0.009, 0.006, 0.003)]
    bid_prices = [max(1, int(price * (1 - rate))) for rate in (0.003, 0.006, 0.009, 0.012)]
    return {
        'asks': [{'price': ask_price, 'quantity': random.randint(600, 28000)} for ask_price in ask_prices],
        'bids': [{'price': bid_price, 'quantity': random.randint(600, 28000)} for bid_price in bid_prices],
    }

# 4. DB 초기화 및 관리자 생성 로직
with app.app_context():
    db.create_all()
    ensure_schema_columns()
    if not User.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash('1q2w3e4r!')
        admin = User(
            username='admin', password=hashed_pw, name='관리자', 
            account='110-000-00', balance=1000000.0
        )
        db.session.add(admin)
        db.session.commit()
    seed_default_stocks()

# --- 라우팅: 메인 및 계정 관련 ---

@app.route('/')
def index():
    is_logged_in = 'user_id' in session
    return render_template('index.html', is_logged_in=is_logged_in)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return redirect(url_for('index'))

    uid = (request.form.get('user_id') or '').strip()
    upw = request.form.get('pw') or ''
    user = User.query.filter_by(username=uid).first()
    
    if user and check_password_hash(user.password, upw):
        if not user.is_active:
            return alert_back('해당 계좌는 일시 정지 상태입니다.')
        session['user_id'] = uid
        return redirect(url_for('index')) 
    return alert_back('아이디 또는 비밀번호를 확인하십시오.')

@app.route('/register', methods=['POST'])
def register():
    uid = (request.form.get('user_id') or '').strip()
    upw = request.form.get('pw') or ''
    uname = (request.form.get('name') or '').strip()

    if not uid or not upw or not uname:
        return alert_back('모든 항목을 입력해주세요.')
    
    if User.query.filter_by(username=uid).first():
        return alert_back('이미 존재하는 아이디입니다.')
    
    new_acc = generate_unique_account()
    hashed_pw = generate_password_hash(upw)
    new_user = User(username=uid, password=hashed_pw, name=uname, account=new_acc, balance=1000.0)
    db.session.add(new_user)
    db.session.commit()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.session.add(History(date=now, type='입금', target='가입 축하금', amount=1000.0, user_id=new_user.id))
    db.session.commit()
    return "<script>alert('계좌 개설 성공! 1,000 NAD가 입금되었습니다.'); location.href='/';</script>"

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    user, response = require_login()
    if response:
        return response
    return render_template('dashboard.html', user=user)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

# --- 라우팅: 커뮤니티 (대댓글 기능 포함) ---

@app.route('/community')
def community():
    user, response = require_login()
    if response:
        return response
    cat = request.args.get('cat', '전체')
    if cat == '전체':
        posts = Post.query.order_by(Post.date_posted.desc()).all()
    else:
        posts = Post.query.filter_by(category=cat).order_by(Post.date_posted.desc()).all()
    return render_template('community.html', posts=posts, current_cat=cat)

@app.route('/community/write', methods=['POST']) 
def write_post():
    user, response = require_login()
    if response:
        return response
    title = (request.form.get('title') or '').strip()
    content = (request.form.get('content') or '').strip()
    category = (request.form.get('category') or '').strip()
    if not title or not content or category not in {'정보', '질문', '자유'}:
        return alert_back('게시글 내용을 확인해주세요.')
    new_post = Post(
        title=title,
        content=content,
        category=category,
        author_id=user.username,
        author_name=user.name
    )
    db.session.add(new_post)
    db.session.commit()
    return redirect('/community')

@app.route('/community/post/<int:post_id>')
def view_post(post_id):
    curr_user, response = require_login()
    if response:
        return response
    post = Post.query.get_or_404(post_id)
    post.views += 1
    db.session.commit()
    return render_template('post_view.html', post=post, user=curr_user)

@app.route('/community/post/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    user, response = require_login()
    if response:
        return response
    post = Post.query.get_or_404(post_id)
    content = (request.form.get('content') or '').strip()
    parent_id = request.form.get('parent_id')
    
    if content:
        parent = None
        if parent_id:
            parent = Comment.query.filter_by(id=parent_id, post_id=post.id).first()
            if not parent:
                return alert_back('답글 대상 댓글을 찾을 수 없습니다.')
        new_comment = Comment(
            content=content,
            post_id=post_id,
            author_name=user.name,
            parent=parent
        )
        db.session.add(new_comment)
        db.session.commit()
    return redirect(f'/community/post/{post_id}')

# --- 라우팅: 송금 및 랭킹 ---

@app.route('/send_money', methods=['POST'])
def send_money():
    sender, response = require_login()
    if response:
        return response
    receiver_acc = (request.form.get('receiver_acc') or '').strip()
    amount, error = parse_positive_float(request.form.get('amount'))
    if error:
        return alert_back(error)

    receiver = User.query.filter_by(account=receiver_acc).first()
    if not receiver:
        return alert_back('존재하지 않는 계좌입니다.')
    if not receiver.is_active:
        return alert_back('정지된 계좌로는 송금할 수 없습니다.')
    if sender.account == receiver_acc:
        return alert_back('본인에게는 송금할 수 없습니다.')
    if sender.balance < amount:
        return alert_back('잔액이 부족합니다.')

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sender.balance -= amount
    receiver.balance += amount
    db.session.add(History(date=now, type='출금', target=f"{receiver.name}", amount=-amount, user_id=sender.id))
    db.session.add(History(date=now, type='입금', target=f"{sender.name}", amount=amount, user_id=receiver.id))
    db.session.commit()
    return "<script>alert('송금 완료!'); location.href='/dashboard';</script>"

@app.route('/ranking')
def ranking():
    rankings = User.query.filter(User.username != 'admin').order_by(User.balance.desc()).limit(100).all()
    return render_template('ranking.html', rankings=rankings)

# --- 라우팅: 증권 거래소 (Stock Market) ---

@app.route('/market')
def market():
    user, response = require_login()
    if response:
        return response

    update_stock_prices()
    listed_stocks = Stock.query.filter_by(is_listed=True).order_by(Stock.name.asc()).all()
    portfolios = Portfolio.query.filter_by(user_id=user.id).all()
    portfolio_map = {portfolio.stock_id: portfolio for portfolio in portfolios}
    owned_unlisted = (
        Stock.query
        .filter(Stock.id.in_(portfolio_map.keys()), Stock.is_listed == False)
        .order_by(Stock.name.asc())
        .all()
        if portfolio_map else []
    )
    stocks = listed_stocks + owned_unlisted
    if not stocks:
        return "시장 데이터가 존재하지 않습니다. 관리자에게 문의하세요."

    selected_symbol = (request.args.get('stock') or stocks[0].symbol).upper()
    selected_stock = next((stock for stock in stocks if stock.symbol == selected_symbol), stocks[0])
    selected_portfolio = portfolio_map.get(selected_stock.id)
    chart_data = generate_chart_data(selected_stock)
    orderbook = build_orderbook(selected_stock)
    recent_trades = [
        {
            'price': max(1, int(selected_stock.current_price * (1 + random.uniform(-0.01, 0.01)))),
            'quantity': random.randint(1, 95),
            'time': datetime.now().strftime('%H:%M:%S'),
        }
        for _ in range(10)
    ]
    return render_template(
        'exchange.html',
        stocks=stocks,
        stock=selected_stock,
        user=user,
        portfolio=selected_portfolio,
        portfolio_map=portfolio_map,
        chart_data=chart_data,
        orderbook=orderbook,
        recent_trades=recent_trades,
    )

@app.route('/api/stocks/tick')
def api_stock_tick():
    user, response = require_login()
    if response:
        return jsonify({'error': 'login_required'}), 401
    stocks = update_stock_prices()
    return jsonify({'stocks': [stock_payload(stock) for stock in stocks]})

@app.route('/api/admin/stocks')
def api_admin_stocks():
    if session.get('user_id') != 'admin':
        return jsonify({'error': 'admin_required'}), 403
    update_stock_prices()
    stocks = Stock.query.order_by(Stock.name.asc()).all()
    return jsonify({'stocks': [stock_payload(stock) for stock in stocks]})

@app.route('/market/trade', methods=['POST'])
def trade_stock():
    user, response = require_login()
    if response:
        return response

    stock = Stock.query.get_or_404(request.form.get('stock_id'))
    mode = request.form.get('mode')
    quantity, error = parse_positive_int(request.form.get('quantity'), '주문 수량')
    if error:
        return alert_back(error)

    price = stock.current_price
    total = price * quantity
    portfolio = Portfolio.query.filter_by(user_id=user.id, stock_id=stock.id).first()

    if mode == 'buy':
        if not stock.is_listed:
            return alert_back('상장 중인 종목만 매수할 수 있습니다.')
        if user.balance < total:
            return alert_back('주문 가능 금액이 부족합니다.')
        if not portfolio:
            portfolio = Portfolio(user_id=user.id, stock_id=stock.id, quantity=0, avg_price=0)
            db.session.add(portfolio)
        new_total_cost = portfolio.avg_price * portfolio.quantity + total
        portfolio.quantity += quantity
        portfolio.avg_price = int(new_total_cost / portfolio.quantity)
        user.balance -= total
        history_type = '주식매수'
        history_amount = -total
    elif mode == 'sell':
        if not portfolio or portfolio.quantity < quantity:
            return alert_back('보유 수량이 부족합니다.')
        portfolio.quantity -= quantity
        user.balance += total
        history_type = '주식매도'
        history_amount = total
        if portfolio.quantity == 0:
            portfolio.avg_price = 0
    else:
        return alert_back('주문 정보를 확인해주세요.')

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.session.add(History(date=now, type=history_type, target=f"{stock.name}({stock.symbol})", amount=history_amount, user_id=user.id))
    db.session.commit()
    return f"<script>alert('주문이 처리되었습니다.'); location.href='/market?stock={stock.symbol}';</script>"

# --- 라우팅: 관리자 패널 (Admin) ---

@app.route('/admin')
def admin_panel():
    if session.get('user_id') != 'admin':
        return "<script>alert('권한이 없습니다.'); location.href='/';</script>"
    users = User.query.all()
    user_dict = { u.username: u for u in users } # 템플릿 호환용
    return render_template('admin.html', 
                           users=user_dict, 
                           user_count=len(users), 
                           total_balance=sum(u.balance for u in users))

@app.route('/admin/stock')
def admin_stock_panel():
    if session.get('user_id') != 'admin':
        return "<script>alert('권한이 없습니다.'); location.href='/';</script>"
    stocks = Stock.query.order_by(Stock.name.asc()).all()
    return render_template('admin_stock.html', stocks=stocks)

@app.route('/admin/stock/create', methods=['POST'])
def admin_stock_create():
    if session.get('user_id') != 'admin':
        return redirect('/')

    name = (request.form.get('name') or '').strip()
    symbol = (request.form.get('symbol') or '').strip().upper()
    price, error = parse_stock_price(request.form.get('listed_price'), '상장 시작금액')
    if error:
        return alert_back(error)
    if not name or not symbol:
        return alert_back('종목명과 종목코드를 입력해주세요.')
    if Stock.query.filter_by(symbol=symbol).first():
        return alert_back('이미 존재하는 종목코드입니다.')

    db.session.add(Stock(
        name=name,
        symbol=symbol,
        current_price=price,
        prev_price=price,
        listed_price=price,
        change_rate=0.0,
        volatility=0.03,
        is_listed=True,
        updated_at=datetime.utcnow(),
    ))
    db.session.commit()
    return redirect(url_for('admin_stock_panel'))

@app.route('/admin/stock/update/<int:stock_id>', methods=['POST'])
def admin_stock_update(stock_id):
    if session.get('user_id') != 'admin':
        return redirect('/')

    stock = Stock.query.get_or_404(stock_id)
    new_price, error = parse_stock_price(request.form.get('current_price'), '현재가')
    if error:
        return alert_back(error)

    listed_price, listed_error = parse_stock_price(request.form.get('listed_price'), '상장 시작금액')
    if listed_error:
        return alert_back(listed_error)

    volatility, volatility_error = parse_positive_float(request.form.get('volatility'), '변동폭')
    if volatility_error:
        return alert_back(volatility_error)

    stock.name = (request.form.get('name') or stock.name).strip()
    stock.listed_price = listed_price
    stock.volatility = min(volatility / 100, 0.5)
    stock.is_listed = request.form.get('is_listed') == 'on'
    if new_price != stock.current_price:
        stock.pending_action = 'set'
        stock.pending_target_price = new_price
        stock.pending_percent = 0.0
    db.session.commit()
    return redirect(url_for('admin_stock_panel'))

@app.route('/admin/stock/tick', methods=['POST'])
def admin_stock_tick():
    if session.get('user_id') != 'admin':
        return redirect('/')
    update_stock_prices()
    return redirect(url_for('admin_stock_panel'))

@app.route('/admin/stock/adjust/<int:stock_id>', methods=['POST'])
def admin_stock_adjust(stock_id):
    if session.get('user_id') != 'admin':
        return redirect('/')

    stock = Stock.query.get_or_404(stock_id)
    action = request.form.get('action')
    percent, error = parse_positive_float(request.form.get('percent', 0), '조정률')
    if error and action != 'reset':
        return alert_back(error)

    if action in {'up', 'down'}:
        stock.pending_action = action
        stock.pending_percent = percent
        stock.pending_target_price = None
    elif action == 'reset':
        stock.pending_action = 'reset'
        stock.pending_percent = 0.0
        stock.pending_target_price = None
    else:
        return alert_back('조작 방식을 선택해주세요.')
    db.session.commit()
    return redirect(url_for('admin_stock_panel'))

@app.route('/admin/action/<uid>', methods=['POST'])
def admin_action(uid):
    if session.get('user_id') != 'admin': return redirect('/')
    user = User.query.filter_by(username=uid).first()
    if not user:
        return alert_back('존재하지 않는 사용자입니다.')
    action = request.form.get('action')
    
    if action == 'adjust':
        try:
            amount = float(request.form.get('amount', 0))
        except (TypeError, ValueError):
            return alert_back('올바른 금액을 입력하세요.')
        user.balance += amount
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.session.add(History(date=now, type='관리자조정', target='운영', amount=amount, user_id=user.id))
    elif action == 'toggle_status':
        user.is_active = not user.is_active
    
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<uid>', methods=['POST'])
def admin_delete(uid):
    if session.get('user_id') != 'admin': return redirect('/')
    if uid == 'admin': return "<script>alert('관리자 삭제 불가'); history.back();</script>"
    user = User.query.filter_by(username=uid).first()
    if user:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(debug=True)
