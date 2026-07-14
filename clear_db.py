import sqlite3
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def main():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    
    # Видаляємо всі сесії
    cursor.execute("DELETE FROM sessions")
    
    # Звільняємо всі лінії
    cursor.execute("UPDATE lines SET status = 'available'")
    
    conn.commit()
    conn.close()
    logger.info("Database cleared successfully!")

if __name__ == "__main__":
    main()
