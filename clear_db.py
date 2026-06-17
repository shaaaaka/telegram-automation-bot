import sqlite3

def main():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    
    # Видаляємо всі сесії
    cursor.execute("DELETE FROM sessions")
    
    # Звільняємо всі лінії
    cursor.execute("UPDATE lines SET status = 'available'")
    
    conn.commit()
    conn.close()
    print("Database cleared successfully!")

if __name__ == "__main__":
    main()
