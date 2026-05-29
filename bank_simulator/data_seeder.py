"""
Bank Simulator Data Seeder
===========================
Tạo dữ liệu giả lập chất lượng cao cho Financial AI Advisor

Features:
- 50 users với 3 personas khác nhau
- 100+ transactions/user trong 3 tháng
- 5% anomaly transactions
- Dữ liệu realistic với Faker
"""

import os
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any

import psycopg2
from faker import Faker
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Load environment variables from local .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Initialize Faker với locale tiếng Việt
fake = Faker(['vi_VN', 'en_US'])

# ============================================================================
# Configuration
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env file")

NUM_USERS = 50
TRANSACTIONS_PER_USER_MIN = 100
TRANSACTIONS_PER_USER_MAX = 150
ANOMALY_RATE = 0.05  # 5% giao dịch là anomaly
MONTHS_BACK = 3

# ============================================================================
# Persona Definitions
# ============================================================================

PERSONAS = {
    "Student": {
        "monthly_income": (3_000_000, 8_000_000),  # 3-8 triệu VND
        "initial_balance": (500_000, 5_000_000),
        "categories": {
            "Ăn uống": 0.35,
            "Giải trí": 0.20,
            "Di chuyển": 0.15,
            "Mua sắm": 0.15,
            "Học tập": 0.10,
            "Khác": 0.05,
        },
        "avg_transaction": (20_000, 200_000),
        "merchants": {
            "Ăn uống": ["Highlands Coffee", "The Coffee House", "Phở 24", "Lotteria", "KFC", "Cơm tấm Sài Gòn", "Bún bò Huế", "Bánh mì Hòa Mã"],
            "Giải trí": ["CGV Cinemas", "Lotte Cinema", "Galaxy Cinema", "Spotify", "Netflix", "Steam", "Karaoke Nice"],
            "Di chuyển": ["Grab", "Be", "Xe buýt", "Xăng Petrolimex", "Bãi giữ xe"],
            "Mua sắm": ["Shopee", "Lazada", "Tiki", "Circle K", "FamilyMart", "Thế giới di động"],
            "Học tập": ["Nhà sách Fahasa", "Coursera", "Udemy", "Photocopy", "Văn phòng phẩm"],
            "Khác": ["Tiền nhà", "Điện nước", "Internet FPT", "Viettel"],
        }
    },
    "Office Worker": {
        "monthly_income": (12_000_000, 30_000_000),  # 12-30 triệu VND
        "initial_balance": (5_000_000, 20_000_000),
        "categories": {
            "Ăn uống": 0.25,
            "Di chuyển": 0.20,
            "Mua sắm": 0.20,
            "Dịch vụ": 0.15,
            "Giải trí": 0.10,
            "Sức khỏe": 0.05,
            "Khác": 0.05,
        },
        "avg_transaction": (50_000, 500_000),
        "merchants": {
            "Ăn uống": ["Starbucks", "Highlands Coffee", "Nhà hàng Món Huế", "Sushi Hokkaido", "Pizza 4P's", "Gogi House", "Lẩu Hải Sản"],
            "Di chuyển": ["Grab", "Xăng Shell", "Xăng Petrolimex", "Bảo dưỡng xe", "Gửi xe tháng"],
            "Mua sắm": ["Vincom", "Aeon Mall", "Shopee", "Lazada", "Uniqlo", "H&M", "Decathlon"],
            "Dịch vụ": ["Tiền nhà", "Điện nước", "Internet", "Bảo hiểm", "Gym", "Cắt tóc"],
            "Giải trí": ["CGV", "Netflix", "Spotify", "Du lịch cuối tuần", "Massage"],
            "Sức khỏe": ["Phòng khám", "Nhà thuốc", "Vitamin", "Khám định kỳ"],
            "Khác": ["Quà tặng", "Từ thiện", "Sửa chữa"],
        }
    },
    "High-Net-Worth": {
        "monthly_income": (50_000_000, 200_000_000),  # 50-200 triệu VND
        "initial_balance": (50_000_000, 500_000_000),
        "categories": {
            "Du lịch": 0.25,
            "Mua sắm": 0.20,
            "Ăn uống": 0.15,
            "Đầu tư": 0.15,
            "Dịch vụ cao cấp": 0.10,
            "Sức khỏe": 0.08,
            "Giải trí": 0.05,
            "Khác": 0.02,
        },
        "avg_transaction": (500_000, 10_000_000),
        "merchants": {
            "Du lịch": ["Vietnam Airlines", "Vietjet", "Khách sạn JW Marriott", "Vinpearl Resort", "Agoda", "Booking.com", "Tour du lịch"],
            "Mua sắm": ["Louis Vuitton", "Gucci", "Apple Store", "Rolex", "Vincom Luxury", "Takashimaya"],
            "Ăn uống": ["Nhà hàng La Vela", "The Deck Saigon", "Shri Restaurant", "Noir Dining", "Sushi Rei"],
            "Đầu tư": ["Chứng khoán SSI", "Vietcombank Securities", "Quỹ đầu tư", "Bất động sản"],
            "Dịch vụ cao cấp": ["Spa Thann", "Golf club", "Private banking", "Tư vấn tài chính"],
            "Sức khỏe": ["Bệnh viện FV", "Phòng khám Quốc tế", "Nha khoa Paris", "Khám sức khỏe tổng quát"],
            "Giải trí": ["Câu lạc bộ golf", "Yacht club", "Casino", "Sự kiện VIP"],
            "Khác": ["Từ thiện", "Quà tặng cao cấp", "Bảo hiểm cao cấp"],
        }
    }
}

