
import pymysql

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'BhardwajSai@123',
    'database': 'smartcity',
    'charset': 'utf8'
}

def check_schema():
    con = pymysql.connect(**DB_CONFIG)
    try:
        with con.cursor() as cur:
            print("--- complaint table ---")
            cur.execute("DESCRIBE complaint")
            for row in cur.fetchall():
                if 'name' in row[0] or 'muni' in row[0]:
                    print(row)
            
            print("\n--- municipality table ---")
            cur.execute("DESCRIBE municipality")
            for row in cur.fetchall():
                if 'name' in row[0] or 'muni' in row[0]:
                    print(row)
    finally:
        con.close()

if __name__ == "__main__":
    check_schema()
