import os
import random
from datetime import datetime
from flask import Flask, render_template, session, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# 1. 기본 설정
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, 
            template_folder=os.path.join(basedir, 'templates'),
            static_folder=os.path.join(basedir, 'static'))

app.secret_key = "ssack_dook_secret"

# 2. DB 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'bank.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 3. DB 모델 정의
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    account = db.Column(db.String(20), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)
    # [추가] 계좌 활성화 상태 (기본값 True)
    is_active = db.Column(db.Boolean, default=True) 
    history = db.relationship('History', backref='user', lazy=True, cascade="all, delete-orphan")

# 데이터베이스 모델 추가 (기존 User 모델 아래에 배치)
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(20), default='일반')
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.String(20), db.ForeignKey('user.username'), nullable=False)
    author_name = db.Column(db.String(20)) # 작성자 이름 스냅샷
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    comments = db.relationship('Comment', backref='post', lazy=True)

# 1. 댓글 모델 수정 (parent_id 추가)
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_name = db.Column(db.String(100), nullable=False)
    
    # 답글을 위한 셀프 참조 설정
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True, cascade="all, delete-orphan")

# 2. 댓글 작성 라우트 수정
@app.route('/community/post/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    if 'user_id' not in session: return redirect('/login')
    
    content = request.form.get('content')
    parent_id = request.form.get('parent_id') # 답글일 경우 부모 ID가 넘어옴
    
    if content:
        user = User.query.filter_by(username=session['user_id']).first()
        new_comment = Comment(
            content=content,
            post_id=post_id,
            author_name=user.name,
            parent_id=parent_id if parent_id else None
        )
        db.session.add(new_comment)
        db.session.commit()
    
    return redirect(f'/community/post/{post_id}')

# 커뮤니티 메인 페이지
# 커뮤니티 메인 및 카테고리 필터링
@app.route('/community')
def community():
    if 'user_id' not in session: return redirect('/login')
    
    cat = request.args.get('cat', '전체') # URL 파라미터에서 카테고리 가져오기
    
    if cat == '전체':
        posts = Post.query.order_by(Post.date_posted.desc()).all()
    else:
        posts = Post.query.filter_by(category=cat).order_by(Post.date_posted.desc()).all()
        
    return render_template('community.html', posts=posts, current_cat=cat)

# 글쓰기 처리
# ✅ methods=['POST']가 반드시 포함되어야 합니다!
@app.route('/community/write', methods=['POST']) 
def write_post():
    if 'user_id' not in session: return redirect('/login')
    # ... 나머지 코드
    user = User.query.filter_by(username=session['user_id']).first()
    
    new_post = Post(
        title=request.form.get('title'),
        content=request.form.get('content'),
        category=request.form.get('category'),
        author_id=user.username,
        author_name=user.name
    )
    db.session.add(new_post)
    db.session.commit()
    return redirect('/community')

# 게시글 상세보기
@app.route('/community/post/<int:post_id>')
def view_post(post_id):
    if 'user_id' not in session: return redirect('/login')
    
    post = Post.query.get_or_404(post_id)
    post.views += 1
    db.session.commit()
    
    # 현재 로그인한 유저 객체를 가져와서 넘겨줘야 합니다.
    curr_user = User.query.filter_by(username=session['user_id']).first()
    return render_template('post_view.html', post=post, user=curr_user)


class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    target = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# 4. 초기 관리자 생성 및 DB 초기화
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash('1q2w3e4r!')
        admin = User(
            username='admin', 
            password=hashed_pw, 
            name='관리자', 
            account='110-000-00', 
            balance=1000000.0
        )
        db.session.add(admin)
        db.session.commit()
        print("관리자 계정이 성공적으로 생성되었습니다.")

# --- 라우팅 기능 ---

@app.route('/')
def index():
    # 로그인 여부를 index.html에 전달하면 더 스마트한 대응이 가능합니다.
    is_logged_in = 'user_id' in session
    return render_template('index.html', is_logged_in=is_logged_in)

@app.route('/login', methods=['POST'])
def login():
    uid = request.form.get('user_id')
    upw = request.form.get('pw')
    
    user = User.query.filter_by(username=uid).first()
    
    if user and check_password_hash(user.password, upw):
        if not user.is_active:
            return "<script>alert('해당 계좌는 일시 정지 상태입니다. 관리자에게 문의하세요.'); history.back();</script>"
            
        session['user_id'] = uid
        # [수정] dashboard가 아니라 index(메인 화면)로 리다이렉트합니다.
        return redirect(url_for('index')) 
    
    return "<script>alert('아이디 또는 비밀번호를 확인하십시오.'); history.back();</script>"

@app.route('/register', methods=['POST'])
def register():
    # registerModal의 name 속성에 맞춤
    uid = request.form.get('user_id')
    upw = request.form.get('pw')
    uname = request.form.get('name')
    
    if not uid or not upw or not uname:
        return "<script>alert('모든 항목을 입력해주세요.'); history.back();</script>"
    
    if User.query.filter_by(username=uid).first():
        return "<script>alert('이미 존재하는 아이디입니다.'); history.back();</script>"
    
    # 계좌번호 자동 생성
    new_acc = f"110-{random.randint(100, 999)}-{random.randint(10, 99)}"
    
    # 비밀번호 해싱 및 가입 축하금 1,000 NAD 지급
    hashed_pw = generate_password_hash(upw)
    new_user = User(
        username=uid, 
        password=hashed_pw, 
        name=uname, 
        account=new_acc, 
        balance=1000.0  # 축하금 반영
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    # 가입 축하금 내역 추가
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    welcome_history = History(
        date=now, type='입금', target='가입 축하금', amount=1000.0, user_id=new_user.id
    )
    db.session.add(welcome_history)
    db.session.commit()
    
    return "<script>alert('계좌 개설 성공! 1,000 NAD가 입금되었습니다.'); location.href='/';</script>"

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user = User.query.filter_by(username=session['user_id']).first()
    return render_template('dashboard.html', user=user)

@app.route('/send_money', methods=['POST'])
def send_money():
    if 'user_id' not in session: return redirect('/')
    
    sender = User.query.filter_by(username=session['user_id']).first()
    receiver_acc = request.form.get('receiver_acc')
    try:
        amount = float(request.form.get('amount'))
    except:
        return "<script>alert('금액을 정확히 입력하세요.'); history.back();</script>"

    receiver = User.query.filter_by(account=receiver_acc).first()
    
    if not receiver:
        return "<script>alert('존재하지 않는 계좌입니다.'); history.back();</script>"
    if sender.balance < amount:
        return "<script>alert('잔액이 부족합니다.'); history.back();</script>"
    if sender.account == receiver_acc:
        return "<script>alert('본인에게는 송금할 수 없습니다.'); history.back();</script>"

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    sender.balance -= amount
    receiver.balance += amount
    
    sender_h = History(date=now, type='출금', target=f"{receiver.name}({receiver.account})", amount=-amount, user_id=sender.id)
    receiver_h = History(date=now, type='입금', target=f"{sender.name}({sender.account})", amount=amount, user_id=receiver.id)
    
    db.session.add_all([sender_h, receiver_h])
    db.session.commit()
    
    return "<script>alert('송금 완료!'); location.href='/dashboard';</script>"

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

# --- 관리자 패널 기능 ---
@app.route('/admin')
def admin_panel():
    if session.get('user_id') != 'admin':
        return "<script>alert('관리자 전용 페이지입니다.'); location.href='/';</script>"
    
    users = User.query.all()
    user_count = len(users)
    total_balance = sum(u.balance for u in users)
    
    # HTML의 {% for uid, info in users.items() %} 구조에 맞게 딕셔너리 전달
    user_dict = { u.username: u for u in users }
    
    return render_template('admin.html', 
                           users=user_dict, 
                           user_count=user_count, 
                           total_balance=total_balance)

@app.route('/admin/action/<uid>', methods=['POST'])
def admin_action(uid):
    if session.get('user_id') != 'admin':
        return redirect('/')
    
    user = User.query.filter_by(username=uid).first()
    if not user:
        return "<script>alert('존재하지 않는 사용자입니다.'); history.back();</script>"

    action = request.form.get('action')
    
    # 1. 금액 조정 기능 (HTML의 name="amount" 참조)
    if action == 'adjust':
        try:
            amount = float(request.form.get('amount', 0))
            user.balance += amount
            
            # 관리자 조정 내역 추가 (기능 손실 방지)
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            adj_h = History(date=now, type='관리자조정', 
                            target='중앙은행(운영)', amount=amount, user_id=user.id)
            db.session.add(adj_h)
        except ValueError:
            return "<script>alert('올바른 금액을 입력하세요.'); history.back();</script>"
        
    # 2. 계좌 상태 변경 기능 (정지/해제)
    elif action == 'toggle_status':
        # User 모델에 is_active 컬럼이 있어야 작동합니다.
        user.is_active = not getattr(user, 'is_active', True)
        
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<uid>', methods=['POST'])
def admin_delete(uid):
    if session.get('user_id') != 'admin':
        return redirect('/')
    
    # 본인(admin) 삭제 방지
    if uid == 'admin':
        return "<script>alert('관리자 본인은 삭제할 수 없습니다.'); history.back();</script>"

    user = User.query.filter_by(username=uid).first()
    if user:
        db.session.delete(user)
        db.session.commit()
        return redirect(url_for('admin_panel'))
    
    return "<script>alert('존재하지 않는 사용자입니다.'); history.back();</script>"

@app.route('/ranking')
def ranking():
    rankings = User.query.filter(User.username != 'admin').order_by(User.balance.desc()).limit(100).all()
    
    return render_template('ranking.html', rankings=rankings)

if __name__ == '__main__':
    app.run(debug=True)

#주식시장 기능

@app.route('/market')
def market():
    # 임시로 첫 번째 주식 데이터를 가져오거나, 전체 주식 리스트를 보여줍니다.
    # 만약 Stock 모델이 없다면 앞서 제가 드린 모델 코드를 적용해야 합니다!
    stock = Stock.query.first() 
    return render_template('exchange.html', stock=stock)

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False) # 주식명
    symbol = db.Column(db.String(10), unique=True)   # 종목코드 (예: GCB001)
    current_price = db.Column(db.Integer, default=10000)
    change_rate = db.Column(db.Float, default=0.0)

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'))
    quantity = db.Column(db.Integer, default=0) # 보유 수량
    avg_price = db.Column(db.Integer, default=0) # 평단가