BANKS = ["Vietcombank", "Techcombank", "BIDV", "VietinBank", "ACB", "MB Bank", "TPBank", "Sacombank"]

# ============================================================================
# Helper Functions
# ============================================================================

def generate_account_number() -> str:
    """Tạo số tài khoản ngân hàng realistic"""
    return f"{random.randint(1000000000, 9999999999)}"


def generate_reference_number() -> str:
    """Tạo mã tham chiếu giao dịch unique"""
    return f"TXN{datetime.now().strftime('%Y%m%d')}{random.randint(100000, 999999)}{uuid.uuid4().hex[:6]}"


def random_date_in_range(start_date: datetime, end_date: datetime) -> datetime:
    """Tạo ngày giờ random trong khoảng thời gian"""
    time_delta = end_date - start_date
    random_days = random.randint(0, time_delta.days)
    random_seconds = random.randint(0, 86400)  # Seconds in a day
    return start_date + timedelta(days=random_days, seconds=random_seconds)


def is_anomaly_transaction() -> bool:
    """Xác định xem giao dịch có phải là anomaly không (5% chance)"""
    return random.random() < ANOMALY_RATE


def generate_anomaly_reason() -> str:
    """Tạo lý do cho anomaly transaction"""
    reasons = [
        "Giao dịch vượt ngưỡng bình thường",
        "Merchant lạ, chưa từng giao dịch",
        "Giao dịch vào thời gian bất thường (3-5 AM)",
        "Số tiền gấp 3-5 lần trung bình",
        "Địa điểm giao dịch bất thường",
        "Nhiều giao dịch liên tiếp trong thời gian ngắn",
    ]
    return random.choice(reasons)


def calculate_anomaly_amount(normal_amount: float, persona_type: str) -> float:
    """Tính toán số tiền cho anomaly transaction (gấp 1.5-2 lần bình thường)"""
    multiplier = random.uniform(1.5, 2.0)  # Giảm từ 3-5 xuống 1.5-2
    return normal_amount * multiplier


# ============================================================================
# Database Operations
# ============================================================================

def get_db_connection():
    """Tạo kết nối đến database"""
    return psycopg2.connect(DATABASE_URL)


def create_user_persona(conn, user_id: uuid.UUID, persona_type: str) -> Dict[str, Any]:
    """Tạo persona cho user"""
    persona_config = PERSONAS[persona_type]
    monthly_income = random.uniform(*persona_config["monthly_income"])
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_personas (user_id, persona_type, monthly_income, spending_pattern, risk_profile)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (
        str(user_id),
        persona_type,
        monthly_income,
        psycopg2.extras.Json(persona_config["categories"]),
        random.choice(["low", "medium", "high"])
    ))
    
    persona_id = cursor.fetchone()[0]
    conn.commit()
    
    return {
        "id": persona_id,
        "user_id": user_id,
        "persona_type": persona_type,
        "monthly_income": monthly_income,
        "config": persona_config
    }


