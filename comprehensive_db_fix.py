
import pymysql

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'BhardwajSai@123',
    'database': 'smartcity',
    'charset': 'utf8'
}

def fix_schema_comprehensive():
    con = pymysql.connect(**DB_CONFIG)
    try:
        with con.cursor() as cur:
            print("Ensuring columns are sufficiently long...")
            
            # Complaint Table
            cur.execute("ALTER TABLE complaint MODIFY COLUMN description TEXT")
            cur.execute("ALTER TABLE complaint MODIFY COLUMN category VARCHAR(255)")
            cur.execute("ALTER TABLE complaint MODIFY COLUMN priority VARCHAR(100)")
            cur.execute("ALTER TABLE complaint MODIFY COLUMN status VARCHAR(100)")
            cur.execute("ALTER TABLE complaint MODIFY COLUMN assigned_to VARCHAR(255)")
            
            # Municipality Table
            cur.execute("ALTER TABLE municipality MODIFY COLUMN municipality_desc TEXT")
            cur.execute("ALTER TABLE municipality MODIFY COLUMN city_name VARCHAR(255)")
            
            # Signup Table (Citizen)
            cur.execute("ALTER TABLE signup MODIFY COLUMN email_id VARCHAR(255)")
            cur.execute("ALTER TABLE signup MODIFY COLUMN address TEXT")
            
            con.commit()
            print("Comprehensive schema fix completed!")
    except Exception as e:
        print(f"Error: {e}")
        con.rollback()
    finally:
        con.close()

if __name__ == "__main__":
    fix_schema_comprehensive()
