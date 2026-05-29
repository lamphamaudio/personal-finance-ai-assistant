"""
Bank Simulator FastAPI Backend
===============================
REST API để các service khác lấy dữ liệu từ Bank Simulator

Endpoints:
- GET /transactions?user_id={uuid}
- GET /summary?user_id={uuid}
- GET /anomalies?user_id={uuid}
- GET /prediction?user_id={uuid}
- GET /users (List all users)
- GET /stats (Overall statistics)
"""

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pathlib import Path

import psycopg2
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from local .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# ============================================================================
# Configuration
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env file")

API_PORT = int(os.getenv("BANK_SIMULATOR_PORT", "8000"))
API_HOST = os.getenv("BANK_SIMULATOR_HOST", "0.0.0.0")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Bank Simulator API",
    description="REST API cho Financial AI Advisor - Bank Simulator Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Pydantic Models
# ============================================================================

class Transaction(BaseModel):
    id: str
    user_id: str
    account_id: str
    transaction_type: str
    amount: float
    merchant: str
    merchant_category: str
    category: str
    description: Optional[str] = None
    balance_after: float
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    location: Optional[str] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }


class CategorySummary(BaseModel):
    category: str
    total_amount: float
    transaction_count: int
    avg_amount: float
    percentage: float


class SpendingSummary(BaseModel):
    user_id: str
    total_spending: float
    total_income: float
    net_cashflow: float
    categories: List[CategorySummary]
    period_days: int


class AnomalyTransaction(BaseModel):
    id: str
    amount: float
    merchant: str
    category: str
    anomaly_reason: str
    created_at: datetime
    severity: str  # low, medium, high


class PredictionResponse(BaseModel):
    user_id: str
    current_balance: float
    predicted_end_of_month_balance: float
    avg_daily_spending: float
    days_remaining: int
    spending_trend: str  # increasing, stable, decreasing
    recommendation: str


class UserInfo(BaseModel):
    user_id: str
    persona_type: str
    account_number: str
    bank_name: str
    current_balance: float
    transaction_count: int
    anomaly_count: int


class OverallStats(BaseModel):
    total_users: int
    total_transactions: int
    total_anomalies: int
    anomaly_rate: float
    total_volume: float
    personas: Dict[str, int]


# ============================================================================
# Database Helper Functions
# ============================================================================

def get_db_connection():
    """Tạo kết nối database"""
    return psycopg2.connect(DATABASE_URL)


def row_to_dict(cursor, row) -> Dict[str, Any]:
    """Convert database row to dictionary"""
    if row is None:
        return {}
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Bank Simulator API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": [
            "/transactions",
            "/summary",
            "/anomalies",
            "/prediction",
            "/users",
            "/stats"
        ]
    }


@app.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    user_id: str = Query(..., description="UUID của user"),
    limit: int = Query(100, ge=1, le=1000, description="Số lượng transactions tối đa"),
    offset: int = Query(0, ge=0, description="Offset cho pagination"),
    category: Optional[str] = Query(None, description="Filter theo category"),
    start_date: Optional[str] = Query(None, description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Ngày kết thúc (YYYY-MM-DD)")
):
    """
    Lấy danh sách transactions của user
    
    - **user_id**: UUID của user
    - **limit**: Số lượng records tối đa (default: 100)
    - **offset**: Offset cho pagination (default: 0)
    - **category**: Filter theo category (optional)
    - **start_date**: Filter từ ngày (optional)
    - **end_date**: Filter đến ngày (optional)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT 
                id, user_id, account_id, transaction_type, amount, merchant,
                merchant_category, category, description, balance_after,
                is_anomaly, anomaly_reason, location, payment_method,
                reference_number, created_at
            FROM bank_transactions
            WHERE user_id = %s
        """
        params = [user_id]
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        if start_date:
            query += " AND created_at >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND created_at <= %s"
            params.append(end_date)
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        transactions = []
        for row in rows:
            tx_dict = row_to_dict(cursor, row)
            transactions.append(Transaction(**tx_dict))
        
        cursor.close()
        conn.close()
        
        return transactions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/summary", response_model=SpendingSummary)
