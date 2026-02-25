from flask import Flask, render_template, request, redirect, url_for, session
import json
import os
import random
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'nad_secret_key_1234'
DB_FILE = "bank_db.json"

# --- [핵심] 데이터 관리 함수들 ---
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- [웹 경로 설정] ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    users = load_data()
    user_id = request.form.get('user_id')
    pw = request.form.get('pw')

    if user_id in users and check_password_hash(users[user_id]['pw'], pw):
        # [추가] 계좌 정지 여부 확인
        if not users[user_id].get('is_active', True):
            return "<script>alert('정지된 계좌입니다. 관리자에게 문의하세요.'); history.back();</script>"
        
        session['user_id'] = user_id
        return redirect(url_for('dashboard'))
    else:
        return "<script>alert('아이디 또는 비번이 틀렸습니다.'); history.back();</script>"
    
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    users = load_data()
    user_info = users[session['user_id']]
    return render_template('dashboard.html', user=user_info)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/send_money', methods=['POST'])
def send_money():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    users = load_data()
    me_id = session['user_id']
    
    # [추가] 내 계좌가 정지 상태인지 확인
    if not users[me_id].get('is_active', True):
        return "<script>alert('정지된 계좌로는 송금할 수 없습니다.'); history.back();</script>"

    receiver_acc = request.form.get('receiver_acc')
    amount = int(request.form.get('amount', 0))

    # 1. 상대방 찾기
    receiver_id = next((uid for uid, info in users.items() if info['account'] == receiver_acc), None)
    
    if not receiver_id or receiver_id == me_id:
        return "<script>alert('계좌번호가 틀렸거나 본인입니다.'); history.back();</script>"
    
    if users[me_id]['balance'] < amount:
        return "<script>alert('잔액이 부족합니다.'); history.back();</script>"
    
    # 2. 송금 처리
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    users[me_id]['balance'] -= amount
    users[receiver_id]['balance'] += amount
    
    # 기록 남기기
    users[me_id]['history'].append({
        "date": now, "type": "출금", "target": f"{users[receiver_id]['name']}({receiver_acc})",
        "amount": -amount, "balance": users[me_id]['balance']
    })
    users[receiver_id]['history'].append({
        "date": now, "type": "입금", "target": f"{users[me_id]['name']}({users[me_id]['account']})",
        "amount": amount, "balance": users[receiver_id]['balance']
    })
    
    save_data(users)
    return f"<script>alert('{users[receiver_id]['name']}님께 {amount} NAD를 보냈습니다!'); location.href='/dashboard';</script>"

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users = load_data()
        new_id = request.form.get('user_id')
        pw = request.form.get('pw')
        name = request.form.get('name')

        if new_id in users:
            return "<script>alert('이미 사용 중인 아이디입니다.'); history.back();</script>"

        hashed_pw = generate_password_hash(pw)
        new_acc = f"110-{random.randint(100, 999)}"
        
        users[new_id] = {
            "name": name, "pw": hashed_pw, "account": new_acc, "balance": 1000, "is_active": True,
            "history": [{"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "type": "입금", "target": "가상중앙은행(가입축하)", "amount": 1000, "balance": 1000}]
        }
        
        save_data(users)
        return "<script>alert('축하합니다! 가상중앙은행 계좌가 개설되었습니다.'); location.href='/';</script>"
    return render_template('register.html')

@app.route('/admin')
def admin_panel():
    if 'user_id' not in session or session['user_id'] != 'admin':
        return "<script>alert('관리자만 접근 가능합니다!'); location.href='/dashboard';</script>"
    
    users = load_data()
    total_balance = sum(u['balance'] for u in users.values())
    user_count = len(users)
    return render_template('admin.html', users=users, total_balance=total_balance, user_count=user_count)

@app.route('/admin/action/<target_id>', methods=['POST'])
def admin_action(target_id):
    if 'user_id' not in session or session['user_id'] != 'admin':
        return "권한이 없습니다.", 403
    
    users = load_data()
    action = request.form.get('action')
    
    if target_id not in users:
        return "<script>alert('해당 유저를 찾을 수 없습니다.'); history.back();</script>"

    if action == 'adjust':
        amount_str = request.form.get('amount', '0')
        amount = int(amount_str) if amount_str else 0
        users[target_id]['balance'] += amount
        type_str = "지급" if amount > 0 else "회수"
        
        users[target_id]['history'].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "type": f"관리자 {type_str}", "target": "중앙은행관리실", "amount": amount, "balance": users[target_id]['balance']
        })
        msg = f"{abs(amount)} NAD가 {type_str}되었습니다."

    elif action == 'toggle_status':
        current_status = users[target_id].get('is_active', True)
        users[target_id]['is_active'] = not current_status
        status_str = "정상" if users[target_id]['is_active'] else "정지"
        msg = f"계좌가 {status_str} 상태로 변경되었습니다."

    save_data(users)
    return f"<script>alert('{msg}'); location.href='/admin';</script>"

if __name__ == "__main__":
    app.run(debug=True, port=5000)