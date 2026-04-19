import json
import os
import random
from datetime import datetime # 시간 기록용

DB_FILE = "bank_db.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"admin": {"name": "관리자", "pw": "1234", "account": "110-000", "balance": 1000000, "history": []}}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def register_user(users):
    print("\n--- 신규 회원가입 ---")
    new_id = input("사용할 아이디: ")
    if new_id in users:
        print("❌ 이미 존재하는 아이디입니다.")
        return
    pw = input("사용할 비밀번호: ")
    name = input("이름: ")
    existing_accounts = {info["account"] for info in users.values()}
    new_acc = f"110-{random.randint(100, 999)}"
    while new_acc in existing_accounts:
        new_acc = f"110-{random.randint(100, 999)}"
    
    # 회원가입 시 history 리스트를 빈 상태로 추가
    users[new_id] = {
        "name": name, "pw": pw, "account": new_acc, 
        "balance": 1000, "history": [{"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "type": "입금", "target": "시스템(가입축하금)", "amount": 1000, "balance": 1000}]
    }
    save_data(users)
    print(f"🎉 가입 완료! {name}님, 가입 축하금 1000 NAD가 입금되었습니다.")

def main():
    # 메인 시스템 시작
    users = load_data()

    while True:
        print("\n" + "="*30)
        print("      NAD 가상 은행 시스템")
        print("="*30)
        user_id = input("아이디 (가입: join, 종료: exit): ")

        if user_id.lower() == 'exit': break
        if user_id.lower() == 'join':
            register_user(users)
            continue

        if user_id in users:
            input_pw = input("비밀번호: ")
            if users[user_id]["pw"] == input_pw:
                print(f"✅ 로그인 성공!")
            
                while True:
                    me = users[user_id]
                    print(f"\n[ {me['name']}님 | 잔액: {me['balance']} NAD ]")
                    print("1. 송금 | 2. 거래내역 조회 | 3. 내 정보 | 4. 로그아웃")
                    choice = input("선택: ")

                    if choice == "1":
                        receiver_acc = input("보낼 계좌번호: ")
                        receiver_id = next((uid for uid, info in users.items() if info['account'] == receiver_acc), None)
                    
                        if receiver_id and receiver_id != user_id:
                            try:
                                amount = int(input("금액: "))
                                if 0 < amount <= me['balance']:
                                    # 시간 생성
                                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                                
                                    # 1. 실제 잔액 변경
                                    users[user_id]['balance'] -= amount
                                    users[receiver_id]['balance'] += amount
                                
                                    # 2. 보내는 사람 기록 추가
                                    users[user_id]['history'].append({
                                        "date": now, "type": "출금", "target": users[receiver_id]['name'],
                                        "amount": -amount, "balance": users[user_id]['balance']
                                    })
                                
                                    # 3. 받는 사람 기록 추가
                                    # 기존 데이터에 history가 없을 경우를 대비해 처리
                                    if "history" not in users[receiver_id]: users[receiver_id]["history"] = []
                                    users[receiver_id]['history'].append({
                                        "date": now, "type": "입금", "target": users[user_id]['name'],
                                        "amount": amount, "balance": users[receiver_id]['balance']
                                    })

                                    save_data(users)
                                    print(f"✅ {users[receiver_id]['name']}님께 송금 완료!")
                                else:
                                    print("❌ 금액은 0보다 크고 잔액 이하여야 합니다.")
                            except ValueError:
                                print("❌ 숫자만 입력!")
                        else:
                            print("❌ 대상을 찾을 수 없습니다.")

                    elif choice == "2":
                        print(f"\n--- [{me['name']}]님의 거래 내역 ---")
                        if not me.get('history'):
                            print("거래 내역이 없습니다.")
                        else:
                            for h in reversed(me['history']): # 최신순으로 출력
                                print(f"[{h['date']}] {h['type']} | 대상: {h['target']} | 금액: {h['amount']} | 잔액: {h['balance']}")
                        input("\n(엔터를 누르면 메뉴로 돌아갑니다)")

                    elif choice == "3":
                        print(f"\n이름: {me['name']}\n계좌: {me['account']}\n잔액: {me['balance']}")
                        input("\n(엔터)")

                    elif choice == "4":
                        break
            else:
                print("❌ 비밀번호 불일치")
        else:
            print("❌ 아이디 없음")

if __name__ == "__main__":
    main()