async def get_spending_summary(
    user_id: str = Query(..., description="UUID của user"),
    days: int = Query(90, ge=1, le=365, description="Số ngày để tính summary")
):
    """
    Lấy tổng quan chi tiêu của user theo category
    
    - **user_id**: UUID của user
    - **days**: Số ngày để tính summary (default: 90)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get category breakdown
        cursor.execute("""
            SELECT 
                category,
                SUM(amount) as total_amount,
                COUNT(*) as transaction_count,
                AVG(amount) as avg_amount
            FROM bank_transactions
            WHERE user_id = %s 
                AND transaction_type = 'debit'
                AND created_at >= %s
            GROUP BY category
            ORDER BY total_amount DESC
        """, (user_id, start_date))
        
        category_rows = cursor.fetchall()
        
        # Calculate totals
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN transaction_type = 'debit' THEN amount ELSE 0 END) as total_spending,
                SUM(CASE WHEN transaction_type = 'credit' THEN amount ELSE 0 END) as total_income
            FROM bank_transactions
            WHERE user_id = %s AND created_at >= %s
        """, (user_id, start_date))
        
        totals = cursor.fetchone()
        total_spending = float(totals[0] or 0)
        total_income = float(totals[1] or 0)
        
        # Build category summaries
        categories = []
        for row in category_rows:
            # row = (category, total_amount, transaction_count, avg_amount)
            category_name = row[0]
            total_amount = float(row[1])
            transaction_count = int(row[2])
            avg_amount = float(row[3])
            
            categories.append(CategorySummary(
                category=category_name,
                total_amount=total_amount,
                transaction_count=transaction_count,
                avg_amount=avg_amount,
                percentage=(total_amount / total_spending * 100) if total_spending > 0 else 0
            ))
        
        cursor.close()
        conn.close()
        
        return SpendingSummary(
            user_id=user_id,
            total_spending=total_spending,
            total_income=total_income,
            net_cashflow=total_income - total_spending,
            categories=categories,
            period_days=days
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/anomalies", response_model=List[AnomalyTransaction])
async def get_anomalies(
    user_id: str = Query(..., description="UUID của user"),
    limit: int = Query(50, ge=1, le=200, description="Số lượng anomalies tối đa")
):
    """
    Lấy danh sách giao dịch bất thường (anomalies)
    
    - **user_id**: UUID của user
    - **limit**: Số lượng records tối đa (default: 50)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, amount, merchant, category, anomaly_reason, created_at
            FROM bank_transactions
            WHERE user_id = %s AND is_anomaly = TRUE
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        
        anomalies = []
        for row in rows:
            tx_dict = row_to_dict(cursor, row)
            
            # Determine severity based on amount
            amount = float(tx_dict["amount"])
            if amount > 10_000_000:
                severity = "high"
            elif amount > 1_000_000:
                severity = "medium"
            else:
                severity = "low"
            
            anomalies.append(AnomalyTransaction(
                id=tx_dict["id"],
                amount=amount,
                merchant=tx_dict["merchant"],
                category=tx_dict["category"],
                anomaly_reason=tx_dict["anomaly_reason"],
                created_at=tx_dict["created_at"],
                severity=severity
            ))
        
        cursor.close()
        conn.close()
        
        return anomalies
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/prediction", response_model=PredictionResponse)
async def get_balance_prediction(
    user_id: str = Query(..., description="UUID của user")
):
    """
    Dự đoán số dư cuối tháng dựa trên pattern chi tiêu
    
    - **user_id**: UUID của user
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current balance
        cursor.execute("""
            SELECT balance
            FROM bank_accounts
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))
        
        balance_row = cursor.fetchone()
        if not balance_row:
            raise HTTPException(status_code=404, detail="User not found")
        
        current_balance = float(balance_row[0])
        
        # Calculate average daily spending (last 30 days)
        cursor.execute("""
            SELECT 
                SUM(amount) / 30.0 as avg_daily_spending,
                COUNT(*) as tx_count
            FROM bank_transactions
            WHERE user_id = %s 
                AND transaction_type = 'debit'
                AND created_at >= NOW() - INTERVAL '30 days'
        """, (user_id,))
        
        spending_row = cursor.fetchone()
        avg_daily_spending = float(spending_row[0] or 0)
        
        # Calculate spending trend (compare last 15 days vs previous 15 days)
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN created_at >= NOW() - INTERVAL '15 days' THEN amount ELSE 0 END) as recent,
                SUM(CASE WHEN created_at < NOW() - INTERVAL '15 days' AND created_at >= NOW() - INTERVAL '30 days' THEN amount ELSE 0 END) as previous
            FROM bank_transactions
            WHERE user_id = %s AND transaction_type = 'debit'
        """, (user_id,))
        
        trend_row = cursor.fetchone()
        recent_spending = float(trend_row[0] or 0)
        previous_spending = float(trend_row[1] or 0)
        
        if previous_spending > 0:
            trend_ratio = recent_spending / previous_spending
            if trend_ratio > 1.1:
                spending_trend = "increasing"
            elif trend_ratio < 0.9:
                spending_trend = "decreasing"
            else:
                spending_trend = "stable"
        else:
            spending_trend = "stable"
        
        # Calculate days remaining in month
        now = datetime.now()
        last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        days_remaining = (last_day - now).days
        
        # Predict end of month balance
        predicted_spending = avg_daily_spending * days_remaining
        predicted_balance = current_balance - predicted_spending
        
        # Generate recommendation
        if predicted_balance < 0:
            recommendation = "⚠️ Cảnh báo: Số dư dự kiến âm. Hãy giảm chi tiêu hoặc tăng thu nhập."
        elif predicted_balance < current_balance * 0.2:
            recommendation = "⚡ Lưu ý: Số dư cuối tháng thấp. Nên kiểm soát chi tiêu."
        elif spending_trend == "increasing":
            recommendation = "📈 Chi tiêu đang tăng. Hãy xem xét các khoản chi không cần thiết."
        else:
            recommendation = "✅ Tài chính ổn định. Tiếp tục duy trì thói quen tốt."
        
        cursor.close()
        conn.close()
        
        return PredictionResponse(
            user_id=user_id,
            current_balance=current_balance,
            predicted_end_of_month_balance=predicted_balance,
            avg_daily_spending=avg_daily_spending,
            days_remaining=days_remaining,
            spending_trend=spending_trend,
            recommendation=recommendation
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/users", response_model=List[UserInfo])
async def get_all_users(
    limit: int = Query(50, ge=1, le=100, description="Số lượng users tối đa"),
    persona_type: Optional[str] = Query(None, description="Filter theo persona type")
):
    """
    Lấy danh sách tất cả users
    
    - **limit**: Số lượng users tối đa (default: 50)
    - **persona_type**: Filter theo persona (Student, Office Worker, High-Net-Worth)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                ba.user_id,
                up.persona_type,
                ba.account_number,
                ba.bank_name,
                ba.balance,
                COUNT(bt.id) as transaction_count,
                COUNT(CASE WHEN bt.is_anomaly THEN 1 END) as anomaly_count
            FROM bank_accounts ba
            LEFT JOIN user_personas up ON ba.user_id = up.user_id
            LEFT JOIN bank_transactions bt ON ba.user_id = bt.user_id
        """
        
        params = []
        if persona_type:
            query += " WHERE up.persona_type = %s"
            params.append(persona_type)
        
        query += """
            GROUP BY ba.user_id, up.persona_type, ba.account_number, ba.bank_name, ba.balance
            ORDER BY ba.balance DESC
            LIMIT %s
        """
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        users = []
        for row in rows:
            user_dict = row_to_dict(cursor, row)
            users.append(UserInfo(
                user_id=user_dict["user_id"],
                persona_type=user_dict["persona_type"] or "Unknown",
                account_number=user_dict["account_number"],
                bank_name=user_dict["bank_name"],
                current_balance=float(user_dict["balance"]),
                transaction_count=int(user_dict["transaction_count"]),
                anomaly_count=int(user_dict["anomaly_count"])
            ))
        
        cursor.close()
        conn.close()
        
        return users
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/stats", response_model=OverallStats)
async def get_overall_stats():
    """
    Lấy thống kê tổng quan của toàn bộ hệ thống
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total users
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM bank_accounts")
        total_users = cursor.fetchone()[0]
        
        # Total transactions
        cursor.execute("SELECT COUNT(*) FROM bank_transactions")
        total_transactions = cursor.fetchone()[0]
        
        # Total anomalies
        cursor.execute("SELECT COUNT(*) FROM bank_transactions WHERE is_anomaly = TRUE")
        total_anomalies = cursor.fetchone()[0]
        
        # Total volume
        cursor.execute("SELECT SUM(amount) FROM bank_transactions WHERE transaction_type = 'debit'")
        total_volume = float(cursor.fetchone()[0] or 0)
        
        # Personas distribution
        cursor.execute("""
            SELECT persona_type, COUNT(*) as count
            FROM user_personas
            GROUP BY persona_type
        """)
        persona_rows = cursor.fetchall()
        personas = {row[0]: row[1] for row in persona_rows}
        
        cursor.close()
        conn.close()
        
        anomaly_rate = (total_anomalies / total_transactions * 100) if total_transactions > 0 else 0
        
        return OverallStats(
            total_users=total_users,
            total_transactions=total_transactions,
            total_anomalies=total_anomalies,
            anomaly_rate=anomaly_rate,
            total_volume=total_volume,
            personas=personas
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 80)
    print("Bank Simulator API Server")
    print("=" * 80)
    print(f"Starting on: http://{API_HOST}:{API_PORT}")
    print(f"API Docs: http://localhost:{API_PORT}/docs")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'configured'}")
    print("=" * 80)
    uvicorn.run(app, host=API_HOST, port=API_PORT)
