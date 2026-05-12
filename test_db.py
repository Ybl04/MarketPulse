import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="marketpulse",
        user="ybl_market",
        password="marketybl0011223"
    )
    print("Connection successful")
    conn.close()
except Exception as e:
    print(f"Error: {e}")