def create_bank_account(conn, user_id: uuid.UUID, persona_config: Dict) -> uuid.UUID:
    """Tạo tài khoản ngân hàng cho user"""
    initial_balance = random.uniform(*persona_config["initial_balance"])
    account_number = generate_account_number()
    bank_name = random.choice(BANKS)
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bank_accounts (user_id, account_number, bank_name, balance, account_type, currency)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        str(user_id),
        account_number,
        bank_name,
        initial_balance,
        "checking",
        "VND"
    ))
    
    account_id = cursor.fetchone()[0]
    conn.commit()
    
    return account_id


def generate_transactions_for_user(
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    persona_type: str,
    persona_config: Dict,
    num_transactions: int
) -> List[Dict[str, Any]]:
    """Tạo danh sách transactions cho một user"""
    transactions = []
    
    # Thời gian bắt đầu và kết thúc
    end_date = datetime.now()
    start_date = end_date - timedelta(days=MONTHS_BACK * 30)
    
    # Lấy balance hiện tại - TĂNG LÊN ĐỂ ĐỦ TIỀN
    initial_balance = random.uniform(*persona_config["initial_balance"]) * 3  # x3 để đủ tiền
    current_balance = initial_balance
    
    # Tạo income transactions (lương hàng tháng) - THÊM TRƯỚC
    income_transactions = []
    for month in range(MONTHS_BACK):
        salary_date = end_date - timedelta(days=(MONTHS_BACK - month - 1) * 30 + random.randint(1, 5))
        salary_amount = random.uniform(*PERSONAS[persona_type]["monthly_income"])
        
        income_transactions.append({
            "user_id": str(user_id),
            "account_id": str(account_id),
            "transaction_type": "credit",
            "amount": salary_amount,
            "merchant": "Công ty - Chuyển lương",
            "merchant_category": "Income",
            "category": "Thu nhập",
            "description": f"Lương tháng {salary_date.strftime('%m/%Y')}",
            "balance_after": 0,  # Sẽ tính lại sau
            "is_anomaly": False,
            "anomaly_reason": None,
            "location": "Việt Nam",
            "payment_method": "transfer",
            "reference_number": generate_reference_number(),
            "created_at": salary_date
        })
    
    # Tạo spending transactions
    categories = list(persona_config["categories"].keys())
    category_weights = list(persona_config["categories"].values())
    
    spending_transactions = []
    
    for _ in range(num_transactions):
        # Random category dựa trên weights
        category = random.choices(categories, weights=category_weights)[0]
        
        # Random merchant trong category
        merchants = persona_config["merchants"].get(category, ["Unknown Merchant"])
        merchant = random.choice(merchants)
        
        # Tính toán amount - GIẢM XUỐNG ĐỂ KHÔNG HẾT TIỀN
        min_amt, max_amt = persona_config["avg_transaction"]
        base_amount = random.uniform(min_amt, max_amt) * 0.5  # Giảm 50%
        
        # Xác định có phải anomaly không
        is_anomaly = is_anomaly_transaction()
        
        if is_anomaly:
            amount = calculate_anomaly_amount(base_amount, persona_type)
            anomaly_reason = generate_anomaly_reason()
        else:
            amount = base_amount
            anomaly_reason = None
        
        # Random date
        tx_date = random_date_in_range(start_date, end_date)
        
        # Payment method
        payment_method = random.choice(["card", "transfer", "online", "cash"])
        
        # Location
        locations = ["Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Cần Thơ", "Nha Trang", "Việt Nam"]
        location = random.choice(locations)
        
        spending_transactions.append({
            "user_id": str(user_id),
            "account_id": str(account_id),
            "transaction_type": "debit",
            "amount": amount,
            "merchant": merchant,
            "merchant_category": category,
            "category": category,
            "description": f"Thanh toán tại {merchant}",
            "balance_after": 0,  # Sẽ tính lại sau
            "is_anomaly": is_anomaly,
            "anomaly_reason": anomaly_reason,
            "location": location,
            "payment_method": payment_method,
            "reference_number": generate_reference_number(),
            "created_at": tx_date
        })
    
    # Merge và sort tất cả transactions theo thời gian
    all_transactions = income_transactions + spending_transactions
    all_transactions.sort(key=lambda x: x["created_at"])
    
    # Tính lại balance cho từng transaction theo đúng thứ tự
    current_balance = initial_balance
    for tx in all_transactions:
        if tx["transaction_type"] == "credit":
            current_balance += tx["amount"]
        else:
            current_balance -= tx["amount"]
        tx["balance_after"] = current_balance
    
    return all_transactions


