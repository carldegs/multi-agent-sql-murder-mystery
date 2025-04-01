from db_manager import DatabaseManager

def main():
    print("Hello from multi-agent-sql-murder-mystery!")
    
    db_manager = DatabaseManager("sql-murder-mystery.db")
    db_manager.connect()
    
    results = db_manager.execute_query("SELECT * FROM interview") 
    print(results)
    
    db_manager.close()

if __name__ == "__main__":
    main()
