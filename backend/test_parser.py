import asyncio
from app.services.excel_parser import parse_students_from_excel

def test_parse():
    with open("../SC5001_2025S2.xls", "rb") as f:
        file_bytes = f.read()
    
    students = parse_students_from_excel(file_bytes, "SC5001_2025S2.xls")
    print(f"Total students parsed: {len(students)}")
    if students:
        print("First 3:")
        for s in students[:3]:
            print(s)
        
        print("Last 3:")
        for s in students[-3:]:
            print(s)

if __name__ == "__main__":
    test_parse()
