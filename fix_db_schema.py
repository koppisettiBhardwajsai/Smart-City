
import pymysql

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'BhardwajSai@123',
    'database': 'smartcity',
    'charset': 'utf8'
}

def fix_schema():
    con = pymysql.connect(**DB_CONFIG)
    try:
        with con.cursor() as cur:
            # Increase municipality_name length in all relevant tables
            print("Altering complaint table...")
            cur.execute("ALTER TABLE complaint MODIFY COLUMN municipality_name VARCHAR(255)")
            
            print("Altering municipality table...")
            cur.execute("ALTER TABLE municipality MODIFY COLUMN municipality_name VARCHAR(255)")
            
            print("Altering fieldofficer table...")
            cur.execute("ALTER TABLE fieldofficer MODIFY COLUMN municipality_name VARCHAR(255)")
            
            con.commit()
            print("Schema fixed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        con.rollback()
    finally:
        con.close()

if __name__ == "__main__":
    fix_schema()
