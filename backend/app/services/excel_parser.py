import pandas as pd
import io

# Attendance-list exports are ragged: title/metadata rows have far fewer
# tab-separated fields than the student rows. pandas would otherwise infer the
# column count from the first row and raise a ParserError on the wider rows
# ("Expected N fields in line X, saw M"). Naming a fixed, generously wide set of
# columns makes pandas pad short rows with NaN instead of erroring.
_MAX_TSV_COLUMNS = 50


def parse_students_from_excel(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Parses a student list Excel/TSV file.
    Returns a list of dicts: [{'name': '...', 'email': '...', 'class_group': '...'}]
    """
    # Attempt to load as dataframe
    df = None
    
    # Try reading as TSV first if it's an .xls that's actually a TSV (common for exported system files)
    try:
        if file_bytes.startswith(b'"Class Attendance List') or b'\t' in file_bytes[:100]:
            df = pd.read_csv(io.BytesIO(file_bytes), sep='\t', header=None, names=range(_MAX_TSV_COLUMNS), encoding='utf-8', engine='python')
    except Exception:
        pass

    if df is None:
        try:
            if filename.endswith('.xlsx'):
                df = pd.read_excel(io.BytesIO(file_bytes), header=None, engine='openpyxl')
            elif filename.endswith('.xls'):
                try:
                    df = pd.read_excel(io.BytesIO(file_bytes), header=None, engine='xlrd')
                except Exception:
                    # Fallback to TSV if xlrd fails (e.g. BOF record not found)
                    df = pd.read_csv(io.BytesIO(file_bytes), sep='\t', header=None, names=range(_MAX_TSV_COLUMNS), encoding='utf-8', engine='python')
            else:
                df = pd.read_excel(io.BytesIO(file_bytes), header=None)
        except Exception as e:
            raise ValueError(f"Failed to parse file: {str(e)}")

    if df is None:
        raise ValueError("Failed to parse file: unknown format")

    students = []
    current_class_group = None

    for index, row in df.iterrows():
        # Convert row to list of strings, replacing NaNs with empty string
        row_values = [str(val).strip() if pd.notna(val) else "" for val in row.to_list()]
        
        if not row_values:
            continue
            
        col_0 = row_values[0]
        
        # Detect Class Group
        if col_0.startswith("Class Group:"):
            current_class_group = col_0.replace("Class Group:", "").strip()
            continue

        # If we have at least 6 columns, check if it's a student row
        if len(row_values) >= 6:
            name = row_values[1]
            username = row_values[5]

            # Skip header row or empty name/username
            if not name or not username or name.lower() == "name" or username.lower() == "vms acc" or "prog/ yr/" in name.lower():
                continue

            # It's a student row
            email = f"{username.lower()}@e.ntu.edu.sg"
            
            students.append({
                "name": name,
                "email": email,
                "class_group": current_class_group
            })

    return students
