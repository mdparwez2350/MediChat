
try:
    with open('error_log_6.txt', 'r', encoding='utf-16-le') as f:
        print(f.read())
except Exception as e:
    try:
        with open('error_log_6.txt', 'r', encoding='utf-8') as f:
            print(f.read())
    except Exception as e2:
         with open('error_log_6.txt', 'r', errors='ignore') as f:
            print(f.read())