def insert_transactions_batch(conn, transactions: List[Dict[str, Any]]):
    """Insert transactions vào database theo batch"""
    cursor = conn.cursor()
    
    query = """
        INSERT INTO bank_transactions (
            user_id, account_id, transaction_type, amount, merchant, merchant_category,
            category, description, balance_after, is_anomaly, anomaly_reason,
            location, payment_method, reference_number, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    
    data = [
        (
            tx["user_id"], tx["account_id"], tx["transaction_type"], tx["amount"],
            tx["merchant"], tx["merchant_category"], tx["category"], tx["description"],
            tx["balance_after"], tx["is_anomaly"], tx["anomaly_reason"],
            tx["location"], tx["payment_method"], tx["reference_number"], tx["created_at"]
        )
        for tx in transactions
    ]
    
    execute_batch(cursor, query, data, page_size=100)
    conn.commit()


def calculate_transaction_patterns(conn, user_id: uuid.UUID):
    """Tính toán patterns cho user để phát hiện anomaly"""
    cursor = conn.cursor()
    
    # Tính avg, std_dev cho mỗi category
    cursor.execute("""
        SELECT 
            category,
            AVG(amount) as avg_amount,
            STDDEV(amount) as std_deviation,
            COUNT(*) as frequency,
            array_agg(DISTINCT merchant) as merchants
        FROM bank_transactions
        WHERE user_id = %s AND transaction_type = 'debit'
        GROUP BY category
    """, (str(user_id),))
    
    patterns = cursor.fetchall()
    
    # Insert vào transaction_patterns
    for pattern in patterns:
        category, avg_amt, std_dev, freq, merchants = pattern
        
        cursor.execute("""
            INSERT INTO transaction_patterns (
                user_id, category, avg_amount, std_deviation, 
                frequency_per_month, typical_merchants
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            str(user_id),
            category,
            avg_amt or 0,
            std_dev or 0,
            freq // MONTHS_BACK,
            psycopg2.extras.Json(merchants)
        ))
    
    conn.commit()


# ============================================================================
# Main Seeding Function
# ============================================================================

def seed_data():
    """Main function để seed tất cả dữ liệu"""
    print("=" * 80)
    print("Bank Simulator Data Seeder")
    print("=" * 80)
    print(f"Creating data for {NUM_USERS} users...")
    print(f"Each user will have {TRANSACTIONS_PER_USER_MIN}-{TRANSACTIONS_PER_USER_MAX} transactions")
    print(f"Anomaly rate: {ANOMALY_RATE * 100}%")
    print("=" * 80)
    
    conn = get_db_connection()
    
    try:
        # Phân bổ personas
        persona_distribution = {
            "Student": NUM_USERS // 3,
            "Office Worker": NUM_USERS // 3,
            "High-Net-Worth": NUM_USERS - (2 * (NUM_USERS // 3))
        }
        
        total_transactions = 0
        total_anomalies = 0
        
        for persona_type, count in persona_distribution.items():
            print(f"\nCreating {count} users with persona: {persona_type}")
            
            for i in range(count):
                # Tạo user_id
                user_id = uuid.uuid4()
                
                # Tạo persona
                persona = create_user_persona(conn, user_id, persona_type)
                
                # Tạo bank account
                account_id = create_bank_account(conn, user_id, persona["config"])
                
                # Tạo transactions
                num_tx = random.randint(TRANSACTIONS_PER_USER_MIN, TRANSACTIONS_PER_USER_MAX)
                transactions = generate_transactions_for_user(
                    user_id, account_id, persona_type, persona["config"], num_tx
                )
                
                # Insert transactions
                insert_transactions_batch(conn, transactions)
                
                # Calculate patterns
                calculate_transaction_patterns(conn, user_id)
                
                # Statistics
                anomalies = sum(1 for tx in transactions if tx["is_anomaly"])
                total_transactions += len(transactions)
                total_anomalies += anomalies
                
                print(f"  ✓ User {i+1}/{count}: {len(transactions)} transactions ({anomalies} anomalies)")
        
        print("\n" + "=" * 80)
        print("Seeding completed!")
        print(f"Total users: {NUM_USERS}")
        print(f"Total transactions: {total_transactions}")
        print(f"Total anomalies: {total_anomalies} ({(total_anomalies/total_transactions)*100:.2f}%)")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nError: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    seed_data()
